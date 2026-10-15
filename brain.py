
import ast
import datetime
import json
import operator
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from safeguards import authorize, Decision


class JarvisBrain:
    def __init__(self):
        self.name = "JARVIS"
        self.running = True

        # Local AI powered by Ollama
        self.ollama_url = "http://127.0.0.1:11434/api/chat"
        self.model = "qwen2.5:3b"

        self.messages = [
            {
                "role": "system",
                "content": (
                    "You are JARVIS, a personal desktop assistant. "
                    "Speak in concise, polished British English. "
                    "Address the user as sir occasionally, not every time. "
                    "Be friendly, intelligent, and direct. "
                    "Never claim to have performed a computer action "
                    "unless a real Python function performed it. "
                    "You cannot execute arbitrary system commands."
                ),
            }
        ]

        # Safe arithmetic operators
        self.operators = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.FloorDiv: operator.floordiv,
            ast.Mod: operator.mod,
            ast.Pow: operator.pow,
        }

        # Website shortcuts
        self.websites = {
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

        # Desktop application shortcuts
        self.apps = {
            "notepad": ["notepad.exe"],
            "calculator": ["calc.exe"],
            "paint": ["mspaint.exe"],
            "task manager": ["taskmgr.exe"],
            "file explorer": ["explorer.exe"],
            "explorer": ["explorer.exe"],
            "settings": ["explorer.exe", "ms-settings:"],
        }

        # Common folders
        self.folders = {
            "desktop": "Desktop",
            "downloads": "Downloads",
            "documents": "Documents",
            "pictures": "Pictures",
            "music": "Music",
            "videos": "Videos",
        }

    # --------------------------------------------------
    # SAFE CALCULATOR
    # --------------------------------------------------

    def calculate(self, expression):
        def evaluate(node):
            if isinstance(node, ast.Constant):
                if type(node.value) in (int, float):
                    return node.value
                raise ValueError("Invalid number")

            if isinstance(node, ast.BinOp):
                operation = self.operators.get(type(node.op))

                if operation is None:
                    raise ValueError("Unsupported operation")

                left = evaluate(node.left)
                right = evaluate(node.right)

                if isinstance(node.op, ast.Pow) and abs(right) > 10:
                    raise ValueError("Exponent too large")

                if abs(left) > 1e100 or abs(right) > 1e100:
                    raise ValueError("Number too large")

                result = operation(left, right)

                if isinstance(result, complex):
                    raise ValueError("Complex results unsupported")

                return result

            if isinstance(node, ast.UnaryOp):
                if isinstance(node.op, ast.USub):
                    return -evaluate(node.operand)

                if isinstance(node.op, ast.UAdd):
                    return evaluate(node.operand)

            raise ValueError("Invalid expression")

        tree = ast.parse(expression, mode="eval")
        return evaluate(tree.body)

    # --------------------------------------------------
    # BROWSER CONTROL
    # --------------------------------------------------

    def find_brave(self):
        candidates = [
            os.path.join(
                os.environ.get("PROGRAMFILES", ""),
                "BraveSoftware",
                "Brave-Browser",
                "Application",
                "brave.exe",
            ),
            os.path.join(
                os.environ.get("PROGRAMFILES(X86)", ""),
                "BraveSoftware",
                "Brave-Browser",
                "Application",
                "brave.exe",
            ),
            os.path.join(
                os.environ.get("LOCALAPPDATA", ""),
                "BraveSoftware",
                "Brave-Browser",
                "Application",
                "brave.exe",
            ),
        ]

        for path in candidates:
            if os.path.isfile(path):
                return path

        return None

    
    def open_brave(self, url=None):
        # Opening a browser or a URL is an explicit, allowlisted action.
        if url is None:
            decision, reason = authorize(
                "open_approved_app", target="brave"
            )
        else:
            try:
                parsed = urllib.parse.urlparse(url)
                valid_url = (
                    parsed.scheme == "https"
                    and bool(parsed.hostname)
                    and parsed.username is None
                    and parsed.password is None
                )
            except (TypeError, ValueError):
                valid_url = False

            if not valid_url:
                return "That URL is not permitted, sir."

            decision, reason = authorize(
                "open_approved_website", target=url
            )

        if decision != Decision.ALLOW:
            return reason

        brave = self.find_brave()

        try:
            if brave:
                args = [brave]
                if url:
                    args.append(url)

                subprocess.Popen(args)
                return "Opening Brave, sir."

            if url:
                webbrowser.open(url)
                return (
                    "I couldn't locate Brave, sir. "
                    "I've opened the page in your default browser instead."
                )

            return (
                "I couldn't locate Brave, sir. "
                "Please check that it is installed."
            )

        except OSError:
            return "I couldn't launch the browser, sir."

    def open_website(self, name):
        name = name.strip().lower()

        if name in self.websites:
            return self.open_brave(self.websites[name])

        # Accept a domain such as example.com.
        if (
            "." in name
            and " " not in name
            and "/" not in name
            and "\\" not in name
        ):
            url = "https://" + name
            return self.open_brave(url)

        return None

    def search_web(self, query):
        query = query.strip()

        if not query:
            return "What would you like me to search for, sir?"

        decision, reason = authorize("search_web", target=query)
        if decision != Decision.ALLOW:
            return reason

        url = (
            "https://www.google.com/search?q="
            + urllib.parse.quote_plus(query)
        )

        result = self.open_brave(url)

        if result.startswith("Opening Brave"):
            return f"Searching the web for {query}, sir."

        return result

    def search_youtube(self, query):
        query = query.strip()

        if not query:
            return "What would you like me to search for, sir?"

        decision, reason = authorize("search_youtube", target=query)
        if decision != Decision.ALLOW:
            return reason

        url = (
            "https://www.youtube.com/results?search_query="
            + urllib.parse.quote_plus(query)
        )

        result = self.open_brave(url)

        if result.startswith("Opening Brave"):
            return f"Searching YouTube for {query}, sir."

        return result

    # --------------------------------------------------
    # DESKTOP APPLICATIONS
    # --------------------------------------------------

    def open_app(self, name):
        name = name.strip().lower()

        if name not in self.apps:
            return None

        decision, reason = authorize(
            "open_approved_app", target=name
        )
        if decision != Decision.ALLOW:
            return reason

        try:
            subprocess.Popen(self.apps[name])
            return f"Opening {name.title()}, sir."
        except OSError:
            return f"I couldn't open {name.title()}, sir."

    def open_folder(self, name):
        name = name.strip().lower()

        if name not in self.folders:
            return None

        folder_path = os.path.join(
            os.path.expanduser("~"),
            self.folders[name],
        )

        decision, reason = authorize(
            "open_approved_folder", target=folder_path
        )
        if decision != Decision.ALLOW:
            return reason

        if not os.path.isdir(folder_path):
            return f"I couldn't find your {name} folder, sir."

        try:
            os.startfile(folder_path)
            return f"Opening your {name} folder, sir."
        except OSError:
            return f"I couldn't open your {name} folder, sir."

    # --------------------------------------------------
    # LOCAL AI
    # --------------------------------------------------

    def ask_ai(self, command):
        # Preserve the system prompt and recent conversation.
        self.messages.append({
            "role": "user",
            "content": command,
        })

        self.messages = [
            self.messages[0]
        ] + self.messages[-10:]

        payload = {
            "model": self.model,
            "messages": self.messages,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_ctx": 4096,
            },
        }

        request = urllib.request.Request(
            self.ollama_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request, timeout=120
            ) as response:
                result = json.loads(
                    response.read().decode("utf-8")
                )

            answer = (
                result.get("message", {})
                .get("content", "")
                .strip()
            )

            if not answer:
                return "I couldn't generate a response, sir."

            self.messages.append({
                "role": "assistant",
                "content": answer,
            })

            return answer

        except urllib.error.HTTPError as error:
            if error.code == 404:
                return (
                    "My local AI model wasn't found, sir. "
                    "Check that qwen2.5:3b is installed in Ollama."
                )

            return (
                f"My local AI returned error {error.code}, sir."
            )

        except urllib.error.URLError:
            return (
                "I can't connect to my local AI brain, sir. "
                "Please ensure Ollama is running."
            )

        except TimeoutError:
            return "My response timed out, sir. Please try again."

        except Exception:
            return "I encountered an unexpected error while thinking, sir."

    # --------------------------------------------------
    # MAIN COMMAND ROUTER
    # --------------------------------------------------

    def respond(self, command):
        original = command.strip()
        command = original.lower()

        if not command:
            return "I'm listening, sir."

        blocked_request_phrases = (
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
        if any(phrase in command for phrase in blocked_request_phrases):
            decision, _reason = authorize("execute_arbitrary_command")
            if decision == Decision.BLOCK:
                return (
                    "I can't perform that action, sir. "
                    "It is blocked by JARVIS's security policy."
                )

        # Shutdown
        if command in (
            "exit",
            "quit",
            "shutdown jarvis",
            "go offline",
        ):
            self.running = False
            return "Until next time, sir."

        # Greetings
        if command in (
            "hello",
            "hi",
            "hey",
            "hello jarvis",
            "hey jarvis",
        ):
            return "Hello, sir. All systems are operational."

        # Identity
        if "your name" in command or "who are you" in command:
            return "I am JARVIS, your personal desktop assistant."

        # Time
        if command in (
            "time",
            "what time is it",
            "tell me the time",
        ):
            current_time = datetime.datetime.now().strftime(
                "%I:%M %p"
            )
            return f"The current time is {current_time}, sir."

        # Date
        if command in (
            "date",
            "what is today's date",
            "what's today's date",
            "what day is it",
        ):
            today = datetime.datetime.now().strftime(
                "%A, %d %B %Y"
            )
            return f"Today is {today}, sir."

        # Help
        if command in (
            "help",
            "what can you do",
            "show commands",
            "list commands",
        ):
            return (
                "I can open Brave and websites, search YouTube "
                "and Google, launch supported desktop apps, open "
                "common folders, tell the time and date, calculate "
                "arithmetic, and answer questions using my local AI. "
                "Say 'open calculator' or 'search YouTube for music' "
                "to get started."
            )

        # Calculator
        if command.startswith("calculate "):
            expression = original[len("calculate "):].strip()

            try:
                result = self.calculate(expression)
                return f"The answer is {result}, sir."
            except (
                ValueError,
                SyntaxError,
                ZeroDivisionError,
                OverflowError,
            ):
                return "I couldn't calculate that expression, sir."

        # YouTube searches
        youtube_prefixes = (
            "search youtube for ",
            "search youtube ",
            "youtube search ",
            "find on youtube ",
        )

        for prefix in youtube_prefixes:
            if command.startswith(prefix):
                query = original[len(prefix):].strip()
                return self.search_youtube(query)

        # General web searches
        search_prefixes = (
            "search the web for ",
            "search google for ",
            "google search ",
            "search for ",
            "look up ",
        )

        for prefix in search_prefixes:
            if command.startswith(prefix):
                query = original[len(prefix):].strip()
                return self.search_web(query)

        # Browser commands
        if command in (
            "open brave",
            "launch brave",
            "start brave",
        ):
            return self.open_brave()

        if command in (
            "open youtube",
            "launch youtube",
        ):
            return self.open_brave(
                "https://www.youtube.com"
            )

        if command in (
            "open google",
            "launch google",
        ):
            return self.open_brave(
                "https://www.google.com"
            )

        if command.startswith("open website "):
            name = original[len("open website "):].strip()
            result = self.open_website(name)

            if result:
                return result

            return (
                "I don't recognise that website shortcut, sir. "
                "Try a domain such as example.com."
            )

        # Website shortcuts: "open GitHub", "open Spotify", etc.
        if command.startswith("open "):
            name = command[len("open "):].strip()

            # Apps and folders take priority over websites.
            app_result = self.open_app(name)
            if app_result:
                return app_result

            folder_result = self.open_folder(name)
            if folder_result:
                return folder_result

            website_result = self.open_website(name)
            if website_result:
                return website_result

        # Explicit desktop app commands
        for prefix in ("launch ", "start "):
            if command.startswith(prefix):
                name = command[len(prefix):].strip()
                app_result = self.open_app(name)

                if app_result:
                    return app_result

        # Let the local AI answer other questions.
        return self.ask_ai(original)


if __name__ == "__main__":
    # Optional standalone keyboard test:
    # Run with: py -3.10 brain.py
    jarvis = JarvisBrain()

    print("J.A.R.V.I.S. BRAIN TEST")
    print("Type 'help' for commands or 'exit' to quit.")

    while jarvis.running:
        try:
            user_command = input("\nYou: ")
            response = jarvis.respond(user_command)
            print(f"JARVIS: {response}")
        except (KeyboardInterrupt, EOFError):
            print("\nJARVIS: Until next time, sir.")
            break
