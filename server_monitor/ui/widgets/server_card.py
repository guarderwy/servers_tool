"""服务器状态卡片控件"""

from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor

from ...core.models import ServerSnapshot, ServerStatus
from ...utils.humanize import humanize_bytes_per_sec
from ...config import (
    THRESHOLD_WARNING, THRESHOLD_CRITICAL,
    COLOR_NORMAL_BG, COLOR_NORMAL_FG, COLOR_NORMAL_BAR,
    COLOR_WARNING_BG, COLOR_WARNING_FG, COLOR_WARNING_BAR,
    COLOR_CRITICAL_BG, COLOR_CRITICAL_FG, COLOR_CRITICAL_BAR,
    COLOR_OFFLINE_BG, COLOR_OFFLINE_FG,
)


def get_status_color(status: ServerStatus, value=None):
    """根据状态和值返回颜色配置"""
    if status == ServerStatus.OFFLINE:
        return COLOR_OFFLINE_BG, COLOR_OFFLINE_FG
    if value is not None:
        if value >= THRESHOLD_CRITICAL:
            return COLOR_CRITICAL_BG, COLOR_CRITICAL_FG
        if value >= THRESHOLD_WARNING:
            return COLOR_WARNING_BG, COLOR_WARNING_FG
    return COLOR_NORMAL_BG, COLOR_NORMAL_FG


# 进度条基础样式（固定不变，避免每次刷新都拼接到样式字符串末尾导致无限膨胀）
_BAR_BASE_STYLE = """
    QProgressBar {
        border: 1px solid #3a3a4a;
        border-radius: 3px;
        text-align: center;
        background: #1e1e2e;
        font-size: 10px;
        color: #ccc;
    }
    QProgressBar::chunk {
        border-radius: 2px;
    }
"""
_BAR_CHUNK_COLORS = {
    "normal": "#2ecc71",
    "warning": "#f39c12",
    "critical": "#e74c3c",
    "offline": "#7f8c8d",
}


def _bar_style(chunk_color: str) -> str:
    """根据进度条颜色返回完整（基础 + chunk）样式"""
    return _BAR_BASE_STYLE + f"QProgressBar::chunk {{ background-color: {chunk_color}; }}"


