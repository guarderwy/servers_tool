"""服务器列表表格组件 —— 核心 UI 组件"""

from PyQt5.QtWidgets import (
    QTableView, QHeaderView, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QAbstractItemView,
)
from PyQt5.QtCore import (
    Qt, QAbstractTableModel, QSortFilterProxyModel,
    QModelIndex, pyqtSignal,
)
from PyQt5.QtGui import QColor, QBrush, QFont, QPainter, QPen
from PyQt5.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from ...core.models import ServerSnapshot, ServerStatus
from ...core.state_manager import StateManager
from ...utils.humanize import humanize_bytes_per_sec
from ...config import (
    THRESHOLD_WARNING, THRESHOLD_CRITICAL,
    COLOR_NORMAL_BG, COLOR_NORMAL_FG, COLOR_NORMAL_BAR,
    COLOR_WARNING_BG, COLOR_WARNING_FG, COLOR_WARNING_BAR,
    COLOR_CRITICAL_BG, COLOR_CRITICAL_FG, COLOR_CRITICAL_BAR,
    COLOR_OFFLINE_BG, COLOR_OFFLINE_FG, COLOR_OFFLINE_BAR,
)


def get_color_level(value) -> str:
    """根据值返回颜色级别"""
    if value is None:
        return "offline"
    if value >= 90:
        return "critical"
    if value >= 80:
        return "warning"
    return "normal"


COLOR_MAP = {
    "normal":   {"bg": COLOR_NORMAL_BG,   "fg": COLOR_NORMAL_FG,   "bar": COLOR_NORMAL_BAR},
    "warning":  {"bg": COLOR_WARNING_BG,  "fg": COLOR_WARNING_FG,  "bar": COLOR_WARNING_BAR},
    "critical": {"bg": COLOR_CRITICAL_BG, "fg": COLOR_CRITICAL_FG, "bar": COLOR_CRITICAL_BAR},
    "offline":  {"bg": COLOR_OFFLINE_BG,  "fg": COLOR_OFFLINE_FG,  "bar": COLOR_OFFLINE_BAR},
}


