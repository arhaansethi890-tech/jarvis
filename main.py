
# pythonw.exe has no console streams. Keep status prints harmless when JARVIS
# starts quietly in the system tray.
import os
import sys

_null_output = None
if sys.stdout is None or sys.stderr is None:
    _null_output = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = _null_output
    if sys.stderr is None:
        sys.stderr = _null_output

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

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

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


def build_tray_icon():
    """Draw a compact JARVIS mark without adding an image dependency."""
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#101522"))
    painter.drawEllipse(1, 1, 30, 30)
    painter.setBrush(QColor("#50DFFF"))
    painter.drawEllipse(5, 5, 22, 22)
    painter.setBrush(QColor("#101522"))
    painter.drawEllipse(9, 9, 14, 14)
    painter.setBrush(QColor("#D9FAFF"))
    painter.drawEllipse(13, 13, 6, 6)
    painter.end()
    return QIcon(pixmap)


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
        self.speech_lock = threading.Lock()
        self.wake_stop = threading.Event()
        self.wake_thread = None
        self.wake_listener_active = False
        self.wake_ready = False
        self.wake_desired = False
        self.wake_error = None
        self.ready_notice_shown = False
        self.jarvis.notify = self.notify_user

        # The orb and Tkinter UI share the main thread. Tk periodically pumps
        # Qt events, avoiding a second GUI thread and keeping orb state updates safe.
        self.orb = JarvisOrb()
        self.orb.exit_requested.connect(self.close_app)
        self.root.after(50, self._pump_qt_events)

        self.mode = tk.StringVar(value="Keyboard + Microphone")

        root.title("J.A.R.V.I.S. | Personal AI")
        root.geometry("1000x700")
        root.minsize(680, 480)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

        # Use a consistent Tk scaling value for crisp, readable text.
        # Windows DPI awareness above handles display scaling where available.
        try:
            root.tk.call("tk", "scaling", 1.25)
        except tk.TclError:
            pass

        self.build_header()
        self.build_chat()
        self.build_controls()
        self.create_tray_icon()

        self.add_message(
            "JARVIS",
            "Systems online, sir. Say ‘Hey Jarvis’ or type a command."
        )

        self.root.after(0, self.start_wake_listener)
        self.update_clock()


    def create_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(build_tray_icon(), self.qt_app)
        self.tray_icon.setToolTip("JARVIS — listening for Hey Jarvis")

        self.tray_menu = QMenu()
        show_action = self.tray_menu.addAction("Open JARVIS")
        show_action.triggered.connect(self.show_window)
        hide_action = self.tray_menu.addAction("Hide to tray")
        hide_action.triggered.connect(self.hide_to_tray)
        self.tray_mic_action = self.tray_menu.addAction("Turn microphone off")
        self.tray_mic_action.triggered.connect(self.toggle_microphone)
        self.tray_voice_action = self.tray_menu.addAction("Turn voice off")
        self.tray_voice_action.triggered.connect(self.toggle_voice)
        self.tray_menu.addSeparator()
        exit_action = self.tray_menu.addAction("Exit JARVIS")
        exit_action.triggered.connect(self.close_app)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()
        self._update_tray_status()

        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.root.after(0, self.show_window)

    def _update_tray_status(self):
        if not hasattr(self, "tray_icon"):
            return
        self.tray_mic_action.setText(
            "Turn microphone off" if self.mic_enabled else "Turn microphone on"
        )
        self.tray_voice_action.setText(
            "Turn voice off" if self.voice_enabled else "Turn voice on"
        )
        if self.wake_error:
            state = "microphone unavailable"
        elif not self.mic_enabled:
            state = "microphone off"
        elif self.mode.get() == "Keyboard Only":
            state = "keyboard-only mode"
        elif self.wake_ready:
            state = "listening for Hey Jarvis"
        else:
            state = "starting voice listener"
        self.tray_icon.setToolTip(f"JARVIS — {state}")

    def _tray_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_window()

    def show_window(self):
        if self.closing:
            return
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.focus_force()

    def hide_to_tray(self):
        if not self.closing:
            self.root.withdraw()

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

        self.apply_mode()

    def change_mode(self, selected=None):
        self.apply_mode()
        if self._should_listen_for_wake_word():
            self.start_wake_listener()
        else:
            self.stop_wake_listener()
        self._update_tray_status()

    def apply_mode(self):
        if self.closing:
            return

        selected = self.mode.get()
        keyboard_allowed = selected in (
            "Keyboard Only",
            "Keyboard + Microphone"
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
        if not self.mic_enabled:
            label = "Microphone disabled"
        elif selected == "Keyboard Only":
            label = "Keyboard ready"
        elif self.wake_error:
            label = "Microphone unavailable"
        elif self.wake_ready:
            label = "Wake word active — say Hey Jarvis"
        elif selected == "Microphone Only":
            label = "Loading voice model..."
        else:
            label = "Loading voice model..."

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

        if self._should_listen_for_wake_word():
            self.start_wake_listener()
        else:
            self.stop_wake_listener()
        self.apply_mode()
        self._update_tray_status()

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
        self._update_tray_status()

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

    # ---------- MICROPHONE / WAKE WORD ----------
    def _should_listen_for_wake_word(self):
        return (
            self.mic_enabled
            and self.mode.get() != "Keyboard Only"
            and not self.closing
        )

    def start_wake_listener(self):
        if not self._should_listen_for_wake_word():
            return

        self.wake_desired = True
        self.wake_stop.clear()
        self.wake_listener_active = True
        self.wake_ready = False
        self.wake_error = None
        self.apply_mode()
        self.status.configure(
            text="● LISTENING" if self.wake_ready else "● LOADING VOICE",
            fg=GREEN if self.wake_ready else YELLOW,
        )
        self.orb.request_hide()
        self._update_tray_status()

        if self.wake_thread is not None and self.wake_thread.is_alive():
            return

        self.wake_thread = threading.Thread(
            target=self._wake_listener_loop,
            daemon=True,
        )
        self.wake_thread.start()

    def stop_wake_listener(self):
        self.wake_desired = False
        self.wake_stop.set()
        self.wake_listener_active = False
        self.wake_ready = False
        if not self.closing:
            self.orb.request_hide()
            self._update_tray_status()
            if not self.busy:
                self.status.configure(text="● ONLINE", fg=GREEN)

    def _wake_phrase_heard(self):
        if not self.closing:
            try:
                self.root.after(0, self.orb.show_session, "I'm listening...")
            except tk.TclError:
                pass

    def _wake_listener_ready(self):
        if self.closing:
            return
        self.wake_ready = True
        try:
            self.root.after(0, self._show_wake_listener_ready)
        except tk.TclError:
            pass

    def _show_wake_listener_ready(self):
        if self.closing:
            return
        self.apply_mode()
        self.orb.request_hide()
        if not self.ready_notice_shown:
            device_name = self.speech_module.get_input_device_name()
            self.add_message(
                "SYSTEM",
                f"Wake-word mic ready: {device_name}. Say ‘Hey Jarvis’ to begin."
            )
            self.tray_icon.showMessage(
                "JARVIS is ready",
                "Say ‘Hey Jarvis’ to start an interaction.",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )
            self.ready_notice_shown = True
        self._update_tray_status()
        if not self.busy:
            self.status.configure(text="● LISTENING", fg=GREEN)

    def _wake_command_received(self, command):
        if self.closing:
            return
        self.add_message("YOU", command)
        self.set_busy("PROCESSING")
        self.orb.request_overlay_text(command)
        self.orb.request_state("Thinking")

    def _wake_listener_failed(self, error):
        if self.closing:
            return
        self.wake_desired = False
        self.wake_ready = False
        self.wake_error = error
        self.add_message("SYSTEM", f"Microphone error: {error}")
        self.status.configure(text="● MICROPHONE ERROR", fg=YELLOW)
        self.orb.request_hide()
        self.tray_icon.showMessage(
            "JARVIS microphone unavailable",
            str(error),
            QSystemTrayIcon.MessageIcon.Warning,
            5000,
        )
        self.apply_mode()
        self._update_tray_status()

    def _wake_listener_stopped(self):
        if self.closing:
            return
        if self.wake_desired and self._should_listen_for_wake_word():
            self.start_wake_listener()
            return
        self.apply_mode()
        if not self.busy:
            if self.wake_error:
                self.status.configure(text="● MICROPHONE ERROR", fg=YELLOW)
            else:
                self.status.configure(text="● ONLINE", fg=GREEN)

    def _wake_listener_loop(self):
        try:
            if self.speech_module is None:
                import speech
                self.speech_module = speech

            if self.closing or self.wake_stop.is_set():
                return

            while (
                self.wake_desired
                and not self.wake_stop.is_set()
            ):
                command = self.speech_module.listen_for_wake_command(
                    self.wake_stop,
                    on_wake=self._wake_phrase_heard,
                    on_activity=self._wake_activity,
                    on_ready=self._wake_listener_ready,
                )
                if self.wake_stop.is_set() or self.closing:
                    break
                if not command:
                    self.root.after(0, self.orb.request_hide)
                    continue
                if self.busy:
                    continue

                self.root.after(0, self._wake_command_received, command)
                self.process_command(command)

        except Exception as error:
            if not self.closing and self.wake_desired:
                self.root.after(0, self._wake_listener_failed, str(error))
        finally:
            self.wake_listener_active = False
            self.wake_ready = False
            if not self.closing:
                self.root.after(0, self._wake_listener_stopped)

    def _wake_activity(self, rms, transcript):
        if self.closing:
            return
        try:
            self.root.after(0, self._show_wake_activity, rms, transcript)
        except tk.TclError:
            pass

    def _show_wake_activity(self, rms, transcript):
        if self.closing or self.busy or not self.wake_listener_active:
            return

        threshold = getattr(self.speech_module, "WAKE_RMS_THRESHOLD", 12)
        if rms < threshold:
            self.status.configure(text="● MIC QUIET", fg=YELLOW)
            self.input_status.configure(text="Mic is quiet; check your input device")
            self.tray_icon.setToolTip("JARVIS — microphone is quiet")
        elif transcript:
            heard = " ".join(transcript.split())[:24]
            self.status.configure(text=f"● HEARD: {heard}", fg=GREEN)
            self.input_status.configure(text="Listening for Hey Jarvis")
            self.tray_icon.setToolTip(f"JARVIS — heard: {heard}")
        else:
            self.status.configure(text="● HEARING AUDIO", fg=GREEN)
            self.input_status.configure(text="Listening for Hey Jarvis")
            self.tray_icon.setToolTip("JARVIS — hearing audio")

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
        if self._should_listen_for_wake_word() and self.wake_listener_active:
            self.status.configure(text="● LISTENING", fg=GREEN)
            self.orb.request_hide()
        else:
            self.status.configure(text="● ONLINE", fg=GREEN)
            self.orb.request_hide()
        self.apply_mode()
        self._update_tray_status()

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

            # Keep the UI busy until speech finishes, so another response
            # cannot compete for the shared audio player.
            self.speak_if_enabled(response)

        except Exception as error:
            if not self.closing:
                self.root.after(
                    0, self.add_message,
                    "SYSTEM", f"Error: {error}"
                )
        finally:
            if not self.closing:
                if self.jarvis.running:
                    self.root.after(0, self.set_ready)
                else:
                    self.wake_desired = False
                    self.wake_stop.set()
                    # Leave the farewell visible briefly after speech completes.
                    self.root.after(
                        0,
                        lambda: self.status.configure(
                            text="● SHUTTING DOWN", fg=YELLOW
                        ),
                    )
                    self.root.after(1200, self.close_app)

    def speak_async(self, message):
        if not self.voice_enabled or self.closing:
            return

        threading.Thread(
            target=self.speak_if_enabled,
            args=(message,),
            daemon=True
        ).start()

    def speak_if_enabled(self, message):
        with self.speech_lock:
            # Check again after waiting for any earlier speech to finish.
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
                    if not self.busy:
                        self.orb.request_hide()

    def notify_user(self, message):
        """Forward timer notifications from worker threads to the GUI."""
        if self.closing:
            return
        try:
            self.root.after(0, self._show_notification, message)
        except tk.TclError:
            pass

    def _show_notification(self, message):
        if self.closing:
            return
        self.add_message("JARVIS", message)
        self.speak_async(message)

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
        self.wake_desired = False
        self.wake_stop.set()
        try:
            if hasattr(self, "tray_icon"):
                self.tray_icon.hide()
            self.orb.close()
            self.qt_app.quit()
        finally:
            self.root.destroy()


if __name__ == "__main__":
    # Create Qt first because the orb is a Qt window. Tk remains the main UI loop;
    # JarvisGUI pumps Qt events on the same thread for smooth orb animation.
    qt_app = QApplication.instance() or QApplication([])
    qt_app.setQuitOnLastWindowClosed(False)
    root = tk.Tk()
    app = JarvisGUI(root, qt_app)
    root.withdraw()
    root.mainloop()
