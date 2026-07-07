"""连接来源 TOP5 表格控件 —— 用于排查异常连接 / 恶意攻击"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from ...core.models import IPConnectionCount


class ConnIPTable(QWidget):
    """展示连接数最多的来源 IP（Top N），辅助排查服务器是否被恶意攻击"""

    def __init__(self, parent=None, top_n: int = 5):
        super().__init__(parent)
        self._top_n = top_n
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._table = QTableWidget()
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(["来源 IP", "连接数"])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.setMaximumHeight(190)
        layout.addWidget(self._table)

        self.update_data([])

    def update_data(self, conns: list):
        """conns: list[IPConnectionCount]，按连接数降序"""
        top = list(conns)[:self._top_n]

        if not top:
            self._table.setRowCount(1)
            item = QTableWidgetItem("暂无连接数据")
            item.setForeground(QColor("#777777"))
            self._table.setItem(0, 0, item)
            self._table.setItem(0, 1, QTableWidgetItem(""))
            self._table.item(0, 1).setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            return

        self._table.setRowCount(len(top))
        max_count = max(c.count for c in top) or 1
        for i, c in enumerate(top):
            color = None
            ratio = c.count / max_count
            if ratio >= 0.8:
                color = QColor("#e74c3c")   # 红：占比极高，疑似攻击
            elif ratio >= 0.5:
                color = QColor("#f39c12")   # 橙：占比较高，需关注

            ip_item = QTableWidgetItem(c.ip)
            cnt_item = QTableWidgetItem(str(c.count))
            cnt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if color is not None:
                ip_item.setForeground(color)
                cnt_item.setForeground(color)
            self._table.setItem(i, 0, ip_item)
            self._table.setItem(i, 1, cnt_item)