class ServerListModel(QAbstractTableModel):
    """服务器列表数据模型"""

    COLUMNS = [
        ("status",     "状态",     60),
        ("name",       "主机名",   120),
        ("ip",         "IP 地址",  130),
        ("spec",       "规格",     130),
        ("cpu_pct",    "CPU %",    100),
        ("mem_pct",    "内存 %",   100),
        ("disk_pct",   "磁盘 %",   100),
        ("net_rx",     "↓速率",    90),
        ("net_tx",     "↑速率",    90),
        ("load",       "负载",     70),
        ("updated_at", "更新时间", 140),
        ("monitor",    "监控",     70),
    ]

    PERCENT_COLS = {4, 5, 6}  # cpu_pct, mem_pct, disk_pct
    MONITOR_COL = 11

    def __init__(self, state_manager: StateManager, parent=None):
        super().__init__(parent)
        self._state = state_manager
        self._data: list = []
        self._state.register_listener(self._on_state_change)

    def _on_state_change(self, server_id: str):
        self.refresh()

    def refresh(self, scheduler=None):
        """刷新数据"""
        self.beginResetModel()
        self._data = []
        for snap in self._state.get_all_snapshots():
            cfg = self._state.get_config(snap.server_id)
            if not cfg:
                continue

            cpu_pct = snap.cpu.usage_percent if snap.cpu else None
            mem_pct = snap.memory.usage_percent if snap.memory else None
            disk_pct = None
            if snap.disk and snap.disk.partitions:
                disk_pct = max(p.usage_percent for p in snap.disk.partitions)

            net_rx = snap.network.rx_rate if snap.network else 0.0
            net_tx = snap.network.tx_rate if snap.network else 0.0

            load = snap.cpu.load_1m if snap.cpu else None
            monitoring = scheduler.is_running(snap.server_id) if scheduler else False

            self._data.append({
                "server_id": snap.server_id,
                "status": snap.status,
                "name": cfg.name,
                "ip": cfg.host,
                "spec": snap.static_info,
                "cpu_pct": cpu_pct,
                "mem_pct": mem_pct,
                "disk_pct": disk_pct,
                "net_rx": net_rx,
                "net_tx": net_tx,
                "load": load,
                "updated_at": snap.timestamp,
                "monitoring": monitoring,
                "snapshot": snap,
            })
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.COLUMNS[section][1]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._data[index.row()]
        col_key = self.COLUMNS[index.column()][0]

        if role == Qt.DisplayRole:
            return self._display_value(row, col_key)
        elif role == Qt.UserRole:
            # 原始数值，用于排序和委托渲染
            return self._raw_value(row, col_key)
        elif role == Qt.BackgroundRole and index.column() in self.PERCENT_COLS:
            val = self._raw_value(row, col_key)
            level = get_color_level(val)
            return QBrush(QColor(COLOR_MAP[level]["bg"]))
        elif role == Qt.ForegroundRole and index.column() in self.PERCENT_COLS:
            val = self._raw_value(row, col_key)
            level = get_color_level(val)
            return QBrush(QColor(COLOR_MAP[level]["fg"]))
        elif role == Qt.ForegroundRole and index.column() == 0:
            # 状态列的颜色：按状态显示不同颜色
            status = row["status"]
            sc = {
                ServerStatus.ONLINE: "#2ecc71",
                ServerStatus.OFFLINE: "#7f8c8d",
                ServerStatus.WARNING: "#f39c12",
                ServerStatus.CRITICAL: "#e74c3c",
            }
            return QBrush(QColor(sc.get(status, "#7f8c8d")))
        elif role == Qt.ForegroundRole and index.column() == self.MONITOR_COL:
            monitoring = row.get("monitoring", False)
            return QBrush(QColor("#2ecc71" if monitoring else "#7f8c8d"))
        elif role == Qt.TextAlignmentRole:
            if index.column() >= 3:
                return Qt.AlignCenter
            return Qt.AlignLeft | Qt.AlignVCenter
        return None

    def _display_value(self, row: dict, key: str):
        if row["status"] == ServerStatus.OFFLINE:
            if key in ("cpu_pct", "mem_pct", "disk_pct", "load"):
                return "--"

        if key == "status":
            status_map = {
                ServerStatus.ONLINE: "● 在线",
                ServerStatus.OFFLINE: "● 离线",
                ServerStatus.WARNING: "● 警告",
                ServerStatus.CRITICAL: "● 严重",
            }
            return status_map.get(row["status"], "● --")
        elif key == "name":
            return row["name"]
        elif key == "ip":
            return row["ip"]
        elif key == "spec":
            si = row["spec"]
            if si and si.cpu_cores:
                mem_gb = si.mem_total_mb / 1024 if si.mem_total_mb else 0
                spec = f"{si.cpu_cores}vCPU"
                if mem_gb > 0:
                    spec += f" {mem_gb:.0f}GB"
                return spec
            return "--"
        elif key == "cpu_pct":
            v = row["cpu_pct"]
            return f"{v:.1f}%" if v is not None else "--"
        elif key == "mem_pct":
            v = row["mem_pct"]
            return f"{v:.1f}%" if v is not None else "--"
        elif key == "disk_pct":
            v = row["disk_pct"]
            return f"{v:.1f}%" if v is not None else "--"
        elif key == "net_rx":
            return humanize_bytes_per_sec(row["net_rx"])
        elif key == "net_tx":
            return humanize_bytes_per_sec(row["net_tx"])
        elif key == "load":
            v = row["load"]
            return f"{v:.2f}" if v is not None else "--"
        elif key == "updated_at":
            return row["updated_at"].strftime("%H:%M:%S")
        elif key == "monitor":
            return "● 监控中" if row.get("monitoring") else "○ 已停止"
        return ""

    def _raw_value(self, row: dict, key: str):
        if key == "spec":
            si = row.get("spec")
            if si and si.cpu_cores:
                return si.cpu_cores
            return 0
        val = row.get(key)
        if val is None:
            return -1  # 用于排序
        if isinstance(val, (int, float)):
            return val
        return 0

    def get_server_id(self, row: int) -> str:
        if 0 <= row < len(self._data):
            return self._data[row]["server_id"]
        return ""

    def get_snapshot(self, row: int):
        if 0 <= row < len(self._data):
            return self._data[row].get("snapshot")
        return None


