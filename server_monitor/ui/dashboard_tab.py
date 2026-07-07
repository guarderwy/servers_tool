"""仪表盘 Tab —— 总览卡片/列表双模式"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QScrollArea, QGridLayout, QSplitter,
)
from PyQt5.QtCore import Qt, pyqtSignal

from .widgets.server_card import ServerCard
from .widgets.server_list_table import ServerListTable
from ..core.state_manager import StateManager
from ..core.models import ServerSnapshot, ServerStatus
from ..utils.humanize import humanize_bytes_per_sec


class DashboardTab(QWidget):
    """仪表盘 Tab：支持卡片视图和列表视图双模式切换"""

    monitoring_state_changed = pyqtSignal()

    def __init__(self, state_manager: StateManager, scheduler=None, parent=None):
        super().__init__(parent)
        self._state = state_manager
        self._scheduler = scheduler
        self._mode = "card"  # card | list
        self._theme = "dark"
        self._cards: dict[str, ServerCard] = {}
        self._last_update_time = None
        self._batch_mode = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 标题栏
        header = QHBoxLayout()
        self._title_label = QLabel("<b>服务器总览</b>")
        header.addWidget(self._title_label)
        header.addStretch()

        self._switch_btn = QPushButton("切换列表视图")
        self._switch_btn.setFixedWidth(120)
        self._switch_btn.clicked.connect(self._toggle_mode)
        header.addWidget(self._switch_btn)
        layout.addLayout(header)

        # 统计栏
        stats_row = QHBoxLayout()
        self._online_label = QLabel("在线: 0/0")
        stats_row.addWidget(self._online_label)

        self._alert_label = QLabel("告警: 0")
        stats_row.addWidget(self._alert_label)

        self._update_label = QLabel("最后更新: --")
        stats_row.addWidget(self._update_label)
        stats_row.addStretch()
        layout.addLayout(stats_row)

        # 堆叠切换
        self._stack = QStackedWidget()
        layout.addWidget(self._stack, 1)

        # 卡片视图
        card_scroll = QScrollArea()
        card_scroll.setWidgetResizable(True)
        card_scroll.setStyleSheet("QScrollArea { border: none; }")
        self._card_container = QWidget()
        self._card_grid = QGridLayout(self._card_container)
        self._card_grid.setSpacing(12)
        card_scroll.setWidget(self._card_container)
        self._stack.addWidget(card_scroll)

        # 列表视图
        self._list_table = ServerListTable(self._state, scheduler=self._scheduler)
        self._list_table.monitor_toggled.connect(self._on_list_monitor_toggled)
        self._stack.addWidget(self._list_table)

    def _toggle_mode(self):
        if self._mode == "card":
            self._mode = "list"
            self._stack.setCurrentIndex(1)
            self._switch_btn.setText("切换卡片视图")
        else:
            self._mode = "card"
            self._stack.setCurrentIndex(0)
            self._switch_btn.setText("切换列表视图")

    def update_snapshot(self, snapshot: ServerSnapshot):
        """更新单台服务器的快照"""
        cfg = self._state.get_config(snapshot.server_id)
        if not cfg:
            return

        # 更新或创建卡片
        card = self._cards.get(snapshot.server_id)
        if not card:
            card = ServerCard(theme=self._theme)
            self._cards[snapshot.server_id] = card
            # 连接监控切换信号 → 调度器
            if self._scheduler:
                card.monitoring_toggled.connect(self._on_card_monitor_toggle)
            if not self._batch_mode:
                self._rebuild_grid()

        card.update_snapshot(snapshot, cfg)

        # 更新监控状态显示
        if self._scheduler:
            card.set_monitoring_state(self._scheduler.is_running(snapshot.server_id))

        # 记录最新采集时间
        self._last_update_time = snapshot.timestamp

        # 更新统计
        self._update_stats()

    def apply_theme(self, theme: str):
        """切换仪表盘所有视觉元素到指定主题"""
        self._theme = theme
        # 标题栏
        fg = "#ffffff" if theme == "dark" else "#222222"
        self._title_label.setStyleSheet(f"font-size: 16px; color: {fg};")
        # 更新所有已有卡片
        for card in self._cards.values():
            card.set_card_theme(theme)
        # 统计栏文字颜色（暗色下不变，亮色下加深）
        online_fg = "#2ecc71"
        alert_fg = "#f39c12"
        update_fg = "#888888" if theme == "dark" else "#666666"
        self._online_label.setStyleSheet(f"color: {online_fg}; font-size: 13px;")
        self._alert_label.setStyleSheet(f"color: {alert_fg}; font-size: 13px;")
        self._update_label.setStyleSheet(f"color: {update_fg}; font-size: 12px;")

    def _rebuild_grid(self):
        """重建卡片网格"""
        # 清除现有卡片
        while self._card_grid.count():
            item = self._card_grid.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        # 重新添加
        cols = 4
        for i, (sid, card) in enumerate(self._cards.items()):
            row = i // cols
            col = i % cols
            self._card_grid.addWidget(card, row, col)

    def _update_stats(self):
        total = self._state.get_total_count()
        online = self._state.get_online_count()
        alerts = self._state.get_alert_count()

        self._online_label.setText(f"在线: {online}/{total}")
        self._alert_label.setText(f"告警: {alerts}")

        if self._last_update_time:
            self._update_label.setText(
                f"最后更新: {self._last_update_time.strftime('%H:%M:%S')}"
            )
        else:
            self._update_label.setText("最后更新: --")

    def _on_card_monitor_toggle(self, server_id: str, start: bool):
        """卡片监控切换按钮回调"""
        if not self._scheduler:
            return
        if start:
            self._scheduler.start(server_id)
        else:
            self._scheduler.stop(server_id)
        # 刷新所有卡片的监控状态
        self.refresh_monitoring_state()
        self.monitoring_state_changed.emit()

    def _on_list_monitor_toggled(self, server_id: str, start: bool):
        """列表视图监控列切换"""
        self.monitoring_state_changed.emit()

    def refresh_monitoring_state(self):
        """刷新所有卡片的监控状态显示"""
        if not self._scheduler:
            return
        for sid, card in self._cards.items():
            card.set_monitoring_state(self._scheduler.is_running(sid))

    def full_refresh(self):
        """全量刷新（批量模式：先更新所有卡片，最后重建一次网格）"""
        self._batch_mode = True
        for snap in self._state.get_all_snapshots():
            self.update_snapshot(snap)
        self._batch_mode = False
        self._rebuild_grid()
        self.refresh_monitoring_state()
        self._list_table.refresh()

    def get_list_table(self) -> ServerListTable:
        return self._list_table
