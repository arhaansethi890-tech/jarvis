
# Enable sharper Windows rendering before creating the Tkinter window.
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

import tkinter as tk
from tkinter import scrolledtext
import threading
import datetime

from PySide6.QtWidgets import QApplication

from brain import JarvisBrain
from orb import JarvisOrb
from speech_output import speak


# ---------- RED JARVIS THEME ----------
BG = "#080808"
PANEL = "#141414"
PANEL2 = "#202020"
RED = "#FF3030"
RED_DARK = "#701010"
WHITE = "#FFFFFF"
GREY = "#C0C0C0"
GREEN = "#55F59B"
YELLOW = "#FFD166"

FONT = "Segoe UI"
MONO = "Cascadia Mono"


class JarvisGUI:
    def __init__(self, root, qt_app):
        self.root = root
        self.qt_app = qt_app
        self.jarvis = JarvisBrain()

        self.closing = False
        self.busy = False
        self.mic_enabled = True
        self.voice_enabled = True
        self.speech_module = None
        self.speaking = threading.Event()

        # The orb and Tkinter UI share the main thread. Tk periodically pumps
        # Qt events, avoiding a second GUI thread and keeping orb state updates safe.
        self.orb = JarvisOrb()
        self.orb.exit_requested.connect(self.close_app)
        # Keep the visual hidden until the user starts a voice interaction.
        self.orb.hide_session()
        self.root.after(10, self._pump_qt_events)

        self.mode = tk.StringVar(value="Keyboard + Microphone")

        root.title("J.A.R.V.I.S. | Personal AI")
        root.geometry("1000x700")
        root.minsize(680, 480)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.close_app)

        # Use a consistent Tk scaling value for crisp, readable text.
        # Windows DPI awareness above handles display scaling where available.
        try:
            root.tk.call("tk", "scaling", 1.25)
        except tk.TclError:
            pass

        self.build_header()
        self.build_chat()
        self.build_controls()

        self.add_message(
            "JARVIS",
            "Systems online, sir. Select an input mode and enter a command."
        )

        self.update_clock()

        # Speak the startup greeting only if voice is enabled.
        self.speak_async("Systems online, sir.")

    # ---------- HEADER ----------
    def build_header(self):
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=20, pady=(16, 6))

        tk.Label(
            header,
            text="J.A.R.V.I.S.",
            font=(FONT, 28, "bold"),
            fg=RED,
            bg=BG
        ).pack(side="left")

        self.status = tk.Label(
            header,
            text="● ONLINE",
            font=(MONO, 11, "bold"),
            fg=GREEN,
            bg=BG
        )
        self.status.pack(side="right", pady=10)

        self.clock = tk.Label(
            self.root,
            text="",
            font=(MONO, 11, "bold"),
            fg=GREY,
            bg=BG
        )
        self.clock.pack(anchor="e", padx=24)

        cards = tk.Frame(self.root, bg=BG)
        cards.pack(fill="x", padx=16, pady=12)

        for title, detail in [
            ("LOCAL AI", "Qwen 2.5 3B"),
            ("VOICE OUTPUT", "Edge TTS"),
            ("INTERFACE", "High-contrast mode"),
        ]:
            card = tk.Frame(
                cards,
                bg=PANEL,
                highlightbackground=RED_DARK,
                highlightthickness=1,
                padx=12,
                pady=11
            )
            card.pack(side="left", fill="x", expand=True, padx=4)

            tk.Label(
                card,
                text=title,
                bg=PANEL,
                fg=RED,
                font=(FONT, 10, "bold")
            ).pack(anchor="w")

            tk.Label(
                card,
                text=detail,
                bg=PANEL,
                fg=WHITE,
                font=(FONT, 11, "bold")
            ).pack(anchor="w", pady=(5, 0))

    # ---------- CHAT ----------
    def build_chat(self):
        frame = tk.Frame(
            self.root,
            bg=RED,
            highlightbackground=RED,
            highlightthickness=1
        )
        frame.pack(
            side="top",
            fill="both",
            expand=True,
            padx=20,
            pady=(0, 10)
        )

        self.chat = scrolledtext.ScrolledText(
            frame,
            wrap=tk.WORD,
            state="disabled",
            font=(MONO, 11),
            bg="#0C0C0C",
            fg=WHITE,
            insertbackground=RED,
            selectbackground=RED_DARK,
            selectforeground=WHITE,
            relief="flat",
            padx=14,
            pady=14,
            borderwidth=0,
            spacing1=3,
            spacing3=7
        )
        self.chat.pack(fill="both", expand=True)

        self.chat.tag_config(
            "user", foreground="#FF7777",
            font=(MONO, 11, "bold")
        )
        self.chat.tag_config(
            "jarvis", foreground="#FF4545",
            font=(MONO, 11, "bold")
        )
        self.chat.tag_config(
            "system", foreground=GREY,
            font=(FONT, 10, "bold")
        )

    def add_message(self, sender, message):
        if self.closing:
            return

        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        if sender == "YOU":
            tag = "user"
        elif sender == "JARVIS":
            tag = "jarvis"
        else:
            tag = "system"

        self.chat.configure(state="normal")
        self.chat.insert(
            tk.END, f"[{timestamp}] {sender}: ", tag
        )
        self.chat.insert(tk.END, f"{message}\n\n")
        self.chat.configure(state="disabled")
        self.chat.see(tk.END)

    # ---------- CONTROLS ----------
    def build_controls(self):
        bottom = tk.Frame(self.root, bg=BG)
        bottom.pack(side="bottom", fill="x", padx=20, pady=(0, 14))

        mode_row = tk.Frame(bottom, bg=BG)
        mode_row.pack(fill="x", pady=(0, 9))

        tk.Label(
            mode_row,
            text="INPUT MODE",
            font=(FONT, 10, "bold"),
            fg=RED,
            bg=BG
        ).pack(side="left", padx=(0, 10))

        self.mode_menu = tk.OptionMenu(
            mode_row,
            self.mode,
            "Keyboard Only",
            "Microphone Only",
            "Keyboard + Microphone",
            command=self.change_mode
        )
        self.mode_menu.configure(
            bg=PANEL2,
            fg=WHITE,
            activebackground=RED_DARK,
            activeforeground=WHITE,
            highlightthickness=1,
            highlightbackground=RED_DARK,
            relief="flat",
            font=(FONT, 10, "bold"),
            width=22
        )
        self.mode_menu["menu"].configure(
            bg=PANEL2,
            fg=WHITE,
            activebackground=RED,
            activeforeground=WHITE,
            font=(FONT, 10)
        )
        self.mode_menu.pack(side="left")

        self.mic_button = tk.Button(
            mode_row,
            text="MIC ON",
            command=self.toggle_microphone,
            bg=RED_DARK,
            fg=WHITE,
            activebackground=RED,
            activeforeground=WHITE,
            relief="flat",
            font=(FONT, 10, "bold"),
            padx=13,
            pady=6
        )
        self.mic_button.pack(side="left", padx=8)

        self.voice_button = tk.Button(
            mode_row,
            text="VOICE ON",
            command=self.toggle_voice,
            bg="#292929",
            fg=GREEN,
            activebackground="#3A3A3A",
            activeforeground=WHITE,
            relief="flat",
            font=(FONT, 10, "bold"),
            padx=13,
            pady=6
        )
        self.voice_button.pack(side="left", padx=2)

        self.input_status = tk.Label(
            mode_row,
            text="Keyboard ready",
            fg=GREY,
            bg=BG,
            font=(FONT, 10, "bold")
        )
        self.input_status.pack(side="right")

        entry_row = tk.Frame(bottom, bg=BG)
        entry_row.pack(fill="x")

        self.entry = tk.Entry(
            entry_row,
            font=(FONT, 13),
            bg=PANEL,
            fg=WHITE,
            insertbackground=RED,
            relief="flat",
            disabledbackground="#101010",
            disabledforeground=GREY,
            highlightthickness=1,
            highlightbackground="#555555",
            highlightcolor=RED
        )
        self.entry.pack(
            side="left",
            fill="x",
            expand=True,
            ipady=12,
            padx=(0, 8)
        )
        self.entry.bind(
            "<Return>",
            lambda event: self.send_keyboard()
        )

        self.send_button = tk.Button(
            entry_row,
            text="SEND  ➤",
            command=self.send_keyboard,
            bg=RED_DARK,
            fg=WHITE,
            activebackground=RED,
            activeforeground=WHITE,
            relief="flat",
            font=(FONT, 10, "bold"),
            padx=18,
            pady=10
        )
        self.send_button.pack(side="left", padx=(0, 8))

        self.listen_button = tk.Button(
            entry_row,
            text="SPEAK",
            command=self.send_microphone,
            bg=PANEL2,
            fg=RED,
            activebackground=RED_DARK,
            activeforeground=WHITE,
            relief="flat",
            font=(FONT, 10, "bold"),
            padx=17,
            pady=10
        )
        self.listen_button.pack(side="left")

        self.apply_mode()

    def change_mode(self, selected=None):
        self.apply_mode()

    def apply_mode(self):
        if self.closing:
            return

        selected = self.mode.get()
        keyboard_allowed = selected in (
            "Keyboard Only",
            "Keyboard + Microphone"
        )
        mic_allowed = (
            selected in (
                "Microphone Only",
                "Keyboard + Microphone"
            )
            and self.mic_enabled
        )

        self.entry.configure(
            state="normal" if keyboard_allowed else "disabled"
        )
        self.send_button.configure(
            state=(
                "normal"
                if keyboard_allowed and not self.busy
                else "disabled"
            )
        )
        self.listen_button.configure(
            state=(
                "normal"
                if mic_allowed and not self.busy
                else "disabled"
            )
        )

        if not self.mic_enabled:
            label = "Microphone disabled"
        elif selected == "Keyboard Only":
            label = "Keyboard ready"
        elif selected == "Microphone Only":
            label = "Microphone ready"
        else:
            label = "Both inputs available"

        self.input_status.configure(text=label)

    def toggle_microphone(self):
        if self.busy:
            return

        self.mic_enabled = not self.mic_enabled

        if self.mic_enabled:
            self.mic_button.configure(text="MIC ON", bg=RED_DARK)
            self.add_message("SYSTEM", "Microphone input enabled.")
        else:
            self.mic_button.configure(text="MIC OFF", bg="#292929")
            self.add_message("SYSTEM", "Microphone input disabled.")

        self.apply_mode()

    def toggle_voice(self):
        self.voice_enabled = not self.voice_enabled

        if self.voice_enabled:
            self.voice_button.configure(
                text="VOICE ON", fg=GREEN
            )
            self.add_message("SYSTEM", "Spoken responses enabled.")
        else:
            self.voice_button.configure(
                text="VOICE OFF", fg="#FF7777"
            )
            self.add_message(
                "SYSTEM",
                "Spoken responses disabled. Text replies remain available."
            )

    # ---------- KEYBOARD ----------
    def send_keyboard(self):
        if self.busy or self.mode.get() == "Microphone Only":
            return

        command = self.entry.get().strip()
        if not command:
            return

        self.entry.delete(0, tk.END)
        self.add_message("YOU", command)
        self.set_busy("PROCESSING")

        threading.Thread(
            target=self.process_command,
            args=(command,),
            daemon=True
        ).start()

    # ---------- MICROPHONE ----------
    def send_microphone(self):
        if self.busy or not self.mic_enabled:
            return

        if self.mode.get() == "Keyboard Only":
            return

        self.set_busy("LISTENING")
        self.orb.request_session("Listening… speak now")
        self.add_message(
            "SYSTEM",
            "Recording started. Speak when ready."
        )

        threading.Thread(
            target=self.capture_microphone,
            daemon=True
        ).start()

    def capture_microphone(self):
        try:
            if self.speech_module is None:
                import speech
                self.speech_module = speech

            if self.closing:
                return

            command = self.speech_module.listen()

            if self.closing:
                return

            if not self.mic_enabled:
                self.root.after(0, self.set_ready)
                return

            if not command or not command.strip():
                self.root.after(
                    0, self.add_message,
                    "SYSTEM", "No speech detected. Try again."
                )
                self.root.after(0, self.set_ready)
                self.root.after(0, self.orb.request_overlay_text, "Didn't catch that. Try again.")
                self.root.after(1600, self.orb.request_hide)
                return

            command = command.strip()
            self.root.after(0, self.add_message, "YOU", command)
            self.root.after(0, self.orb.request_overlay_text, f"You said: {command}")
            self.root.after(0, self.set_busy, "PROCESSING")
            self.root.after(0, self.orb.request_state, "Thinking")
            self.process_command(command)

        except Exception as error:
            if not self.closing:
                self.root.after(
                    0, self.add_message,
                    "SYSTEM", f"Microphone error: {error}"
                )
                self.root.after(0, self.set_ready)

    # ---------- AI / VOICE ----------
    def set_busy(self, message):
        self.busy = True
        self.status.configure(text=f"● {message}", fg=YELLOW)
        if message.upper() == "LISTENING":
            self.orb.request_state("Listening")
        else:
            self.orb.request_state("Thinking")
        self.apply_mode()

    def set_ready(self):
        if self.closing:
            return

        self.busy = False
        self.status.configure(text="● ONLINE", fg=GREEN)
        if self.speaking.is_set():
            self.orb.request_state("Speaking")
        else:
            self.orb.request_hide()
        self.apply_mode()

    def process_command(self, command):
        try:
            response = self.jarvis.respond(command)

            if self.closing:
                return

            self.root.after(
                0, self.add_message, "JARVIS", response
            )
            self.root.after(0, self.orb.request_overlay_text, response)
            self.root.after(0, self.orb.request_state, "Thinking")

            self.speak_async(response)

        except Exception as error:
            if not self.closing:
                self.root.after(
                    0, self.add_message,
                    "SYSTEM", f"Error: {error}"
                )
        finally:
            if not self.closing:
                self.root.after(0, self.set_ready)

    def speak_async(self, message):
        if not self.voice_enabled or self.closing:
            return

        threading.Thread(
            target=self.speak_if_enabled,
            args=(message,),
            daemon=True
        ).start()

    def speak_if_enabled(self, message):
        # Check again immediately before speaking.
        if not self.voice_enabled or self.closing:
            return

        self.speaking.set()
        self.orb.request_state("Speaking")
        try:
            speak(message)
        except Exception as error:
            print("Speech output error:", error)
        finally:
            self.speaking.clear()
            if not self.closing:
                # If the AI worker has already finished, return to Idle now.
                # Otherwise set_ready() will return the orb to Idle afterwards.
                if not self.busy:
                    self.orb.request_hide()

    # ---------- QT EVENT PUMP ----------
    def _pump_qt_events(self):
        if self.closing:
            return
        self.qt_app.processEvents()
        if not self.closing:
            self.root.after(10, self._pump_qt_events)

    # ---------- CLOCK / SHUTDOWN ----------
    def update_clock(self):
        if self.closing:
            return

        now = datetime.datetime.now().strftime(
            "%d %b %Y  |  %I:%M:%S %p"
        )
        self.clock.configure(text=now)
        self.root.after(1000, self.update_clock)

    def close_app(self):
        if self.closing:
            return
        self.closing = True
        self.jarvis.running = False
        try:
            self.orb.close()
            self.qt_app.quit()
        finally:
            self.root.destroy()


if __name__ == "__main__":
    # Create Qt first because the orb is a Qt window. Tk remains the main UI loop;
    # JarvisGUI pumps Qt events on the same thread for smooth orb animation.
    qt_app = QApplication.instance() or QApplication([])
    root = tk.Tk()
    app = JarvisGUI(root, qt_app)
    root.mainloop()
