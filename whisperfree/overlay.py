"""Modern overlay indicators for WhisperFree."""

from __future__ import annotations

import time
from typing import Optional

from PyQt6 import QtCore, QtGui, QtWidgets


class OverlayWindow(QtWidgets.QWidget):
    """Frameless always-on-top overlay that expands on hover."""

    COLLAPSED_HEIGHT = 6.0
    EXPANDED_HEIGHT = 74.0
    BASELINE_OFFSET = 24
    SCREEN_MARGIN = 28
    FIXED_WIDTH = 360

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.Tool
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)

        self.setFixedHeight(int(self.EXPANDED_HEIGHT + self.BASELINE_OFFSET))
        self.setFixedWidth(self.FIXED_WIDTH)

        self._visual_height = self.COLLAPSED_HEIGHT
        self._height_animation = QtCore.QPropertyAnimation(self, b"visualHeight", self)
        self._height_animation.setDuration(220)
        self._height_animation.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self._height_timer: Optional[QtCore.QTimer] = None

        self._state = "idle"
        self._expanded = False
        self._recording_start: Optional[float] = None
        self._elapsed_text = "00:00"

        self._elapsed_timer = QtCore.QTimer(self)
        self._elapsed_timer.setInterval(500)
        self._elapsed_timer.timeout.connect(self._update_elapsed)

        self._toast_label = QtWidgets.QLabel("", self)
        self._toast_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._toast_label.setStyleSheet(
            "color: white; background-color: rgba(20, 20, 20, 180);"
            "border-radius: 8px; padding: 6px; font-size: 12px;"
        )
        self._toast_label.hide()
        self._toast_timer = QtCore.QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._toast_label.hide)

        self._update_dimensions()

    # ------------------------------------------------------------------ Qt events

    def enterEvent(self, event: QtCore.QEvent) -> None:
        self._set_expanded(True)
        super().enterEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        if self._state != "hidden":
            self._set_expanded(False)
        super().leaveEvent(event)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._position_toast()

    # ------------------------------------------------------------------ public API

    def show_idle(self) -> None:
        self._state = "idle"
        self._recording_start = None
        self._elapsed_text = "00:00"
        self._elapsed_timer.stop()
        self._set_expanded(False)
        self._height_animation.stop()
        self.setVisualHeight(self.COLLAPSED_HEIGHT)
        self._update_dimensions()
        self.update()
        self.show()

    def show_recording(self) -> None:
        self._state = "recording"
        self._recording_start = time.monotonic()
        self._elapsed_timer.start()
        self._update_elapsed()
        self._update_dimensions()
        self.show()

    def hide_overlay(self) -> None:
        self._state = "hidden"
        self._elapsed_timer.stop()
        self.hide()

    def update_level(self, value: float) -> None:  # pragma: no cover - kept for compatibility
        _ = value

    def ingest_waveform(self, payload: object) -> None:  # pragma: no cover - kept for compatibility
        _ = payload

    def show_toast(self, message: str, timeout_ms: int = 2500) -> None:
        """Display a transient message atop the overlay."""
        self._toast_label.setText(message)
        self._toast_label.adjustSize()
        max_width = self.width() - 40
        self._toast_label.setFixedWidth(min(max_width, self._toast_label.width() + 20))
        self._position_toast()
        self._toast_label.show()
        self._toast_timer.start(timeout_ms)

    # ------------------------------------------------------------------ animation helpers

    def _set_expanded(self, expanded: bool) -> None:
        if self._expanded == expanded:
            return
        self._expanded = expanded
        target = self.EXPANDED_HEIGHT if expanded else self.COLLAPSED_HEIGHT
        self._start_height_animation(target, 220, QtCore.QEasingCurve.Type.InOutCubic)

    def _start_height_animation(
        self,
        target: float,
        duration_ms: int,
        easing: QtCore.QEasingCurve.Type,
    ) -> None:
        self._height_animation.stop()
        self._height_animation.setStartValue(self._visual_height)
        self._height_animation.setEndValue(target)
        self._height_animation.setDuration(duration_ms)
        self._height_animation.setEasingCurve(easing)
        self._height_animation.start()

    # ------------------------------------------------------------------ rendering

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: D401
        _ = event
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        pill_rect = QtCore.QRectF(
            0.0,
            self.height() - self.BASELINE_OFFSET - self._visual_height,
            float(self.width()),
            self._visual_height,
        )

        if self._visual_height <= self.COLLAPSED_HEIGHT + 0.5:
            color = QtGui.QColor("#C9CCD1") if self._state != "recording" else QtGui.QColor("#FF453A")
            line_height = max(2.0, self._visual_height)
            top_offset = (pill_rect.height() - line_height) / 2.0
            line_rect = pill_rect.adjusted(20.0, top_offset, -20.0, -top_offset)
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(line_rect, line_height / 2.0, line_height / 2.0)
            return

        if self._visual_height < self.EXPANDED_HEIGHT - 0.5:
            # Render just the pill during the animation, defer content until expanded.
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(QtGui.QColor(0, 0, 0, 220))
            painter.drawRoundedRect(pill_rect, pill_rect.height() / 2.0, pill_rect.height() / 2.0)
            return

        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor(0, 0, 0, 220))
        painter.drawRoundedRect(pill_rect, pill_rect.height() / 2.0, pill_rect.height() / 2.0)

        content_rect = pill_rect.adjusted(24.0, 0.0, -24.0, 0.0)
        centre_y = pill_rect.center().y()

        indicator_radius = 5.5
        indicator_color = QtGui.QColor("#FF453A") if self._state == "recording" else QtGui.QColor("#80838A")
        indicator_center = QtCore.QPointF(content_rect.left() + indicator_radius, centre_y)
        painter.setBrush(indicator_color)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawEllipse(indicator_center, indicator_radius, indicator_radius)

        timer_font = QtGui.QFont()
        timer_font.setPointSizeF(11.0)
        timer_font.setBold(True)
        painter.setFont(timer_font)
        painter.setPen(indicator_color)
        timer_height = 18.0
        timer_rect = QtCore.QRectF(
            indicator_center.x() + indicator_radius + 6.0,
            centre_y - timer_height / 2.0,
            70.0,
            timer_height,
        )
        timer_text = self._elapsed_text if self._state == "recording" else "00:00"
        painter.drawText(timer_rect, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter, timer_text)

        status_font = QtGui.QFont()
        status_font.setPointSizeF(14.0)
        status_font.setBold(True)
        painter.setFont(status_font)
        painter.setPen(QtGui.QColor("#FFFFFF"))
        status_text = "Recording" if self._state == "recording" else "Ctrl+Win to Record"
        status_height = 24.0
        status_rect = QtCore.QRectF(
            timer_rect.right() + 12.0,
            centre_y - status_height / 2.0,
            content_rect.width() - timer_rect.width() - 120.0,
            status_height,
        )
        painter.drawText(status_rect, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter, status_text)

        button_radius = min(20.0, pill_rect.height() / 2.5)
        button_center = QtCore.QPointF(pill_rect.right() - 32.0, pill_rect.center().y())
        outer_rect = QtCore.QRectF(
            button_center.x() - button_radius,
            button_center.y() - button_radius,
            button_radius * 2,
            button_radius * 2,
        )
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.setPen(QtGui.QPen(QtGui.QColor("#FFFFFF"), 2))
        painter.drawEllipse(outer_rect)

        inner_padding = button_radius * 0.55
        inner_rect = outer_rect.adjusted(inner_padding, inner_padding, -inner_padding, -inner_padding)
        painter.setBrush(QtGui.QColor("#FF453A") if self._state == "recording" else QtGui.QColor("#3A3A3C"))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawRoundedRect(inner_rect, 4.0, 4.0)

    # ------------------------------------------------------------------ helpers

    def _update_dimensions(self) -> None:
        screen = QtGui.QGuiApplication.primaryScreen()
        if not screen:
            return
        geometry = screen.availableGeometry()
        width = min(self.FIXED_WIDTH, int(geometry.width() * 0.6))
        if width != self.width():
            self.setFixedWidth(width)
        x = geometry.center().x() - self.width() // 2
        y = geometry.bottom() - self.SCREEN_MARGIN - (self.height() - self.BASELINE_OFFSET)
        self.move(x, y)

    def _position_toast(self) -> None:
        if not self._toast_label.isHidden():
            self._toast_label.move(
                (self.width() - self._toast_label.width()) // 2,
                max(
                    8,
                    int(self.height() - self.BASELINE_OFFSET - self._visual_height - self._toast_label.height() - 12),
                ),
            )

    def _update_elapsed(self) -> None:
        if self._recording_start is None:
            self._elapsed_text = "00:00"
            return
        elapsed = max(0.0, time.monotonic() - self._recording_start)
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        self._elapsed_text = f"{minutes:02d}:{seconds:02d}"
        self.update()

    # ------------------------------------------------------------------ Qt property

    def getVisualHeight(self) -> float:
        return self._visual_height

    def setVisualHeight(self, value: float) -> None:
        clamped = max(self.COLLAPSED_HEIGHT, min(self.EXPANDED_HEIGHT, float(value)))
        if abs(self._visual_height - clamped) > 0.25:
            self._visual_height = clamped
            self._position_toast()
            self.update()
        else:
            self._visual_height = clamped
            self._position_toast()
            self.update()

    visualHeight = QtCore.pyqtProperty(float, fget=getVisualHeight, fset=setVisualHeight)
