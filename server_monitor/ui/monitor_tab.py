"""实时监控 Tab —— 服务器列表 + 实时曲线图表"""

import time
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSplitter,
    QScrollArea, QGroupBox,
)
from PyQt5.QtCore import Qt, pyqtSignal

from .widgets.server_list_table import ServerListTable
from .widgets.metric_chart import MetricChart
from .widgets.metric_gauge import MetricGauge
from ..core.state_manager import StateManager
from ..core.models import ServerSnapshot, ServerStatus
from ..utils.humanize import humanize_bytes_per_sec, humanize_mb


class MonitorTab(QWidget):
    """实时监控 Tab"""

    server_selected = pyqtSignal(str)  # server_id

    def __init__(self, state_manager: StateManager, parent=None):
        super().__init__(parent)
        self._state = state_manager
        self._selected_server = ""
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)

        # 左侧：服务器列表
        left = QVBoxLayout()
        left_label = QLabel("<b>服务器列表</b>")
        left_label.setStyleSheet("color: #ffffff;")
        left.addWidget(left_label)

        self._server_list = ServerListTable(state_manager=self._state)
        self._server_list.server_selected.connect(self._on_server_selected)
        left.addWidget(self._server_list, 1)

        left_widget = QWidget()
        left_widget.setLayout(left)
        left_widget.setMaximumWidth(500)

        # 右侧：监控面板
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setStyleSheet("QScrollArea { border: none; }")

        self._monitor_panel = QWidget()
        self._monitor_layout = QVBoxLayout(self._monitor_panel)
        self._monitor_layout.setSpacing(8)

        # 服务器标题
        self._server_title = QLabel("请选择一台服务器")
        self._server_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffffff;")
        self._monitor_layout.addWidget(self._server_title)

        # 仪表盘行
        gauge_row = QHBoxLayout()
        self._cpu_gauge = MetricGauge("CPU", "%")
        self._mem_gauge = MetricGauge("内存", "%")
        self._disk_gauge = MetricGauge("磁盘", "%")
        gauge_row.addWidget(self._cpu_gauge)
        gauge_row.addWidget(self._mem_gauge)
        gauge_row.addWidget(self._disk_gauge)
        gauge_row.addStretch()
        self._monitor_layout.addLayout(gauge_row)

        # CPU 曲线图
        self._cpu_chart = MetricChart("CPU 使用率", "%")
        self._cpu_chart.add_series("total", "#2ecc71")
        self._cpu_chart.add_series("user", "#3498db")
        self._cpu_chart.add_series("system", "#e74c3c")
        self._monitor_layout.addWidget(self._cpu_chart)

        # 内存曲线图
        self._mem_chart = MetricChart("内存使用率", "%")
        self._mem_chart.add_series("usage", "#9b59b6")
        self._monitor_layout.addWidget(self._mem_chart)

        # 磁盘使用率
        self._disk_chart = MetricChart("磁盘使用率", "%")
        self._disk_chart.add_series("max_partition", "#e67e22")
        self._monitor_layout.addWidget(self._disk_chart)

        # 网络流量
        self._net_chart = MetricChart("网络流量", "MB/s")
        self._net_chart.add_series("rx", "#3498db")
        self._net_chart.add_series("tx", "#e74c3c")
        self._monitor_layout.addWidget(self._net_chart)

        # 信息面板
        info_group = QGroupBox("详细信息")
        info_group.setStyleSheet("""
            QGroupBox {
                color: #cccccc;
                border: 1px solid #3a3a4a;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
            }
        """)
        info_layout = QVBoxLayout(info_group)
        self._info_labels = {}
        for key, label_text in [
            ("tcp", "TCP 连接数"),
            ("load", "系统负载"),
            ("mem_detail", "内存详情"),
            ("disk_detail", "磁盘分区"),
        ]:
            lbl = QLabel(f"{label_text}: --")
            lbl.setStyleSheet("color: #aaa; font-size: 12px;")
            self._info_labels[key] = lbl
            info_layout.addWidget(lbl)
        self._monitor_layout.addWidget(info_group)

        self._monitor_layout.addStretch()
        right_scroll.setWidget(self._monitor_panel)

        # 分割器
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_scroll)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

    def _on_server_selected(self, server_id: str):
        self._selected_server = server_id
        cfg = self._state.get_config(server_id)
        if cfg:
            self._server_title.setText(f"{cfg.name} ({cfg.host})")
        # 清空图表
        self._cpu_chart.clear()
        self._mem_chart.clear()
        self._disk_chart.clear()
        self._net_chart.clear()
        self.server_selected.emit(server_id)

    def update_snapshot(self, snapshot: ServerSnapshot):
        """更新快照数据到图表"""
        if snapshot.server_id != self._selected_server:
            return
        if snapshot.status == ServerStatus.OFFLINE:
            return

        ts = time.time()

        # CPU
        if snapshot.cpu:
            cpu = snapshot.cpu
            self._cpu_gauge.set_value(cpu.usage_percent)
            self._cpu_chart.append_data("total", ts, cpu.usage_percent)
            self._cpu_chart.append_data("user", ts, cpu.user_percent)
            self._cpu_chart.append_data("system", ts, cpu.system_percent)

            self._info_labels["load"].setText(
                f"系统负载: {cpu.load_1m:.2f} / {cpu.load_5m:.2f} / {cpu.load_15m:.2f}"
            )

        # 内存
        if snapshot.memory:
            mem = snapshot.memory
            self._mem_gauge.set_value(mem.usage_percent)
            self._mem_chart.append_data("usage", ts, mem.usage_percent)

            self._info_labels["mem_detail"].setText(
                f"内存详情: 总计 {humanize_mb(mem.total_mb)} | "
                f"已用 {humanize_mb(mem.used_mb)} | "
                f"可用 {humanize_mb(mem.available_mb)} | "
                f"缓存 {humanize_mb(mem.cached_mb)}"
            )

        # 磁盘
        if snapshot.disk and snapshot.disk.partitions:
            max_pct = max(p.usage_percent for p in snapshot.disk.partitions)
            self._disk_gauge.set_value(max_pct)
            self._disk_chart.append_data("max_partition", ts, max_pct)

            disk_parts = " | ".join(
                f"{p.mount_point}={p.usage_percent:.0f}%"
                for p in snapshot.disk.partitions
            )
            self._info_labels["disk_detail"].setText(f"磁盘分区: {disk_parts}")

        # 网络
        if snapshot.network and snapshot.network.interfaces:
            # 使用 StateManager 预计算的速率（bytes/sec）
            rx_rate = snapshot.network.rx_rate
            tx_rate = snapshot.network.tx_rate
            self._net_chart.append_data("rx", ts, rx_rate / 1024 / 1024)
            self._net_chart.append_data("tx", ts, tx_rate / 1024 / 1024)

            self._info_labels["tcp"].setText(
                f"TCP 连接: 总计 {snapshot.network.tcp_total} | "
                f"已建立 {snapshot.network.tcp_established}"
            )

    def refresh_list(self):
        self._server_list.refresh()

    def get_selected_server_id(self) -> str:
        return self._selected_server
