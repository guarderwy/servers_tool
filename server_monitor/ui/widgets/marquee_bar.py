"""顶部滚动告警栏（跑马灯）

只滚动「活跃」告警信息；告警恢复后自动从滚动内容中移除。

行为约定（按用户要求）：
- 仅在「所有告警内容的总长度超过滚动栏宽度」时才滚动；否则静止显示。
- 相同的预警（内容相同）只显示一条（按文本去重）。

实现说明：
- 不再依赖 QScrollArea 的 horizontalScrollBar().setValue() —— 在
  ScrollBarAlwaysOff 且内容宽度尚未参与布局计算时，滚动条 maximum() 为 0，
  导致 setValue 被钳制到 0、永远滚不动。
- 改用「容器 QWidget + 子 QLabel 平移」方案：定时器每帧把 _label 往左 move 一个步长，
  越过单份文本宽度后归零，形成无缝循环。该方案不依赖滚动条几何，稳定可滚动。
"""

from PyQt5.QtWidgets import QWidget, QLabel
from PyQt5.QtCore import Qt, QTimer

from ...core.models import AlertRecord


class MarqueeBar(QWidget):
    """顶部滚动告警栏 —— 只滚动活跃告警"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setStyleSheet(
            "background-color: #2a2a3a; border-bottom: 1px solid #3a3a4a;"
        )

        self._label = QLabel("", self)
        self._label.setWordWrap(False)
        self._label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._label.setStyleSheet(
            "color: #2ecc71; font-weight: bold; padding: 0 8px;"
        )

        self._sep = "        "          # 单份之间的间隔
        self._offset = 0                 # 当前左移像素
        self._step = 2                   # 每帧像素（越小越平滑）
        self._text = ""                  # 去重后的告警内容（单份，不含循环复制）
        self._unit_w = 0                 # 单份内容 + 间隔的像素宽度（循环周期）
        self._parts = []                 # 去重后的活跃告警文本片段（非空即表示有活跃告警）
        self._has_critical = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        self.set_alerts([])  # 初始占位

    def set_alerts(self, alerts: list[AlertRecord]):
        """根据告警列表刷新滚动内容（只取活跃告警，且相同预警去重）"""
        active = [a for a in alerts if not a.is_resolved]

        if not active:
            self._parts = []
            self._text = "● 当前无活跃告警"
            self._label.setStyleSheet(
                "color: #2ecc71; font-weight: bold; padding: 0 8px;"
            )
            self._label.setText(self._text)
            self._label.adjustSize()
            self._unit_w = self._label.width()
            self._offset = 0
            self._label.move(0, self._vcenter())
            self._timer.stop()
            return

        # 去重：相同内容的预警只保留一条
        seen = set()
        self._parts = []
        self._has_critical = False
        for a in active:
            lvl = "严重" if a.level.value == "critical" else "警告"
            msg = f"● [{lvl}] {a.message}"
            if msg in seen:
                continue
            seen.add(msg)
            self._parts.append(msg)
            if a.level.value == "critical":
                self._has_critical = True
        self._text = self._sep.join(self._parts)

        self._rebuild()

        # 仅在「内容超过滚动栏宽度（需要滚动）」时才启动定时器
        if self._unit_w > self.width() and not self._timer.isActive():
            self._timer.start(30)

    def _rebuild(self):
        """按当前窗口宽度重建滚动内容（滚动条件 + 无缝循环份数）"""
        color = "#e74c3c" if self._has_critical else "#f39c12"
        self._label.setStyleSheet(
            f"color: {color}; font-weight: bold; padding: 0 8px;"
        )
        unit = self._text + self._sep
        self._unit_w = self._label.fontMetrics().width(unit)

        # 仅在「所有内容长度超过滚动栏宽度」时才滚动
        if self._unit_w <= self.width():
            self._label.setText(self._text)
            self._label.adjustSize()
            self._offset = 0
            self._label.move(0, self._vcenter())
            self._timer.stop()
            return

        # 需要复制足够份数，使总宽 > 容器宽，保证滚动中画面始终填满、且无缝
        need = max(2, (self.width() + self._unit_w - 1) // max(1, self._unit_w) + 2)
        loop_text = self._sep.join([self._text] * need)
        self._label.setText(loop_text)
        self._label.adjustSize()

        self._offset = 0
        self._label.move(0, self._vcenter())

    def _vcenter(self) -> int:
        """竖直居中 label"""
        return max(0, (self.height() - self._label.height()) // 2)

    def _tick(self):
        if not self._parts:
            return
        # 内容没超过宽度 -> 不滚动，静止显示
        if self._unit_w <= self.width():
            return
        self._offset -= self._step
        if self._offset <= -self._unit_w:
            self._offset = 0
        self._label.move(self._offset, self._vcenter())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._parts:
            # 宽度变化后按新宽度重建（重新判定是否滚动 / 份数 / 居中）
            self._rebuild()
        else:
            self._label.move(0, self._vcenter())