class ServerCard(QFrame):
    """单台服务器的状态卡片"""

    clicked = pyqtSignal(str)  # server_id
    monitoring_toggled = pyqtSignal(str, bool)  # server_id, start (True=开始监控, False=停止监控)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._server_id = ""
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumSize(220, 180)
        self.setMaximumSize(280, 220)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            ServerCard {
                background-color: #2a2a3a;
                border: 1px solid #3a3a4a;
                border-radius: 8px;
                padding: 8px;
            }
            ServerCard:hover {
                border: 1px solid #5a5a7a;
            }
        """)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        # 头部：状态 + 主机名 + 监控切换
        header = QHBoxLayout()
        self._status_dot = QLabel("●")
        self._status_dot.setFixedWidth(16)
        self._status_dot.setStyleSheet("color: #7f8c8d;")
        header.addWidget(self._status_dot)

        self._name_label = QLabel("--")
        self._name_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #ffffff;")
        header.addWidget(self._name_label)
        header.addStretch()

        self._monitor_btn = QPushButton("○ 停止")
        self._monitor_btn.setFixedWidth(60)
        self._monitor_btn.setFixedHeight(22)
        self._monitor_btn.setCursor(Qt.PointingHandCursor)
        self._monitor_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid #555;
                border-radius: 3px;
                color: #aaa;
                font-size: 10px;
                padding: 0 4px;
            }
            QPushButton:hover {
                border: 1px solid #888;
                color: #fff;
            }
        """)
        self._monitor_btn.clicked.connect(self._on_monitor_clicked)
        header.addWidget(self._monitor_btn)
        layout.addLayout(header)

        # IP
        self._ip_label = QLabel("--")
        self._ip_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._ip_label)

        # CPU 进度条
        layout.addLayout(self._make_metric_row("CPU", "cpu"))

        # 内存进度条
        layout.addLayout(self._make_metric_row("MEM", "mem"))

        # 磁盘进度条
        layout.addLayout(self._make_metric_row("DISK", "disk"))

        # 网络
        self._net_label = QLabel("-- ↓ -- ↑")
        self._net_label.setStyleSheet("color: #aaa; font-size: 10px;")
        layout.addWidget(self._net_label)

        layout.addStretch()

    def _make_metric_row(self, label_text: str, key: str):
        row = QHBoxLayout()
        lbl = QLabel(f"{label_text}:")
        lbl.setFixedWidth(35)
        lbl.setStyleSheet("color: #aaa; font-size: 11px;")
        row.addWidget(lbl)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(True)
        bar.setFixedHeight(16)
        bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #3a3a4a;
                border-radius: 3px;
                text-align: center;
                background: #1e1e2e;
                font-size: 10px;
                color: #ccc;
            }
            QProgressBar::chunk {
                border-radius: 2px;
            }
        """)
        setattr(self, f"_bar_{key}", bar)
        row.addWidget(bar)
        return row

    def update_snapshot(self, snapshot: ServerSnapshot, config=None):
        """用快照数据更新卡片"""
        self._server_id = snapshot.server_id

        if config:
            self._name_label.setText(config.name)
            self._ip_label.setText(config.host)

        if snapshot.status == ServerStatus.OFFLINE:
            self._status_dot.setStyleSheet("color: #7f8c8d;")
            self._set_offline()
            return

        # CPU
        cpu_pct = snapshot.cpu.usage_percent if snapshot.cpu else 0
        self._update_bar("cpu", cpu_pct)

        # 内存
        mem_pct = snapshot.memory.usage_percent if snapshot.memory else 0
        self._update_bar("mem", mem_pct)

        # 磁盘（取最大分区）
        disk_pct = 0
        if snapshot.disk and snapshot.disk.partitions:
            disk_pct = max(p.usage_percent for p in snapshot.disk.partitions)
        self._update_bar("disk", disk_pct)

        # 网络
        if snapshot.network and snapshot.network.interfaces:
            self._net_label.setText(
                f"↓ {humanize_bytes_per_sec(snapshot.network.rx_rate)}  "
                f"↑ {humanize_bytes_per_sec(snapshot.network.tx_rate)}"
            )

        # 状态点
        max_pct = max(cpu_pct, mem_pct, disk_pct)
        if max_pct >= THRESHOLD_CRITICAL:
            self._status_dot.setStyleSheet("color: #e74c3c;")
        elif max_pct >= THRESHOLD_WARNING:
            self._status_dot.setStyleSheet("color: #f39c12;")
        else:
            self._status_dot.setStyleSheet("color: #2ecc71;")

    def _update_bar(self, key: str, value: float):
        bar = getattr(self, f"_bar_{key}", None)
        if bar:
            bar.setValue(int(value))
            if value >= THRESHOLD_CRITICAL:
                color = _BAR_CHUNK_COLORS["critical"]
            elif value >= THRESHOLD_WARNING:
                color = _BAR_CHUNK_COLORS["warning"]
            else:
                color = _BAR_CHUNK_COLORS["normal"]
            bar.setStyleSheet(_bar_style(color))
            # 恢复百分比文本（离线时会改为"离线"）
            bar.setFormat("%p%")

    def _set_offline(self):
        for key in ("cpu", "mem", "disk"):
            bar = getattr(self, f"_bar_{key}", None)
            if bar:
                bar.setValue(0)
                bar.setFormat("离线")
                bar.setStyleSheet(_bar_style(_BAR_CHUNK_COLORS["offline"]))
        self._net_label.setText("-- offline --")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._server_id:
            self.clicked.emit(self._server_id)
        super().mousePressEvent(event)

    def _on_monitor_clicked(self):
        """点击监控切换按钮"""
        if not self._server_id:
            return
        # 当前按钮文字决定当前状态：显示"○ 停止"说明正在监控
        is_running = "停止" in self._monitor_btn.text()
        self.monitoring_toggled.emit(self._server_id, not is_running)

    def set_monitoring_state(self, active: bool):
        """设置监控状态显示"""
        if active:
            self._monitor_btn.setText("● 监控中")
            self._monitor_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: 1px solid #2ecc71;
                    border-radius: 3px;
                    color: #2ecc71;
                    font-size: 10px;
                    padding: 0 4px;
                }
                QPushButton:hover {
                    border: 1px solid #27ae60;
                    color: #27ae60;
                }
            """)
        else:
            self._monitor_btn.setText("○ 停止")
            self._monitor_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: 1px solid #555;
                    border-radius: 3px;
                    color: #aaa;
                    font-size: 10px;
                    padding: 0 4px;
                }
                QPushButton:hover {
                    border: 1px solid #888;
                    color: #fff;
                }
            """)
