"""小地图画布：0x0305 机器人位置 + 0x0307 路径（28m×15m 场地）。"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..core.visual import FIELD_H, FIELD_W


class MapCanvas(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._positions: list[dict] = []
        self._paths: list[list[tuple[float, float]]] = []
        self.setMinimumSize(480, 260)
        self.setStyleSheet("background:#0b0f14;")

    def reset(self) -> None:
        self._positions.clear()
        self._paths.clear()
        self.update()

    def set_positions(self, positions: list[dict]) -> None:
        self._positions = positions
        self.update()

    def add_path(self, points: list[tuple[float, float]]) -> None:
        if points:
            self._paths.append(points)
            self.update()

    def _point(self, x: float, y: float) -> QPointF:
        w, h = self.width(), self.height()
        scale = min(w / FIELD_W, h / FIELD_H)
        ox = (w - FIELD_W * scale) / 2
        oy = (h - FIELD_H * scale) / 2
        return QPointF(ox + x * scale, oy + (FIELD_H - y) * scale)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(0x0B, 0x0F, 0x14))
        w, h = self.width(), self.height()
        scale = min(w / FIELD_W, h / FIELD_H)
        ox = (w - FIELD_W * scale) / 2
        oy = (h - FIELD_H * scale) / 2

        painter.setPen(QPen(QColor(70, 90, 105), 1))
        painter.drawRect(QRectF(ox, oy, FIELD_W * scale, FIELD_H * scale))
        painter.setPen(QPen(QColor(35, 45, 55), 1))
        for gx in range(1, 8):
            x = ox + gx * 4.0 * scale
            painter.drawLine(QPointF(x, oy), QPointF(x, oy + FIELD_H * scale))
        for gy in range(1, 4):
            y = oy + gy * 5.0 * scale
            painter.drawLine(QPointF(ox, y), QPointF(ox + FIELD_W * scale, y))

        painter.setPen(QPen(QColor(255, 220, 80), 2))
        for path in self._paths:
            pts = [self._point(x, y) for x, y in path]
            for i in range(len(pts) - 1):
                painter.drawLine(pts[i], pts[i + 1])

        font = QFont("Microsoft YaHei", max(7, round(4.2 * scale)))
        for item in self._positions:
            side = item["side"]
            color = QColor(255, 70, 70) if side == "enemy" else QColor(70, 160, 255)
            p = self._point(item["x_m"], item["y_m"])
            r = max(3.0, 0.32 * scale)
            painter.setPen(QPen(color, 1))
            painter.setBrush(color)
            painter.drawEllipse(p, r, r)
            painter.setBrush(Qt.NoBrush)
            painter.setFont(font)
            painter.drawText(QPointF(p.x() + r + 1, p.y() - r - 1), item["label"])
