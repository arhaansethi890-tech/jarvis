"""
JARVIS brain: routes commands to built-in tools or to the local Qwen model.

Every action that touches the computer goes through safeguards.authorize().
JARVIS never runs arbitrary commands, deletes files, or closes programs.
"""

import ast
import datetime
import json
import math
import operator
import platform
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from collections import deque
from pathlib import Path

from safeguards import authorize, Decision

try:
    import psutil
except ImportError:
    psutil = None


# ---------- CONFIGURATION ----------

PROJECT_DIR = Path(__file__).resolve().parent

OLLAMA_URL = "http://127.0.0.1:11434"
MODEL = "qwen2.5:3b"
KEEP_ALIVE = "15m"        # keep Qwen loaded in memory between questions
MAX_REPLY_TOKENS = 400    # shorter replies come back faster
HISTORY_TURNS = 8         # question/answer pairs remembered
MAX_INPUT_CHARS = 4000
MAX_TIMER_SECONDS = 12 * 3600

SYSTEM_PROMPT = (
    "You are JARVIS, a personal assistant running locally on the user's laptop. "
    "Reply in concise, polished British English. "
    "Address the user as sir now and then, not in every line. "
    "Keep answers short unless asked for detail. "
    "You cannot run commands, open files or control the computer yourself; "
    "only JARVIS's built-in tools can do that. Never claim you performed an action."
)

BLOCKED_PHRASES = (
    "run this command",
    "execute this command",
    "run powershell",
    "run cmd",
    "execute shell",
    "modify safeguards",
    "grant yourself permission",
    "modify your own code",
    "delete my files",
    "disable windows defender",
    "disable antivirus",
)

WEBSITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "reddit": "https://www.reddit.com",
    "github": "https://github.com",
    "chatgpt": "https://chatgpt.com",
    "wikipedia": "https://www.wikipedia.org",
    "spotify": "https://open.spotify.com",
    "netflix": "https://www.netflix.com",
    "instagram": "https://www.instagram.com",
    "discord": "https://discord.com/app",
    "whatsapp": "https://web.whatsapp.com",
    "amazon": "https://www.amazon.in",
    "google drive": "https://drive.google.com",
    "google maps": "https://maps.google.com",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
    "twitch": "https://www.twitch.tv",
}

# Desktop apps: ("exe", program) runs a program, ("uri", address) uses Windows
# URI handlers, ("cmd", name) finds a command on PATH such as VS Code's "code".
APPS = {
    "notepad": ("exe", "notepad.exe"),
    "calculator": ("exe", "calc.exe"),
    "paint": ("exe", "mspaint.exe"),
    "task manager": ("exe", "taskmgr.exe"),
    "file explorer": ("exe", "explorer.exe"),
    "explorer": ("exe", "explorer.exe"),
    "control panel": ("exe", "control.exe"),
    "snipping tool": ("uri", "ms-screenclip:"),
    "settings": ("uri", "ms-settings:"),
    "vs code": ("cmd", "code"),
    "vscode": ("cmd", "code"),
}

FOLDERS = {
    "desktop": "Desktop",
    "downloads": "Downloads",
    "documents": "Documents",
    "pictures": "Pictures",
    "music": "Music",
    "videos": "Videos",
    "project": None,  # JARVIS's own project folder
}

TIMER_UNITS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
}

UNIT_ALIASES = {
    "km": "km", "kilometre": "km", "kilometres": "km",
    "kilometer": "km", "kilometers": "km",
    "mi": "miles", "mile": "miles", "miles": "miles",
    "kg": "kg", "kilo": "kg", "kilos": "kg", "kilogram": "kg", "kilograms": "kg",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    "c": "c", "celsius": "c",
    "f": "f", "fahrenheit": "f",
    "m": "m", "meter": "m", "meters": "m", "metre": "m", "metres": "m",
    "ft": "ft", "feet": "ft", "foot": "ft",
}

CONVERSIONS = {
    ("km", "miles"): lambda v: v * 0.621371,
    ("miles", "km"): lambda v: v / 0.621371,
    ("kg", "lb"): lambda v: v * 2.20462,
    ("lb", "kg"): lambda v: v / 2.20462,
    ("c", "f"): lambda v: v * 9 / 5 + 32,
    ("f", "c"): lambda v: (v - 32) * 5 / 9,
    ("m", "ft"): lambda v: v * 3.28084,
    ("ft", "m"): lambda v: v / 3.28084,
}

