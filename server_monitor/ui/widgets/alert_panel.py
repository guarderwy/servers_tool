"""告警面板控件"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QAbstractItemView,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from ...core.models import AlertRecord, AlertLevel


class AlertPanel(QWidget):
    """告警面板 —— 展示当前活跃告警和历史记录"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._alerts: list[AlertRecord] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 标题
        header = QHBoxLayout()
        header.addWidget(QLabel("<b>告警记录</b>"))
        header.addStretch()
        self._count_label = QLabel("活跃告警: 0")
        self._count_label.setStyleSheet("color: #f39c12; font-weight: bold;")
        header.addWidget(self._count_label)

        self._clear_btn = QPushButton("清除已恢复")
        header.addWidget(self._clear_btn)
        self._clear_btn.clicked.connect(self._clear_resolved)
        layout.addLayout(header)

        # 告警表格
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels([
            "时间", "服务器", "指标", "当前值", "阈值", "状态",
        ])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table)

    def add_alert(self, alert: AlertRecord):
        self._alerts.insert(0, alert)
        self._render()

    def update_alerts(self, alerts: list[AlertRecord]):
        self._alerts = alerts
        self._render()

    def _render(self):
        active = sum(1 for a in self._alerts if not a.is_resolved)
        self._count_label.setText(f"活跃告警: {active}")
        if active > 0:
            self._count_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
        else:
            self._count_label.setStyleSheet("color: #2ecc71; font-weight: bold;")

        self._table.setRowCount(len(self._alerts))
        for i, alert in enumerate(self._alerts):
            self._table.setItem(i, 0, QTableWidgetItem(
                alert.triggered_at.strftime("%m-%d %H:%M:%S")
            ))
            self._table.setItem(i, 1, QTableWidgetItem(alert.server_name))

            metric_item = QTableWidgetItem(alert.metric.upper())
            if alert.level == AlertLevel.CRITICAL:
                metric_item.setForeground(QColor("#e74c3c"))
            else:
                metric_item.setForeground(QColor("#f39c12"))
            self._table.setItem(i, 2, metric_item)

            self._table.setItem(i, 3, QTableWidgetItem(f"{alert.current_value:.1f}"))
            self._table.setItem(i, 4, QTableWidgetItem(f"{alert.threshold:.1f}"))

            status_text = "已恢复" if alert.is_resolved else "活跃"
            status_item = QTableWidgetItem(status_text)
            if alert.is_resolved:
                status_item.setForeground(QColor("#2ecc71"))
            else:
                status_item.setForeground(QColor("#e74c3c"))
            self._table.setItem(i, 5, status_item)

    def _clear_resolved(self):
        self._alerts = [a for a in self._alerts if not a.is_resolved]
        self._render()

    def get_active_count(self) -> int:
        return sum(1 for a in self._alerts if not a.is_resolved)