class ProgressDelegate(QStyledItemDelegate):
    """自定义委托：在百分比列内绘制「数值文本 + 水平进度条」"""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        value = index.data(Qt.UserRole)
        if value is None or value < 0:
            # 离线状态
            painter.save()
            painter.fillRect(option.rect, QBrush(QColor(COLOR_MAP["offline"]["bg"])))
            painter.setPen(QColor(COLOR_MAP["offline"]["fg"]))
            painter.drawText(option.rect, Qt.AlignCenter, "--")
            painter.restore()
            return

        level = get_color_level(value)
        colors = COLOR_MAP[level]

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        # 背景
        painter.fillRect(option.rect, QBrush(QColor(colors["bg"])))

        rect = option.rect
        text_rect = rect.adjusted(0, 2, 0, -rect.height() // 2 - 2)
        bar_rect = rect.adjusted(4, rect.height() // 2 + 2, -4, -4)

        # 数值文本
        painter.setPen(QColor(colors["fg"]))
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(text_rect, Qt.AlignCenter, f"{value:.1f}%")

        # 进度条背景
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#d5d5d5"))
        painter.drawRoundedRect(bar_rect, 2, 2)

        # 进度条填充
        bar_width = bar_rect.width() * min(value / 100.0, 1.0)
        fill_rect = bar_rect.adjusted(0, 0, -int(bar_rect.width() - bar_width), 0)
        painter.setBrush(QColor(colors["bar"]))
        painter.drawRoundedRect(fill_rect, 2, 2)

        painter.restore()

    def sizeHint(self, option, index):
        from PyQt5.QtCore import QSize
        return QSize(100, 40)


class ServerListTable(QWidget):
    """组合控件：Model + Proxy(排序) + Delegate + 视图"""

    server_selected = pyqtSignal(str)       # server_id
    server_double_clicked = pyqtSignal(str)  # server_id
    monitor_toggled = pyqtSignal(str, bool)  # server_id, start

    def __init__(self, state_manager: StateManager, scheduler=None, parent=None):
        super().__init__(parent)
        self._state = state_manager
        self._scheduler = scheduler

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 表格
        self._model = ServerListModel(state_manager)
        self._proxy = QSortFilterProxyModel()
        self._proxy.setSourceModel(self._model)
        self._proxy.setSortRole(Qt.UserRole)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.verticalHeader().setVisible(False)
        
        self._table.setShowGrid(False)
        self._table.setStyleSheet("""
            QTableView {
                background-color: #1e1e2e;
                alternate-background-color: #252535;
                color: #cccccc;
                gridline-color: #3a3a4a;
                selection-background-color: #3a3a6a;
            }
            QHeaderView::section {
                background-color: #2a2a3a;
                color: #cccccc;
                padding: 6px;
                border: 1px solid #3a3a4a;
                font-weight: bold;
            }
        """)

        # 设置列宽
        header = self._table.horizontalHeader()
        for i, (_, _, width) in enumerate(ServerListModel.COLUMNS):
            self._table.setColumnWidth(i, width)
        header.setStretchLastSection(True)

        # 百分比列使用自定义委托
        delegate = ProgressDelegate()
        for col_idx in ServerListModel.PERCENT_COLS:
            self._table.setItemDelegateForColumn(col_idx, delegate)

        # 行高
        self._table.verticalHeader().setDefaultSectionSize(45)

        # 信号
        self._table.clicked.connect(self._on_clicked)
        self._table.doubleClicked.connect(self._on_double_clicked)

        layout.addWidget(self._table)

    def _on_clicked(self, proxy_index):
        source_index = self._proxy.mapToSource(proxy_index)
        server_id = self._model.get_server_id(source_index.row())
        if server_id:
            self.server_selected.emit(server_id)

    def _on_double_clicked(self, proxy_index):
        source_index = self._proxy.mapToSource(proxy_index)
        server_id = self._model.get_server_id(source_index.row())
        if not server_id:
            return
        if proxy_index.column() == self._model.MONITOR_COL:
            # 监控列双击切换监控状态
            if self._scheduler:
                running = self._scheduler.is_running(server_id)
                self._scheduler.stop(server_id) if running else self._scheduler.start(server_id)
                self.monitor_toggled.emit(server_id, not running)
                self.refresh()
        else:
            self.server_double_clicked.emit(server_id)

    def refresh(self):
        self._model.refresh(self._scheduler)

    def get_selected_server_id(self) -> str:
        indexes = self._table.selectionModel().selectedRows()
        if indexes:
            source_index = self._proxy.mapToSource(indexes[0])
            return self._model.get_server_id(source_index.row())
        return ""