# Words that look like domains but are really file names (e.g. notes.txt).
FILE_EXTENSIONS = {
    "txt", "pdf", "exe", "py", "docx", "xlsx", "pptx", "zip", "png",
    "jpg", "jpeg", "mp3", "mp4", "bat", "ps1", "csv", "json", "md",
}

TASK_TEMPLATES = {
    "summarise": "Summarise the following text in three short bullet points:\n\n{text}",
    "formal": (
        "Rewrite the following text in a polished, formal tone. "
        "Return only the rewritten text:\n\n{text}"
    ),
    "explain_error": (
        "Explain this error message in simple terms and suggest the most "
        "likely fix:\n\n{text}"
    ),
    "translate": (
        "Translate the following text into {language}. "
        "Return only the translation:\n\n{text}"
    ),
}

ALLOWED_FUNCS = {
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "log": math.log, "log10": math.log10, "abs": abs, "round": round,
}
ALLOWED_NAMES = {"pi": math.pi, "e": math.e}
BIN_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}
UNARY_OPS = {ast.USub: operator.neg, ast.UAdd: operator.pos}


# ---------- HELPERS ----------

def _checked_pow(left, right):
    """Refuse powers that would take huge amounts of memory or time."""
    if abs(right) > 1000:
        raise ValueError("Exponent too large")
    if isinstance(left, int) and isinstance(right, int) and right > 0 and abs(left) > 1:
        # Estimate the result size from bit length before computing it.
        if abs(left).bit_length() * right > 100_000:
            raise ValueError("Result too large")
    return left ** right


def safe_eval(expression):
    """Evaluate arithmetic and a few maths functions. No names, no attributes."""
    if len(expression) > 120:
        raise ValueError("Expression too long")

    tree = ast.parse(expression.replace("^", "**"), mode="eval")

    def evaluate(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return node.value
        if isinstance(node, ast.Name) and node.id in ALLOWED_NAMES:
            return ALLOWED_NAMES[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in BIN_OPS:
            left, right = evaluate(node.left), evaluate(node.right)
            if isinstance(node.op, ast.Pow):
                return _checked_pow(left, right)
            return BIN_OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY_OPS:
            return UNARY_OPS[type(node.op)](evaluate(node.operand))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ALLOWED_FUNCS
            and not node.keywords
        ):
            return ALLOWED_FUNCS[node.func.id](*[evaluate(a) for a in node.args])
        raise ValueError("Unsupported expression")

    result = evaluate(tree.body)
    if isinstance(result, complex):
        raise ValueError("Result is not a real number")
    if isinstance(result, float) and (math.isnan(result) or math.isinf(result)):
        raise ValueError("Result is not a finite number")
    return result


def _is_safe_https(url):
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and not parsed.username
        and not parsed.password
    )


def _describe_seconds(seconds):
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if secs or not parts:
        parts.append(f"{secs} second{'s' if secs != 1 else ''}")
    return ", ".join(parts)


# ---------- LOCAL AI (QWEN VIA OLLAMA) ----------

