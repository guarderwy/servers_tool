"""仪表盘/环形进度控件"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QPainter, QPen, QColor, QFont, QConicalGradient

import math


class MetricGauge(QWidget):
    """环形进度仪表盘"""

    def __init__(self, title: str = "", unit: str = "%",
                 min_value: float = 0, max_value: float = 100,
                 parent=None):
        super().__init__(parent)
        self._title = title
        self._unit = unit
        self._min = min_value
        self._max = max_value
        self._value = 0
        self.setMinimumSize(120, 140)
        self.setMaximumSize(200, 220)

    def set_value(self, value: float):
        self._value = max(self._min, min(self._max, value))
        self.update()

    def _get_color(self) -> QColor:
        if self._value >= 90:
            return QColor("#e74c3c")
        elif self._value >= 80:
            return QColor("#f39c12")
        return QColor("#2ecc71")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        size = min(w, h - 30)
        margin = 10

        # 绘制背景环
        rect = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
        pen_bg = QPen(QColor("#3a3a4a"), 8)
        pen_bg.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_bg)

        start_angle = 225 * 16  # 角度 * 16（Qt 单位）
        span_angle = -270 * 16
        painter.drawArc(rect, start_angle, span_angle)

        # 绘制进度环
        ratio = (self._value - self._min) / (self._max - self._min) if self._max > self._min else 0
        color = self._get_color()
        pen_fg = QPen(color, 8)
        pen_fg.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_fg)
        painter.drawArc(rect, start_angle, int(span_angle * ratio))

        # 绘制数值文字
        painter.setPen(color)
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        painter.setFont(font)
        value_text = f"{self._value:.1f}{self._unit}"
        text_rect = QRectF(margin, size * 0.35, size - 2 * margin, size * 0.3)
        painter.drawText(text_rect, Qt.AlignCenter, value_text)

        # 绘制标题
        painter.setPen(QColor("#cccccc"))
        font2 = QFont()
        font2.setPointSize(10)
        painter.setFont(font2)
        title_rect = QRectF(0, h - 30, w, 25)
        painter.drawText(title_rect, Qt.AlignCenter, self._title)
