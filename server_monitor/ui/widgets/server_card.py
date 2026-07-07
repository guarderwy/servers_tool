"""服务器状态卡片控件 —— 支持暗色/亮色主题"""

from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton
from PyQt5.QtCore import Qt, pyqtSignal

from ...core.models import ServerSnapshot, ServerStatus
from ...utils.humanize import humanize_bytes_per_sec
from ...config import THRESHOLD_WARNING, THRESHOLD_CRITICAL


# 进度条色块颜色（与主题无关，按状态级别区分）
_BAR_CHUNK_COLORS = {
    "normal": "#2ecc71",
    "warning": "#f39c12",
    "critical": "#e74c3c",
    "offline": "#bdc3c7",
}


class ServerCard(QFrame):
    """单台服务器的状态卡片"""

    # 主题色表
    THEME_COLORS = {
        "dark": {
            "card_bg": "#2a2a3a",
            "card_border": "#3a3a4a",
            "card_border_hover": "#5a5a7a",
            "name_fg": "#ffffff",
            "ip_fg": "#888888",
            "spec_fg": "#777777",
            "net_fg": "#aaaaaa",
            "label_fg": "#aaaaaa",
            "bar_bg": "#1e1e2e",
            "bar_border": "#3a3a4a",
            "bar_text": "#cccccc",
            "btn_border": "#555555",
            "btn_fg": "#aaaaaa",
            "btn_hover_border": "#888888",
            "btn_hover_fg": "#ffffff",
            "monitor_btn_border": "#2ecc71",
            "monitor_btn_fg": "#2ecc71",
            "monitor_btn_hover_border": "#27ae60",
            "monitor_btn_hover_fg": "#27ae60",
        },
        "light": {
            "card_bg": "#ffffff",
            "card_border": "#d0d0d0",
            "card_border_hover": "#a0a0c0",
            "name_fg": "#222222",
            "ip_fg": "#777777",
            "spec_fg": "#888888",
            "net_fg": "#666666",
            "label_fg": "#555555",
            "bar_bg": "#f0f0f0",
            "bar_border": "#cccccc",
            "bar_text": "#333333",
            "btn_border": "#cccccc",
            "btn_fg": "#666666",
            "btn_hover_border": "#999999",
            "btn_hover_fg": "#333333",
            "monitor_btn_border": "#27ae60",
            "monitor_btn_fg": "#27ae60",
            "monitor_btn_hover_border": "#1e8449",
            "monitor_btn_hover_fg": "#1e8449",
        },
    }

    clicked = pyqtSignal(str)  # server_id
    monitoring_toggled = pyqtSignal(str, bool)  # server_id, start

    def __init__(self, theme="dark", parent=None):
        super().__init__(parent)
        self._server_id = ""
        self._monitoring_active = False
        self._theme = theme if theme in self.THEME_COLORS else "dark"
        self._bar_base_style = ""  # 由 _apply_card_theme 填充
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumSize(220, 180)
        self.setMaximumSize(280, 220)
        self.setCursor(Qt.PointingHandCursor)
        self._setup_ui()
        self._apply_card_theme()

    # ── 主题辅助 ──────────────────────────────────

    def _c(self, key: str) -> str:
        """取当前主题色的快捷方法"""
        return self.THEME_COLORS[self._theme][key]

    def set_card_theme(self, theme: str):
        """切换卡片主题"""
        if theme == self._theme or theme not in self.THEME_COLORS:
            return
        self._theme = theme
        self._apply_card_theme()

    def _apply_card_theme(self):
        """根据当前主题刷新所有静态 UI 元素的颜色"""
        c = self.THEME_COLORS[self._theme]

        # ── 卡片边框 / 背景 ──
        self.setStyleSheet(f"""
            ServerCard {{
                background-color: {c["card_bg"]};
                border: 1px solid {c["card_border"]};
                border-radius: 8px;
                padding: 8px;
            }}
            ServerCard:hover {{
                border: 1px solid {c["card_border_hover"]};
            }}
        """)

        # ── 文字标签 ──
        self._name_label.setStyleSheet(
            f"font-weight: bold; font-size: 14px; color: {c['name_fg']};"
        )
        self._ip_label.setStyleSheet(f"color: {c['ip_fg']}; font-size: 11px;")
        self._spec_label.setStyleSheet(f"color: {c['spec_fg']}; font-size: 10px;")
        self._net_label.setStyleSheet(f"color: {c['net_fg']}; font-size: 10px;")

        for key in ("cpu", "mem", "disk"):
            lbl = getattr(self, f"_lbl_{key}", None)
            if lbl:
                lbl.setStyleSheet(f"color: {c['label_fg']}; font-size: 11px;")

        # ── 进度条基础样式 ──
        self._bar_base_style = (
            f"QProgressBar {{"
            f"  border: 1px solid {c['bar_border']};"
            f"  border-radius: 3px;"
            f"  text-align: center;"
            f"  background: {c['bar_bg']};"
            f"  font-size: 10px;"
            f"  color: {c['bar_text']};"
            f"}}"
            f"QProgressBar::chunk {{"
            f"  border-radius: 2px;"
            f"}}"
        )
        # 重新应用进度条颜色
        for key in ("cpu", "mem", "disk"):
            bar = getattr(self, f"_bar_{key}", None)
            if bar:
                # 保持当前值，只刷新样式
                val = bar.value()
                self._update_bar(key, val)

        # ── 监控按钮 ──
        self._apply_monitor_btn_style()

    def _apply_monitor_btn_style(self):
        """根据主题和监控状态刷新按钮样式"""
        c = self.THEME_COLORS[self._theme]
        if self._monitoring_active:
            style = (
                f"QPushButton {{"
                f"  background: transparent;"
                f"  border: 1px solid {c['monitor_btn_border']};"
                f"  border-radius: 3px;"
                f"  color: {c['monitor_btn_fg']};"
                f"  font-size: 10px;"
                f"  padding: 0 4px;"
                f"}}"
                f"QPushButton:hover {{"
                f"  border: 1px solid {c['monitor_btn_hover_border']};"
                f"  color: {c['monitor_btn_hover_fg']};"
                f"}}"
            )
        else:
            style = (
                f"QPushButton {{"
                f"  background: transparent;"
                f"  border: 1px solid {c['btn_border']};"
                f"  border-radius: 3px;"
                f"  color: {c['btn_fg']};"
                f"  font-size: 10px;"
                f"  padding: 0 4px;"
                f"}}"
                f"QPushButton:hover {{"
                f"  border: 1px solid {c['btn_hover_border']};"
                f"  color: {c['btn_hover_fg']};"
                f"}}"
            )
        self._monitor_btn.setStyleSheet(style)

    # ── UI 构建 ──────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        # 头部：状态圆点 + 主机名 + 监控切换按钮
        header = QHBoxLayout()
        self._status_dot = QLabel("●")
        self._status_dot.setFixedWidth(16)
        header.addWidget(self._status_dot)

        self._name_label = QLabel("--")
        header.addWidget(self._name_label)
        header.addStretch()

        self._monitor_btn = QPushButton("○ 停止")
        self._monitor_btn.setFixedWidth(60)
        self._monitor_btn.setFixedHeight(22)
        self._monitor_btn.setCursor(Qt.PointingHandCursor)
        self._monitor_btn.clicked.connect(self._on_monitor_clicked)
        header.addWidget(self._monitor_btn)
        layout.addLayout(header)

        # IP
        self._ip_label = QLabel("--")
        layout.addWidget(self._ip_label)

        # 规格
        self._spec_label = QLabel("")
        layout.addWidget(self._spec_label)

        # 指标行
        layout.addLayout(self._make_metric_row("CPU", "cpu"))
        layout.addLayout(self._make_metric_row("MEM", "mem"))
        layout.addLayout(self._make_metric_row("DISK", "disk"))

        # 网络速率
        self._net_label = QLabel("-- ↓ -- ↑")
        layout.addWidget(self._net_label)

        layout.addStretch()

    def _make_metric_row(self, label_text: str, key: str):
        row = QHBoxLayout()
        lbl = QLabel(f"{label_text}:")
        lbl.setFixedWidth(35)
        setattr(self, f"_lbl_{key}", lbl)
        row.addWidget(lbl)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(True)
        bar.setFixedHeight(16)
        setattr(self, f"_bar_{key}", bar)
        row.addWidget(bar)
        return row

    # ── 数据更新 ──────────────────────────────────

    def update_snapshot(self, snapshot: ServerSnapshot, config=None):
        """用快照数据更新卡片"""
        self._server_id = snapshot.server_id

        if config:
            self._name_label.setText(config.name)
            self._ip_label.setText(config.host)

        # 规格
        if snapshot.static_info and snapshot.static_info.cpu_cores:
            si = snapshot.static_info
            mem_gb = si.mem_total_mb / 1024 if si.mem_total_mb else 0
            spec = f"{si.cpu_cores} vCPU"
            if mem_gb > 0:
                spec += f" · {mem_gb:.0f} GB"
            if si.os_name:
                spec += f"  {si.os_name}"
            self._spec_label.setText(spec)
            self._spec_label.setVisible(True)
        else:
            self._spec_label.setVisible(False)

        # 离线
        if snapshot.status == ServerStatus.OFFLINE:
            self._status_dot.setStyleSheet(f"color: {_BAR_CHUNK_COLORS['offline']};")
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

        # 状态圆点
        max_pct = max(cpu_pct, mem_pct, disk_pct)
        if max_pct >= THRESHOLD_CRITICAL:
            self._status_dot.setStyleSheet(f"color: {_BAR_CHUNK_COLORS['critical']};")
        elif max_pct >= THRESHOLD_WARNING:
            self._status_dot.setStyleSheet(f"color: {_BAR_CHUNK_COLORS['warning']};")
        else:
            self._status_dot.setStyleSheet(f"color: {_BAR_CHUNK_COLORS['normal']};")

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
            bar.setStyleSheet(
                self._bar_base_style
                + f"QProgressBar::chunk {{ background-color: {color}; }}"
            )
            bar.setFormat("%p%")

    def _set_offline(self):
        for key in ("cpu", "mem", "disk"):
            bar = getattr(self, f"_bar_{key}", None)
            if bar:
                bar.setValue(0)
                bar.setFormat("离线")
                bar.setStyleSheet(
                    self._bar_base_style
                    + f"QProgressBar::chunk {{ background-color: {_BAR_CHUNK_COLORS['offline']}; }}"
                )
        self._net_label.setText("-- offline --")

    # ── 交互 ──────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._server_id:
            self.clicked.emit(self._server_id)
        super().mousePressEvent(event)

    def _on_monitor_clicked(self):
        if not self._server_id:
            return
        is_running = "停止" in self._monitor_btn.text()
        self.monitoring_toggled.emit(self._server_id, not is_running)

    def set_monitoring_state(self, active: bool):
        """设置监控状态显示"""
        self._monitoring_active = active
        if active:
            self._monitor_btn.setText("● 监控中")
        else:
            self._monitor_btn.setText("○ 停止")
        self._apply_monitor_btn_style()