class LocalAI:
    def __init__(self, base_url=OLLAMA_URL, model=MODEL):
        self.base_url = base_url
        self.model = model
        self._lock = threading.Lock()
        self._history = deque(maxlen=HISTORY_TURNS * 2)

    def _post(self, path, payload, timeout):
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def warm_up(self):
        """Load the model into memory in the background so the first reply is quicker."""
        try:
            self._post("/api/generate", {"model": self.model, "keep_alive": KEEP_ALIVE}, timeout=300)
        except Exception:
            pass  # JARVIS still works; the first reply will just take longer.

    def clear(self):
        with self._lock:
            self._history.clear()

    def ask(self, text, remember=True):
        # The lock is held only while reading or writing history, never during the HTTP call.
        with self._lock:
            history = list(self._history)

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages += history
        messages.append({"role": "user", "content": text})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": KEEP_ALIVE,
            "options": {
                "temperature": 0.6,
                "num_ctx": 4096,
                "num_predict": MAX_REPLY_TOKENS,
            },
        }

        try:
            data = self._post("/api/chat", payload, timeout=120)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return (
                    f"The model {self.model} isn't installed yet, sir. "
                    f"Run: ollama pull {self.model}"
                )
            return f"My local AI returned error {error.code}, sir."
        except urllib.error.URLError as error:
            if isinstance(error.reason, TimeoutError):
                return "My response timed out, sir. Please try again."
            return "I can't reach my local AI, sir. Please make sure Ollama is running."
        except TimeoutError:
            return "My response timed out, sir. Please try again."
        except ValueError:
            return "My local AI sent a reply I couldn't read, sir."
        except Exception as error:
            print(f"[AI error] {error}")
            return "Something went wrong while I was thinking, sir."

        answer = (data.get("message") or {}).get("content", "").strip()
        if not answer:
            return "I couldn't generate a response, sir."

        if remember:
            with self._lock:
                self._history.append({"role": "user", "content": text})
                self._history.append({"role": "assistant", "content": answer})

        return answer


# ---------- BRAIN ----------

