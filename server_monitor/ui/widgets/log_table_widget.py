"""日志表格控件"""

from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QComboBox, QAbstractItemView,
)
from PyQt5.QtCore import Qt

from ...core.models import AuthLogEntry


class LogTableWidget(QWidget):
    """登录记录展示表格"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_entries: list[AuthLogEntry] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 筛选栏
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("用户:"))
        self._user_filter = QLineEdit()
        self._user_filter.setPlaceholderText("输入用户名筛选")
        self._user_filter.setFixedWidth(120)
        self._user_filter.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self._user_filter)

        filter_row.addWidget(QLabel("IP:"))
        self._ip_filter = QLineEdit()
        self._ip_filter.setPlaceholderText("输入 IP 筛选")
        self._ip_filter.setFixedWidth(120)
        self._ip_filter.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self._ip_filter)

        filter_row.addWidget(QLabel("类型:"))
        self._type_filter = QComboBox()
        self._type_filter.addItems(["全部", "成功", "失败"])
        self._type_filter.currentTextChanged.connect(self._apply_filter)
        filter_row.addWidget(self._type_filter)

        filter_row.addStretch()

        self._refresh_btn = QPushButton("刷新")
        filter_row.addWidget(self._refresh_btn)
        layout.addLayout(filter_row)

        # 表格
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["时间", "事件", "用户", "来源 IP", "方法"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e2e;
                color: #cccccc;
                alternate-background-color: #252535;
            }
        """)
        layout.addWidget(self._table)

    def update_entries(self, entries: list[AuthLogEntry]):
        """更新日志数据（默认按时间倒序：最新的在前）"""
        self._all_entries = list(reversed(entries))
        self._apply_filter()

    def _apply_filter(self):
        """应用筛选条件"""
        user_kw = self._user_filter.text().strip().lower()
        ip_kw = self._ip_filter.text().strip()
        type_kw = self._type_filter.currentText()

        filtered = []
        for entry in self._all_entries:
            if user_kw and user_kw not in entry.user.lower():
                continue
            if ip_kw and ip_kw not in entry.source_ip:
                continue
            if type_kw == "成功" and entry.event_type != "accepted":
                continue
            if type_kw == "失败" and entry.event_type != "failed":
                continue
            filtered.append(entry)

        self._render(filtered)

    def _render(self, entries: list[AuthLogEntry]):
        self._table.setRowCount(len(entries))
        for i, entry in enumerate(entries):
            ts = entry.timestamp.strftime("%m-%d %H:%M:%S")
            event_text = "接受" if entry.event_type == "accepted" else "失败"
            if entry.event_type == "invalid":
                event_text = "无效"

            self._table.setItem(i, 0, QTableWidgetItem(ts))

            event_item = QTableWidgetItem(event_text)
            if entry.event_type == "accepted":
                event_item.setForeground(Qt.green)
            else:
                event_item.setForeground(Qt.red)
            self._table.setItem(i, 1, event_item)

            self._table.setItem(i, 2, QTableWidgetItem(entry.user))
            self._table.setItem(i, 3, QTableWidgetItem(entry.source_ip))
            self._table.setItem(i, 4, QTableWidgetItem(entry.method))

    def connect_refresh(self, handler):
        self._refresh_btn.clicked.connect(handler)
