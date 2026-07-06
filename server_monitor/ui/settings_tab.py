"""设置 Tab —— 服务器管理、告警规则、全局设置"""

import uuid
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QSpinBox, QComboBox, QMessageBox, QDialog,
    QFormLayout, QDialogButtonBox, QCheckBox, QAbstractItemView,
    QDoubleSpinBox, QFileDialog,
)
from PyQt5.QtCore import Qt, pyqtSignal

from ..core.models import ServerConfig
from ..core.state_manager import StateManager
from ..ssh.credentials import CredentialsManager, save_config
from ..alerts.rules import AlertRule
from ..alerts.alert_engine import AlertEngine
from ..utils.validators import validate_host, validate_port, validate_username
from ..config import DEFAULT_POLL_INTERVAL


class ServerEditDialog(QDialog):
    """服务器编辑对话框"""

    def __init__(self, server: ServerConfig = None, parent=None):
        super().__init__(parent)
        self._server = server
        self._result = None
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("编辑服务器" if self._server else "添加服务器")
        self.setMinimumWidth(400)
        self.setStyleSheet("""
            QDialog { background-color: #2a2a3a; }
            QLabel { color: #cccccc; }
            QLineEdit, QSpinBox {
                background-color: #1e1e2e;
                color: #cccccc;
                border: 1px solid #3a3a4a;
                border-radius: 4px;
                padding: 6px;
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
            }
        """)

        layout = QFormLayout(self)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("显示名称")
        layout.addRow("名称:", self._name_input)

        self._host_input = QLineEdit()
        self._host_input.setPlaceholderText("IP 或域名")
        layout.addRow("主机:", self._host_input)

        self._port_input = QSpinBox()
        self._port_input.setRange(1, 65535)
        self._port_input.setValue(22)
        layout.addRow("端口:", self._port_input)

        self._user_input = QLineEdit()
        self._user_input.setText("root")
        layout.addRow("用户名:", self._user_input)

        self._auth_combo = QComboBox()
        self._auth_combo.addItems(["密码", "密钥"])
        layout.addRow("认证方式:", self._auth_combo)

        self._pass_input = QLineEdit()
        self._pass_input.setEchoMode(QLineEdit.Password)
        layout.addRow("密码:", self._pass_input)

        self._key_input = QLineEdit()
        self._key_input.setPlaceholderText("密钥文件路径（可选）")
        key_row = QHBoxLayout()
        key_row.addWidget(self._key_input, 1)
        self._key_browse_btn = QPushButton("浏览...")
        self._key_browse_btn.setFixedWidth(80)
        self._key_browse_btn.clicked.connect(self._browse_key_file)
        key_row.addWidget(self._key_browse_btn)
        layout.addRow("密钥路径:", key_row)

        self._enabled_check = QCheckBox("启用")
        self._enabled_check.setChecked(True)
        layout.addRow("", self._enabled_check)

        # 预填充
        if self._server:
            self._name_input.setText(self._server.name)
            self._host_input.setText(self._server.host)
            self._port_input.setValue(self._server.port)
            self._user_input.setText(self._server.username)
            self._auth_combo.setCurrentIndex(0 if self._server.auth_type == "password" else 1)
            self._pass_input.setText(self._server.password or "")
            self._key_input.setText(self._server.key_path or "")
            self._enabled_check.setChecked(self._server.enabled)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _browse_key_file(self):
        """打开文件选择对话框选择密钥文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 SSH 私钥文件", "",
            "所有文件 (*);;密钥文件 (*.pem;*.key;*.ppk)",
        )
        if path:
            self._key_input.setText(path)

    def _on_accept(self):
        name = self._name_input.text().strip()
        host = self._host_input.text().strip()
        port = self._port_input.value()
        username = self._user_input.text().strip()

        if not name:
            QMessageBox.warning(self, "错误", "名称不能为空")
            return
        err = validate_host(host)
        if err:
            QMessageBox.warning(self, "错误", err)
            return
        err = validate_username(username)
        if err:
            QMessageBox.warning(self, "错误", err)
            return

        auth_type = "password" if self._auth_combo.currentIndex() == 0 else "key"

        self._result = ServerConfig(
            id=self._server.id if self._server else str(uuid.uuid4())[:8],
            name=name,
            host=host,
            port=port,
            username=username,
            auth_type=auth_type,
            password=self._pass_input.text() or None,
            key_path=self._key_input.text() or None,
            enabled=self._enabled_check.isChecked(),
        )
        self.accept()

    @property
    def result(self) -> ServerConfig:
        return self._result


class SettingsTab(QWidget):
    """设置 Tab"""

    servers_changed = pyqtSignal()  # 服务器列表变更信号
    poll_interval_changed = pyqtSignal(float)
    theme_changed = pyqtSignal(str)  # 主题切换信号，参数: "dark" | "light"

    def __init__(self, state_manager: StateManager,
                 cred_manager: CredentialsManager,
                 alert_engine: AlertEngine, parent=None):
        super().__init__(parent)
        self._state = state_manager
        self._cred = cred_manager
        self._alert_engine = alert_engine
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #3a3a4a;
                background: #1e1e2e;
            }
            QTabBar::tab {
                background: #2a2a3a;
                color: #cccccc;
                padding: 8px 16px;
                border: 1px solid #3a3a4a;
            }
            QTabBar::tab:selected {
                background: #3a3a5a;
                border-bottom: 2px solid #3498db;
            }
        """)

        # 服务器管理
        self._tabs.addTab(self._create_server_tab(), "服务器管理")
        # 告警规则
        self._tabs.addTab(self._create_alert_tab(), "告警规则")
        # 全局设置
        self._tabs.addTab(self._create_general_tab(), "全局设置")

        layout.addWidget(self._tabs)

    def _create_server_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        toolbar = QHBoxLayout()
        add_btn = QPushButton("添加服务器")
        add_btn.clicked.connect(self._add_server)
        toolbar.addWidget(add_btn)

        edit_btn = QPushButton("编辑")
        edit_btn.clicked.connect(self._edit_server)
        toolbar.addWidget(edit_btn)

        del_btn = QPushButton("删除")
        del_btn.clicked.connect(self._delete_server)
        toolbar.addWidget(del_btn)

        test_btn = QPushButton("测试连接")
        test_btn.clicked.connect(self._test_connection)
        toolbar.addWidget(test_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._server_table = QTableWidget()
        self._server_table.setColumnCount(5)
        self._server_table.setHorizontalHeaderLabels([
            "名称", "主机", "端口", "用户", "状态"
        ])
        self._server_table.horizontalHeader().setStretchLastSection(True)
        self._server_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._server_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._server_table.setAlternatingRowColors(True)
        self._server_table.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e2e;
                color: #cccccc;
                alternate-background-color: #252535;
            }
        """)
        layout.addWidget(self._server_table)

        return widget

    def _create_alert_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        toolbar = QHBoxLayout()
        add_btn = QPushButton("添加规则")
        add_btn.clicked.connect(self._add_alert_rule)
        toolbar.addWidget(add_btn)

        del_btn = QPushButton("删除规则")
        del_btn.clicked.connect(self._delete_alert_rule)
        toolbar.addWidget(del_btn)

        save_btn = QPushButton("保存规则")
        save_btn.clicked.connect(self._save_alert_rules)
        toolbar.addWidget(save_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._alert_table = QTableWidget()
        self._alert_table.setColumnCount(5)
        self._alert_table.setHorizontalHeaderLabels([
            "指标", "条件", "阈值", "持续次数", "级别"
        ])
        self._alert_table.horizontalHeader().setStretchLastSection(True)
        self._alert_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._alert_table.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e2e;
                color: #cccccc;
                alternate-background-color: #252535;
            }
        """)
        layout.addWidget(self._alert_table)

        return widget

    def _create_general_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)

        layout.addRow(QLabel("轮询间隔（秒）:"))
        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(3, 60)
        self._interval_spin.setValue(DEFAULT_POLL_INTERVAL)
        self._interval_spin.valueChanged.connect(
            lambda v: (self.poll_interval_changed.emit(float(v)), self._save_all_settings())
        )
        layout.addRow(self._interval_spin)

        layout.addRow(QLabel(""))
        layout.addRow(QLabel("主题:"))
        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["暗色主题", "亮色主题"])
        self._theme_combo.currentIndexChanged.connect(
            lambda idx: (self.theme_changed.emit("dark" if idx == 0 else "light"), self._save_all_settings())
        )
        layout.addRow(self._theme_combo)

        return widget

    # ========== 服务器管理操作 ==========

    def refresh_server_table(self):
        servers = self._cred.get_servers()
        self._server_table.setRowCount(len(servers))
        for i, srv in enumerate(servers):
            self._server_table.setItem(i, 0, QTableWidgetItem(srv.name))
            self._server_table.setItem(i, 1, QTableWidgetItem(srv.host))
            self._server_table.setItem(i, 2, QTableWidgetItem(str(srv.port)))
            self._server_table.setItem(i, 3, QTableWidgetItem(srv.username))
            self._server_table.setItem(i, 4, QTableWidgetItem(
                "启用" if srv.enabled else "禁用"
            ))

    def _add_server(self):
        dlg = ServerEditDialog(parent=self)
        if dlg.exec_() == QDialog.Accepted and dlg.result:
            self._cred.add_server(dlg.result)
            self._state.update_config(dlg.result)
            self.refresh_server_table()
            self.servers_changed.emit()

    def _edit_server(self):
        row = self._server_table.currentRow()
        if row < 0:
            return
        servers = self._cred.get_servers()
        if row >= len(servers):
            return
        dlg = ServerEditDialog(servers[row], parent=self)
        if dlg.exec_() == QDialog.Accepted and dlg.result:
            self._cred.update_server(dlg.result)
            self._state.update_config(dlg.result)
            self.refresh_server_table()
            self.servers_changed.emit()

    def _delete_server(self):
        row = self._server_table.currentRow()
        if row < 0:
            return
        servers = self._cred.get_servers()
        if row >= len(servers):
            return
        srv = servers[row]
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除服务器 '{srv.name}' ({srv.host})？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._cred.remove_server(srv.id)
            self._state.remove_config(srv.id)
            self.refresh_server_table()
            self.servers_changed.emit()

    def _test_connection(self):
        row = self._server_table.currentRow()
        if row < 0:
            return
        servers = self._cred.get_servers()
        if row >= len(servers):
            return
        srv = servers[row]
        # 简单的同步测试
        from ..ssh.connection_pool import SSHConnectionPool
        pool = SSHConnectionPool()
        success, msg = pool.test_connectivity(srv)
        pool.close_all()
        QMessageBox.information(
            self, "测试结果",
            f"{'连接成功!' if success else '连接失败'}\n{msg}",
        )

    # ========== 告警规则操作 ==========

    def refresh_alert_table(self):
        rules = self._alert_engine.get_rules()
        self._alert_table.setRowCount(len(rules))
        cond_map = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "="}
        for i, rule in enumerate(rules):
            self._alert_table.setItem(i, 0, QTableWidgetItem(rule.metric.upper()))
            self._alert_table.setItem(i, 1, QTableWidgetItem(cond_map.get(rule.condition, rule.condition)))
            self._alert_table.setItem(i, 2, QTableWidgetItem(str(rule.threshold)))
            self._alert_table.setItem(i, 3, QTableWidgetItem(str(rule.duration)))
            self._alert_table.setItem(i, 4, QTableWidgetItem(rule.level))

    # ========== 设置持久化 ==========

    def _save_all_settings(self):
        """保存所有全局设置和告警规则到 config.json"""
        data = {
            "poll_interval": self._interval_spin.value(),
            "theme": "dark" if self._theme_combo.currentIndex() == 0 else "light",
            "alert_rules": self._alert_engine.to_dict_list(),
        }
        save_config(data)

    def set_poll_interval(self, interval: float):
        """设置轮询间隔（加载保存的值，不触发信号）"""
        self._interval_spin.blockSignals(True)
        self._interval_spin.setValue(int(interval))
        self._interval_spin.blockSignals(False)

    def set_theme(self, theme: str):
        """设置主题（加载保存的值，不触发信号）"""
        idx = 0 if theme == "dark" else 1
        self._theme_combo.blockSignals(True)
        self._theme_combo.setCurrentIndex(idx)
        self._theme_combo.blockSignals(False)

    def _add_alert_rule(self):
        rule = AlertRule(
            metric="cpu", condition="gte",
            threshold=80.0, duration=3, level="warning",
        )
        rules = self._alert_engine.get_rules()
        rules.append(rule)
        self._alert_engine.set_rules(rules)
        self.refresh_alert_table()
        self._save_all_settings()

    def _delete_alert_rule(self):
        row = self._alert_table.currentRow()
        if row < 0:
            return
        rules = self._alert_engine.get_rules()
        if row < len(rules):
            rules.pop(row)
            self._alert_engine.set_rules(rules)
            self.refresh_alert_table()
            self._save_all_settings()

    def _save_alert_rules(self):
        # 从表格读回编辑的值
        rules = self._alert_engine.get_rules()
        for i in range(self._alert_table.rowCount()):
            if i < len(rules):
                try:
                    rules[i].metric = self._alert_table.item(i, 0).text().lower()
                    cond_text = self._alert_table.item(i, 1).text()
                    cond_map = {">": "gt", ">=": "gte", "<": "lt", "<=": "lte", "=": "eq"}
                    rules[i].condition = cond_map.get(cond_text, cond_text)
                    rules[i].threshold = float(self._alert_table.item(i, 2).text())
                    rules[i].duration = int(self._alert_table.item(i, 3).text())
                    rules[i].level = self._alert_table.item(i, 4).text()
                except (ValueError, AttributeError):
                    pass
        self._alert_engine.set_rules(rules)
        self._save_all_settings()
        QMessageBox.information(self, "保存成功", "告警规则已保存")