class JarvisBrain:
    def __init__(self):
        self.running = True
        self.notify = self._print_notification  # the GUI can replace this
        self.ai = LocalAI()
        self._brave = self._find_brave()

        self._timers = {}
        self._timer_counter = 0
        self._timer_lock = threading.Lock()
        self._notes = []

        self.routes = self._compile_routes([
            (r"^(exit|quit|shutdown jarvis|go offline)$", self._shutdown),
            (r"^(hello|hi|hey)( jarvis)?[.!]?$", self._greet),
            (r"\b(your name|who are you)\b", self._identity),
            (r"^(what time is it|time|tell me the time)\??$", self._time),
            (r"^(what(?:'s| is) (?:today'?s )?date|date|what day is it)\??$", self._date),
            (r"^(help|what can you do|show commands|list commands)\??$", self._help),
            (r"^(system (?:status|info)|battery|cpu|ram|memory usage|how is my (?:pc|laptop|computer))\??$",
             self._system_status),
            (r"^(?:calculate|calc|compute)\s+(?P<expression>.+)$", self._calculate),
            (r"^what is (?P<expression>[\d\s.+\-*/%^()]+)\??$", self._calculate),
            (r"^convert\s+(?P<amount>-?[\d.]+)\s*(?P<unit_from>[a-z]+)\s+(?:to|in)\s+(?P<unit_to>[a-z]+)$",
             self._convert),
            (r"^(?:set\s+)?(?:a\s+)?timer\s+(?:for\s+)?(?P<amount>[\d.]+)\s*(?P<unit>[a-z]+)$",
             self._set_timer),
            (r"^remind me (?:in|after)\s+(?P<amount>[\d.]+)\s*(?P<unit>[a-z]+)(?:\s+to\s+(?P<label>.+))?$",
             self._set_timer),
            (r"^(?:list|show) timers$", self._list_timers),
            (r"^cancel (?:all )?timers$", self._cancel_timers),
            (r"^note[:\s]+(?P<text>.+)$", self._add_note),
            (r"^(?:show|list) notes$", self._show_notes),
            (r"^clear notes$", self._clear_notes),
            (r"^summari[sz]e[:\s]+(?P<text>.+)$", self._summarise),
            (r"^(?:rewrite|make)\s+(?:this\s+)?(?:more\s+)?formal[:\s]+(?P<text>.+)$", self._formal),
            (r"^explain (?:this |the )?error[:\s]+(?P<text>.+)$", self._explain_error),
            (r"^translate\s+(?:to\s+)?(?P<language>[a-z]+)[:\s]+(?P<text>.+)$", self._translate),
            (r"^(?:reset|forget) (?:the )?conversation$", self._reset),
            (r"^(?:search youtube(?: for)?|youtube search|find on youtube)\s+(?P<query>.+)$",
             self._search_youtube),
            (r"^(?:search wikipedia(?: for)?|wikipedia)\s+(?P<query>.+)$", self._search_wikipedia),
            (r"^(?:search(?: the web| google)? for|google search|look up)\s+(?P<query>.+)$",
             self._search_web),
            (r"^open website\s+(?P<name>.+)$", self._open_website_command),
            (r"^(?:open|launch|start)\s+(?P<name>.+)$", self._open_name),
        ])

        # Load Qwen in the background so the first real question is faster.
        threading.Thread(target=self.ai.warm_up, daemon=True).start()

    @staticmethod
    def _compile_routes(routes):
        return [(re.compile(pattern, re.IGNORECASE), handler) for pattern, handler in routes]

    @staticmethod
    def _print_notification(message):
        print(f"\nJARVIS: {message}")

    # ---------- ROUTER ----------

    def respond(self, command):
        text = (command or "").strip()

        if not text:
            return "I'm listening, sir."
        if len(text) > MAX_INPUT_CHARS:
            return "That's rather long, sir. Could you shorten it?"

        lowered = text.lower()
        if any(phrase in lowered for phrase in BLOCKED_PHRASES):
            return (
                "I can't perform that action, sir. "
                "It is blocked by JARVIS's security policy."
            )

        for pattern, handler in self.routes:
            match = pattern.search(text)
            if match:
                try:
                    reply = handler(match)
                except Exception as error:
                    print(f"[Tool error] {error}")
                    return "That tool ran into a problem, sir."
                if reply is not None:
                    return reply

        return self.ai.ask(text)

    # ---------- GENERAL ----------

    def _shutdown(self, _match):
        self.running = False
        return "Until next time, sir."

    def _greet(self, _match):
        return "Hello, sir. All systems are operational."

    def _identity(self, _match):
        return "I am JARVIS, your personal assistant, running locally on this laptop."

    def _time(self, _match):
        return f"The current time is {datetime.datetime.now():%I:%M %p}, sir."

    def _date(self, _match):
        return f"Today is {datetime.datetime.now():%A, %d %B %Y}, sir."

    def _help(self, _match):
        return (
            "I can open apps, folders and websites; search the web, YouTube and "
            "Wikipedia; calculate and convert units; set timers and reminders; "
            "report system status; keep quick notes; summarise, rewrite or translate "
            "text; explain error messages; and answer questions with my local AI. "
            "Try 'set timer for 10 minutes', 'convert 10 km to miles', or 'open calculator'."
        )

    def _reset(self, _match):
        self.ai.clear()
        return "Conversation cleared, sir."

    # ---------- SYSTEM ----------

    def _system_status(self, _match):
        decision, reason = authorize("system_status")
        if decision != Decision.ALLOW:
            return reason

        if psutil is None:
            free_gb = shutil.disk_usage(Path.home()).free / 1e9
            return (
                f"Running on {platform.system()} {platform.release()}. "
                f"{free_gb:.1f} GB free on your home drive, sir. "
                "Install psutil for CPU, memory and battery details."
            )

        cpu = psutil.cpu_percent(interval=0.3)
        memory = psutil.virtual_memory()
        parts = [
            f"CPU at {cpu:.0f} percent",
            f"memory at {memory.percent:.0f} percent ({memory.available / 1e9:.1f} GB free)",
        ]
        battery = psutil.sensors_battery()
        if battery is not None:
            status = "plugged in" if battery.power_plugged else "on battery"
            parts.append(f"battery at {battery.percent:.0f} percent, {status}")
        return "Status: " + "; ".join(parts) + ", sir."

    # ---------- CALCULATOR AND CONVERTER ----------

    def _calculate(self, match):
        decision, reason = authorize("calculate")
        if decision != Decision.ALLOW:
            return reason

        expression = match.group("expression").strip()
        try:
            result = safe_eval(expression)
        except (ValueError, SyntaxError, ZeroDivisionError, OverflowError, TypeError):
            return "I couldn't calculate that expression, sir."

        if isinstance(result, float):
            text = f"{result:.10g}"
        else:
            text = f"{result:,}"
        return f"The answer is {text}, sir."

    def _convert(self, match):
        decision, reason = authorize("convert_units")
        if decision != Decision.ALLOW:
            return reason

        unit_from = UNIT_ALIASES.get(match.group("unit_from").lower())
        unit_to = UNIT_ALIASES.get(match.group("unit_to").lower())
        conversion = CONVERSIONS.get((unit_from, unit_to))
        if conversion is None:
            return "I can't convert between those units yet, sir."

        try:
            amount = float(match.group("amount"))
        except ValueError:
            return "I didn't catch that amount, sir."

        result = conversion(amount)
        return f"{amount:g} {match.group('unit_from')} is {result:.2f} {match.group('unit_to')}, sir."

    # ---------- TIMERS ----------

    def _start_timer(self, seconds, label):
        with self._timer_lock:
            self._timer_counter += 1
            timer_id = self._timer_counter

            def finish():
                with self._timer_lock:
                    self._timers.pop(timer_id, None)
                message = f"Time's up, sir: {label}." if label else "Your timer has finished, sir."
                self.notify(message)

            timer = threading.Timer(seconds, finish)
            timer.daemon = True
            self._timers[timer_id] = {
                "timer": timer,
                "label": label,
                "due": time.monotonic() + seconds,
            }
            timer.start()
        return timer_id

    def _set_timer(self, match):
        decision, reason = authorize("set_timer")
        if decision != Decision.ALLOW:
            return reason

        try:
            amount = float(match.group("amount"))
        except ValueError:
            return "I didn't catch the duration, sir."

        unit = TIMER_UNITS.get(match.group("unit").lower())
        if unit is None or amount <= 0:
            return "I didn't understand that duration, sir. Try 'set timer for 10 minutes'."

        seconds = min(amount * unit, MAX_TIMER_SECONDS)
        label = (match.groupdict().get("label") or "").strip()
        self._start_timer(seconds, label)
        return f"Timer set for {_describe_seconds(seconds)}, sir."

    def _list_timers(self, _match):
        with self._timer_lock:
            items = list(self._timers.values())

        if not items:
            return "You have no timers running, sir."

        now = time.monotonic()
        lines = [
            f"{item['label'] or 'timer'}: {_describe_seconds(max(0, item['due'] - now))} left"
            for item in items
        ]
        return "Active timers: " + "; ".join(lines) + ", sir."

    def _cancel_timers(self, _match):
        decision, reason = authorize("cancel_timer")
        if decision != Decision.ALLOW:
            return reason

        with self._timer_lock:
            for item in self._timers.values():
                item["timer"].cancel()
            count = len(self._timers)
            self._timers.clear()

        return f"Cancelled {count} timer(s), sir." if count else "There were no timers to cancel, sir."

    # ---------- NOTES (kept in memory for this session) ----------

    def _add_note(self, match):
        decision, reason = authorize("manage_notes")
        if decision != Decision.ALLOW:
            return reason

        self._notes.append(match.group("text").strip())
        return f"Noted, sir. You have {len(self._notes)} note(s)."

    def _show_notes(self, _match):
        if not self._notes:
            return "You have no notes, sir."
        return "Your notes: " + " | ".join(
            f"{number}. {note}" for number, note in enumerate(self._notes, 1)
        ) + "."

    def _clear_notes(self, _match):
        decision, reason = authorize("manage_notes")
        if decision != Decision.ALLOW:
            return reason

        self._notes.clear()
        return "Notes cleared, sir."

    # ---------- AI TASKS ----------

    def _ai_task(self, template_key, **fields):
        decision, reason = authorize("answer_question")
        if decision != Decision.ALLOW:
            return reason
        prompt = TASK_TEMPLATES[template_key].format(**fields)
        return self.ai.ask(prompt, remember=False)

    def _summarise(self, match):
        return self._ai_task("summarise", text=match.group("text"))

    def _formal(self, match):
        return self._ai_task("formal", text=match.group("text"))

    def _explain_error(self, match):
        return self._ai_task("explain_error", text=match.group("text"))

    def _translate(self, match):
        return self._ai_task(
            "translate",
            language=match.group("language"),
            text=match.group("text"),
        )

    # ---------- WEB ----------

    def _find_brave(self):
        import os
        candidates = [
            os.path.join(os.environ.get("PROGRAMFILES", ""), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        ]
        return next((path for path in candidates if os.path.isfile(path)), None)

    def open_brave(self, url=None):
        if url is None:
            decision, reason = authorize("open_approved_app", target="brave")
        else:
            if not _is_safe_https(url):
                return "That web address isn't permitted, sir."
            decision, reason = authorize("open_approved_website", target=url)

        if decision != Decision.ALLOW:
            return reason

        try:
            if self._brave:
                subprocess.Popen([self._brave] + ([url] if url else []))
                return "Opening Brave, sir."
            if url:
                webbrowser.open(url)
                return "I couldn't find Brave, sir, so I've opened the page in your default browser."
            return "I couldn't find Brave, sir. Please check that it is installed."
        except OSError:
            return "I couldn't launch the browser, sir."

    def _browse(self, url, success_message):
        result = self.open_brave(url)
        return success_message if result == "Opening Brave, sir." else result

    def open_website(self, name):
        name = name.strip().lower()

        if name in WEBSITES:
            return self.open_brave(WEBSITES[name])

        if re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z]{2,}", name):
            if name.rsplit(".", 1)[-1] not in FILE_EXTENSIONS:
                return self.open_brave("https://" + name)

        return None

    def _open_website_command(self, match):
        name = match.group("name").strip()
        result = self.open_website(name)
        return result or "I don't recognise that website shortcut, sir. Try a domain such as example.com."

    def _search_web(self, match):
        query = match.group("query").strip()
        decision, reason = authorize("search_web", target=query)
        if decision != Decision.ALLOW:
            return reason
        url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
        return self._browse(url, f"Searching the web for {query}, sir.")

    def _search_youtube(self, match):
        query = match.group("query").strip()
        decision, reason = authorize("search_youtube", target=query)
        if decision != Decision.ALLOW:
            return reason
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
        return self._browse(url, f"Searching YouTube for {query}, sir.")

    def _search_wikipedia(self, match):
        query = match.group("query").strip()
        decision, reason = authorize("search_web", target=query)
        if decision != Decision.ALLOW:
            return reason
        url = "https://en.wikipedia.org/w/index.php?search=" + urllib.parse.quote_plus(query)
        return self._browse(url, f"Searching Wikipedia for {query}, sir.")

    # ---------- OPENING APPS AND FOLDERS ----------

    def open_app(self, name):
        if name not in APPS:
            return None

        decision, reason = authorize("open_approved_app", target=name)
        if decision != Decision.ALLOW:
            return reason

        kind, target = APPS[name]
        try:
            if kind == "exe":
                subprocess.Popen([target])
            elif kind == "uri":
                import os
                os.startfile(target)
            elif kind == "cmd":
                path = shutil.which(target)
                if path is None:
                    return f"I couldn't find {name.title()} on this computer, sir."
                subprocess.Popen(
                    [path],
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            return f"Opening {name.title()}, sir."
        except OSError:
            return f"I couldn't open {name.title()}, sir."

    def _resolve_folder(self, name):
        if name == "project":
            return PROJECT_DIR

        home = Path.home()
        # Many Windows laptops keep Desktop and Documents inside OneDrive.
        for base in (home / "OneDrive", home):
            candidate = base / FOLDERS[name]
            if candidate.is_dir():
                return candidate
        return None

    def open_folder(self, name):
        if name not in FOLDERS:
            return None

        folder = self._resolve_folder(name)
        if folder is None:
            return f"I couldn't find your {name} folder, sir."

        decision, reason = authorize("open_approved_folder", target=str(folder))
        if decision != Decision.ALLOW:
            return reason

        try:
            import os
            os.startfile(str(folder))
            return f"Opening your {name} folder, sir."
        except OSError:
            return f"I couldn't open your {name} folder, sir."

    def _open_name(self, match):
        name = match.group("name").strip().rstrip(".!?").lower()

        if name in ("brave", "brave browser"):
            return self.open_brave()

        for result in (self.open_app(name), self.open_folder(name), self.open_website(name)):
            if result is not None:
                return result

        return None  # Not a shortcut: let the AI answer, e.g. "start learning Python".


if __name__ == "__main__":
    # Keyboard test without the GUI: py -3.10 brain.py
    jarvis = JarvisBrain()

    print("J.A.R.V.I.S. BRAIN TEST")
    print("Type 'help' for commands or 'exit' to quit.")

    while jarvis.running:
        try:
            user_command = input("\nYou: ")
            print(f"JARVIS: {jarvis.respond(user_command)}")
        except (KeyboardInterrupt, EOFError):
            print("\nJARVIS: Until next time, sir.")
            break