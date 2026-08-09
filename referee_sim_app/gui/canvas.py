"""裁判系统 UI 图形画布（1920x1080 官方坐标系）。"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from ..protocol.ui_graphics import Figure

WIDTH = 1920
HEIGHT = 1080

COLOR_RGB = {
    0: (0, 200, 255),    # 己方主色（模拟红色方用红，蓝色方用蓝；此处用青色以示区分）
    1: (255, 255, 0),    # 黄色
    2: (0, 255, 0),      # 绿色
    3: (255, 165, 0),    # 橙色
    4: (178, 34, 34),    # 紫红色
    5: (255, 105, 180),  # 粉色
    6: (0, 255, 255),    # 青色
    7: (0, 0, 0),        # 黑色
    8: (255, 255, 255),  # 白色
}


class RefereeCanvas(QWidget):
    """按官方屏幕坐标系（左下角原点）绘制 0x0301 图形。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._figures: dict[str, Figure] = {}
        self._chars: dict[str, tuple[Figure, str]] = {}
        self.setMinimumSize(480, 270)
        self.setStyleSheet("background:#101418;")

    def reset(self) -> None:
        self._figures.clear()
        self._chars.clear()
        self.update()

    def apply_figure(self, fig: Figure, char_text: str | None = None) -> None:
        key = fig.name_str or f"fig{len(self._figures)}"
        if fig.operate == 3:
            self._figures.pop(key, None)
            self._chars.pop(key, None)
        else:
            if fig.figure_type == 7:
                self._chars[key] = (fig, char_text or "")
                self._figures.pop(key, None)
            else:
                self._figures[key] = fig
                self._chars.pop(key, None)
        self.update()

    def apply_delete(self, delete_type: int, layer: int) -> None:
        if delete_type == 0:
            return
        if delete_type == 2:
            self.reset()
            return
        for key in list(self._figures):
            if self._figures[key].layer == layer:
                self._figures.pop(key, None)
        for key in list(self._chars):
            if self._chars[key][0].layer == layer:
                self._chars.pop(key, None)
        self.update()

    def _scale(self, x: float, y: float) -> QPointF:
        w, h = self.width(), self.height()
        scale = min(w / WIDTH, h / HEIGHT)
        ox = (w - WIDTH * scale) / 2
        oy = (h - HEIGHT * scale) / 2
        return QPointF(ox + x * scale, oy + (HEIGHT - y) * scale)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        scale = min(w / WIDTH, h / HEIGHT)
        ox = (w - WIDTH * scale) / 2
        oy = (h - HEIGHT * scale) / 2
        painter.fillRect(self.rect(), QColor(0x10, 0x14, 0x18))
        painter.setPen(QPen(QColor(60, 70, 80), 1))
        painter.drawRect(QRectF(ox, oy, WIDTH * scale, HEIGHT * scale))

        def pen_for(fig: Figure) -> QPen:
            r, g, b = COLOR_RGB.get(fig.color, (255, 255, 255))
            return QPen(QColor(r, g, b), max(1, round(fig.width * scale)))

        for fig in self._figures.values():
            p = pen_for(fig)
            painter.setPen(p)
            s = self._scale(fig.start_x, fig.start_y)
            if fig.figure_type == 0:      # 直线
                e = self._scale(fig.details_d, fig.details_e)
                painter.drawLine(s, e)
            elif fig.figure_type == 1:    # 矩形
                e = self._scale(fig.details_d, fig.details_e)
                painter.drawRect(QRectF(s, e).normalized())
            elif fig.figure_type == 2:    # 正圆
                r = fig.details_c * scale
                painter.drawEllipse(s, r, r)
            elif fig.figure_type == 3:    # 椭圆
                rx = fig.details_d * scale
                ry = fig.details_e * scale
                painter.drawEllipse(s, rx, ry)
            elif fig.figure_type == 4:    # 圆弧（0°=12点方向，顺时针；Qt 角度逆时针 y 向下）
                rx = fig.details_d * scale
                ry = fig.details_e * scale
                rect = QRectF(s.x() - rx, s.y() - ry, 2 * rx, 2 * ry)
                start = 16 * ((90 - fig.details_a) % 360)
                span = -16 * ((fig.details_b - fig.details_a) % 360)
                painter.drawArc(rect, start, span)
            elif fig.figure_type in (5, 6):  # 浮点数/整型数
                font = QFont("Consolas", max(8, round(fig.details_a * scale)))
                painter.setFont(font)
                text = f"{fig.float_value}" if fig.figure_type == 5 else f"{fig.int_value}"
                painter.drawText(QPointF(s.x(), s.y()), text)

        painter.setPen(QPen(QColor(255, 255, 255), 1))
        for key, (fig, text) in self._chars.items():
            font = QFont("Microsoft YaHei", max(8, round(fig.details_a * scale)))
            painter.setFont(font)
            painter.setPen(pen_for(fig))
            s = self._scale(fig.start_x, fig.start_y)
            painter.drawText(QPointF(s.x(), s.y()), text)
