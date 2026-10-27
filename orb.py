"""
JARVIS orb: a frameless animated core that reflects JARVIS's state.

Thread-safe: call orb.request_state("Thinking") from any thread.
"""

import json
import math
import random
import sys
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction, QBrush, QColor, QConicalGradient, QFont,
    QPainter, QPen, QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QMenu, QWidget


# ---------- SETTINGS ----------

ORB_SIZE = 240
FRAME_MS = 33                     # about 30 fps; lower CPU use than 16 ms
EDGE_MARGIN = 40                  # distance from the screen's right edge
BOTTOM_MARGIN = 60                # distance above the bottom of the work area
DEFAULT_ANCHOR = "bottom_right"   # or "bottom_centre"
POSITION_FILE = Path(__file__).resolve().parent / "orb_settings.json"

STATE_MOTION = {"Idle": 1.0, "Listening": 1.12, "Thinking": 1.06, "Speaking": 1.16}
STATE_SPIN = {"Idle": 1.0, "Listening": 1.8, "Thinking": 3.0, "Speaking": 1.4}
EASE = 0.08                       # how quickly size and spin move toward the target

# Ring rotation in degrees per phase unit. Negative values turn the other way.
RING_SPEEDS = (6.0, -4.0)


class JarvisOrb(QWidget):
    STATES = tuple(STATE_MOTION)

    # Emitting this from any thread is safe; Qt delivers it on the GUI thread.
    state_requested = Signal(str)

    def __init__(self):
        super().__init__()

        self.setWindowTitle("JARVIS Orb")
        self.setFixedSize(ORB_SIZE, ORB_SIZE)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool          # no taskbar button
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.cx = self.cy = ORB_SIZE / 2
        self.state = "Idle"
        self.anchor = DEFAULT_ANCHOR
        self.phase = 0.0
        self.motion = 1.0             # current size factor, eased toward the state's target
        self.spin = 1.0               # current speed factor, eased toward the state's target
        self.drag_offset = None

        rng = random.Random()
        self.particles = [
            (
                rng.uniform(0, math.tau),
                rng.uniform(65, 104),
                rng.uniform(0.5, 1.8),
                rng.uniform(1.0, 2.6),
            )
            for _ in range(48)
        ]

        # Gradients that don't change are built once.
        self._glow = self._build_glow()
        self._rings = [
            # (radius, pen width, rotation speed, gradient)
            (77, 3.0, RING_SPEEDS[0], self._build_ring_gradient()),
            (91, 1.6, RING_SPEEDS[1], self._build_ring_gradient()),
        ]
        self._label_font = QFont("Consolas", 8)

        self.state_requested.connect(self.set_state)

        self._load_settings()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(FRAME_MS)

    # ---------- PUBLIC API ----------

    def request_state(self, state):
        """Thread-safe. Call this from JARVIS's worker or timer threads."""
        self.state_requested.emit(state)

    def set_state(self, state):
        if state in STATE_MOTION:
            self.state = state

    # ---------- GRADIENTS ----------

    def _build_glow(self):
        glow = QRadialGradient(self.cx, self.cy, 112)
        glow.setColorAt(0.0, QColor(0, 180, 255, 34))
        glow.setColorAt(0.48, QColor(105, 35, 255, 18))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        return glow

    def _build_ring_gradient(self):
        # Centred on the origin, because paintEvent translates to the orb centre
        # and rotates the painter. The gradient itself never needs a custom angle.
        gradient = QConicalGradient(0, 0, 0)
        gradient.setColorAt(0.0, QColor(0, 225, 255, 0))
        gradient.setColorAt(0.18, QColor(0, 225, 255, 220))
        gradient.setColorAt(0.42, QColor(145, 55, 255, 200))
        gradient.setColorAt(0.68, QColor(0, 125, 255, 30))
        gradient.setColorAt(0.85, QColor(0, 225, 255, 230))
        gradient.setColorAt(1.0, QColor(0, 225, 255, 0))
        return gradient

    # ---------- ANIMATION ----------

    def animate(self):
        self.motion += (STATE_MOTION[self.state] - self.motion) * EASE
        self.spin += (STATE_SPIN[self.state] - self.spin) * EASE
        self.phase = (self.phase + 0.025 * self.spin) % math.tau
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)

        t = self.phase
        radius = 53 * (1 + 0.025 * math.sin(t * 2)) * self.motion

        # Soft outer glow
        p.setBrush(QBrush(self._glow))
        p.drawEllipse(int(self.cx - 112), int(self.cy - 112), 224, 224)

        # Rotating broken energy rings: translate once, then rotate the painter.
        p.save()
        p.translate(self.cx, self.cy)
        for ring_radius, width, speed, gradient in self._rings:
            p.save()
            p.rotate(math.degrees(t * speed))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QBrush(gradient), width))
            p.drawArc(
                -ring_radius, -ring_radius, ring_radius * 2, ring_radius * 2,
                18 * 16, 286 * 16,
            )
            p.restore()
        p.restore()

        # Orbiting particles
        p.setPen(Qt.PenStyle.NoPen)
        orbit_speed = 0.7 * self.spin * 3
        for angle, distance, speed, size in self.particles:
            a = angle + t * speed * orbit_speed
            x = self.cx + math.cos(a) * distance
            y = self.cy + math.sin(a) * distance * 0.57
            alpha = int(100 + 130 * (0.5 + 0.5 * math.sin(a * 2 + t)))
            p.setBrush(QColor(70, 205, 255, alpha))
            p.drawEllipse(int(x), int(y), max(1, int(size)), max(1, int(size)))

        # Event horizon: dark centre, bright thin rim
        horizon = QRadialGradient(self.cx, self.cy, radius + 12)
        horizon.setColorAt(0.0, QColor(0, 0, 0, 255))
        horizon.setColorAt(0.76, QColor(1, 2, 12, 255))
        horizon.setColorAt(0.88, QColor(5, 8, 25, 255))
        horizon.setColorAt(0.94, QColor(0, 205, 255, 230))
        horizon.setColorAt(1.0, QColor(130, 45, 255, 0))
        p.setBrush(QBrush(horizon))
        p.drawEllipse(
            int(self.cx - radius - 12), int(self.cy - radius - 12),
            int((radius + 12) * 2), int((radius + 12) * 2),
        )

        # Status label
        p.setFont(self._label_font)
        p.setPen(QColor(195, 225, 255, 220))
        p.drawText(
            0, ORB_SIZE - 29, ORB_SIZE, 20,
            Qt.AlignmentFlag.AlignCenter,
            f"J.A.R.V.I.S.  \u2022  {self.state.upper()}",
        )
        p.end()

    # ---------- POSITION ----------

    def _work_area(self, point=None):
        screen = None
        if point is not None:
            screen = QApplication.screenAt(point)
        if screen is None:
            screen = QApplication.primaryScreen()
        return screen.availableGeometry()

    def _default_position(self, area):
        if self.anchor == "bottom_centre":
            x = area.center().x() - ORB_SIZE // 2
        else:
            x = area.right() - ORB_SIZE - EDGE_MARGIN
        y = area.bottom() - ORB_SIZE - BOTTOM_MARGIN
        return QPoint(x, y)

    def _clamp_to(self, point, area):
        x = min(max(point.x(), area.left()), area.right() - ORB_SIZE)
        y = min(max(point.y(), area.top()), area.bottom() - ORB_SIZE)
        return QPoint(x, y)

    def _load_settings(self):
        position = None
        try:
            data = json.loads(POSITION_FILE.read_text(encoding="utf-8"))
            self.anchor = data.get("anchor", DEFAULT_ANCHOR)
            if self.anchor not in ("bottom_right", "bottom_centre"):
                self.anchor = DEFAULT_ANCHOR
            position = QPoint(int(data["x"]), int(data["y"]))
        except (OSError, ValueError, KeyError, TypeError):
            pass  # no saved settings yet, or the file is unreadable

        if position is None:
            position = self._default_position(self._work_area())
        else:
            position = self._clamp_to(position, self._work_area(position))
        self.move(position)

    def _save_settings(self):
        data = {"x": self.x(), "y": self.y(), "anchor": self.anchor}
        try:
            POSITION_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass  # not fatal: the orb still works, it just won't remember its place

    def reset_position(self):
        self.move(self._default_position(self._work_area()))
        self._save_settings()

    def set_anchor(self, anchor):
        self.anchor = anchor
        self.reset_position()

    # ---------- MOUSE ----------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            press_global = event.globalPosition().toPoint()
            self.drag_offset = press_global - self.frameGeometry().topLeft()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.show_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            target = event.globalPosition().toPoint() - self.drag_offset
            self.move(self._clamp_to(target, self._work_area(target)))

    def mouseReleaseEvent(self, event):
        if self.drag_offset is not None:
            self.drag_offset = None
            self._save_settings()

    # ---------- MENU ----------

    def show_menu(self, position):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #10121d;
                color: #e8f5ff;
                border: 1px solid #34425e;
                padding: 6px;
            }
            QMenu::item { padding: 7px 24px; }
            QMenu::item:selected { background: #173b58; }
        """)

        state_menu = menu.addMenu("Set visual state")
        for state in self.STATES:
            action = state_menu.addAction(state)
            action.triggered.connect(lambda checked=False, s=state: self.set_state(s))

        position_menu = menu.addMenu("Position")
        for label, anchor in (("Bottom right", "bottom_right"), ("Bottom centre", "bottom_centre")):
            action = QAction(label, position_menu)
            action.setCheckable(True)
            action.setChecked(self.anchor == anchor)
            action.triggered.connect(lambda checked=False, a=anchor: self.set_anchor(a))
            position_menu.addAction(action)
        position_menu.addSeparator()
        position_menu.addAction("Reset position").triggered.connect(self.reset_position)

        menu.addSeparator()
        menu.addAction("Exit JARVIS Orb").triggered.connect(QApplication.quit)
        menu.exec(position)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    orb = JarvisOrb()
    orb.show()
    sys.exit(app.exec())