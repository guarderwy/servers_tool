"""指标曲线图组件 —— 基于 pyqtgraph 的实时滚动曲线"""

import pyqtgraph as pg
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QButtonGroup
from PyQt5.QtCore import Qt
from collections import deque
from datetime import datetime

from ...config import CHART_MAX_POINTS


class TimeAxisItem(pg.AxisItem):
    """自定义 X 轴，将 Unix 时间戳格式化为 HH:MM:SS"""

    def tickStrings(self, values, scale, spacing):
        return [datetime.fromtimestamp(v).strftime("%H:%M:%S") for v in values]


class MetricChart(QWidget):
    """实时指标曲线图，支持多条线叠加和时间窗口切换"""

    TIME_WINDOWS = [
        ("1min", 60),
        ("5min", 300),
        ("15min", 900),
    ]

    def __init__(self, title: str = "", y_label: str = "%",
                 max_points: int = CHART_MAX_POINTS, parent=None):
        super().__init__(parent)
        self._title = title
        self._max_points = max_points
        self._current_window = self.TIME_WINDOWS[0][1]  # 默认 1min

        # 数据线存储：{name: deque of (timestamp, value)}
        self._series: dict[str, deque] = {}
        self._curves: dict[str, pg.PlotDataItem] = {}

        self._setup_ui(y_label)

    def _setup_ui(self, y_label: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # 标题行
        header = QHBoxLayout()
        title_label = QLabel(f"<b>{self._title}</b>")
        header.addWidget(title_label)
        header.addStretch()

        self._value_label = QLabel("--")
        self._value_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2ecc71;")
        header.addWidget(self._value_label)
        layout.addLayout(header)

        # 图表
        pg.setConfigOptions(antialias=True)
        self._plot_widget = pg.PlotWidget(axisItems={'bottom': TimeAxisItem(orientation='bottom')})
        self._plot_widget.setBackground("#1e1e2e")
        self._plot_widget.showGrid(x=False, y=True, alpha=0.3)
        self._plot_widget.setLabel("left", y_label)
        self._plot_widget.setMouseEnabled(x=False, y=False)
        self._plot_widget.setMinimumHeight(150)
        layout.addWidget(self._plot_widget)

        # 时间窗口按钮
        btn_row = QHBoxLayout()
        self._btn_group = QButtonGroup()
        for i, (label, seconds) in enumerate(self.TIME_WINDOWS):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(24)
            btn.setFixedWidth(60)
            if i == 0:
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, s=seconds: self._set_window(s))
            self._btn_group.addButton(btn)
            btn_row.addWidget(btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _set_window(self, seconds: int):
        self._current_window = seconds
        self._redraw()

    def add_series(self, name: str, color: str = "#2ecc71"):
        """添加一条数据线"""
        self._series[name] = deque(maxlen=self._max_points)
        pen = pg.mkPen(color=color, width=2)
        curve = self._plot_widget.plot(pen=pen, name=name)
        self._curves[name] = curve

    def append_data(self, name: str, timestamp: float, value: float):
        """追加数据点"""
        if name not in self._series:
            self.add_series(name)
        self._series[name].append((timestamp, value))

        # 更新最新值显示
        if self._series[name]:
            latest = self._series[name][-1][1]
            self._value_label.setText(f"{latest:.1f}")
            # 根据值变色
            if latest >= 90:
                self._value_label.setStyleSheet(
                    "font-size: 16px; font-weight: bold; color: #e74c3c;"
                )
            elif latest >= 80:
                self._value_label.setStyleSheet(
                    "font-size: 16px; font-weight: bold; color: #f39c12;"
                )
            else:
                self._value_label.setStyleSheet(
                    "font-size: 16px; font-weight: bold; color: #2ecc71;"
                )

        self._redraw()

    def _redraw(self):
        """重绘图表"""
        now = None
        for name, data in self._series.items():
            if not data:
                continue
            if now is None:
                now = data[-1][0]
            cutoff = now - self._current_window
            points = [(t, v) for t, v in data if t >= cutoff]
            if points:
                times = [p[0] for p in points]
                values = [p[1] for p in points]
                if name in self._curves:
                    self._curves[name].setData(times, values)

        # 调整 X 轴范围
        if now:
            self._plot_widget.setXRange(
                now - self._current_window, now, padding=0
            )

    def clear(self):
        """清空所有数据"""
        for name in self._series:
            self._series[name].clear()
            if name in self._curves:
                self._curves[name].setData([], [])
        self._value_label.setText("--")
