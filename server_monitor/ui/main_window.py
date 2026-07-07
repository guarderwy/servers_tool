"""主窗口框架"""

from PyQt5.QtWidgets import (
    QMainWindow, QTabWidget, QToolBar, QAction, QStatusBar,
    QLabel, QMessageBox, QWidget, QVBoxLayout,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon

from .dashboard_tab import DashboardTab
from .monitor_tab import MonitorTab
from .analysis_tab import AnalysisTab
from .settings_tab import SettingsTab
from .widgets.alert_panel import AlertPanel
from .widgets.marquee_bar import MarqueeBar
from .widgets.login_dialog import LoginDialog
from ..core.state_manager import StateManager
from ..core.collector import CollectorScheduler
from ..core.models import ServerSnapshot, ServerStatus
from ..ssh.connection_pool import SSHConnectionPool
from ..ssh.credentials import CredentialsManager, load_config
from ..alerts.alert_engine import AlertEngine
from ..config import APP_TITLE, DEFAULT_POLL_INTERVAL, CREDENTIALS_FILE


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)

        # 核心组件
        self._pool = SSHConnectionPool()
        self._state = StateManager()
        self._cred = CredentialsManager()
        self._alert_engine = AlertEngine()
        self._scheduler = CollectorScheduler(
            self._pool, self._state, DEFAULT_POLL_INTERVAL
        )

        # 定时刷新
        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._periodic_refresh)

        self._last_update_time = None  # 最后一次实际采集的时间

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        # 工具栏
        self._toolbar = QToolBar("主工具栏")
        self._toolbar.setMovable(False)
        self.addToolBar(self._toolbar)

        self._start_action = QAction("全部监控", self)
        self._start_action.triggered.connect(self._start_all)
        self._toolbar.addAction(self._start_action)

        self._stop_action = QAction("停止监控", self)
        self._stop_action.triggered.connect(self._stop_all)
        self._toolbar.addAction(self._stop_action)

        self._toolbar.addSeparator()

        self._refresh_action = QAction("刷新", self)
        self._refresh_action.triggered.connect(self._manual_refresh)
        self._toolbar.addAction(self._refresh_action)

        # Tab 主控件
        self._tabs = QTabWidget()

        self._dashboard = DashboardTab(self._state, scheduler=self._scheduler)
        self._monitor = MonitorTab(self._state, scheduler=self._scheduler)
        self._analysis = AnalysisTab(self._state, self._scheduler)
        self._settings = SettingsTab(
            self._state, self._cred, self._alert_engine
        )

        self._tabs.addTab(self._dashboard, "仪表盘")
        self._tabs.addTab(self._monitor, "实时监控")
        self._tabs.addTab(self._analysis, "分析")
        # 告警面板独立成 Tab，置于「设置」之前
        self._alert_panel = AlertPanel()
        self._tabs.insertTab(3, self._alert_panel, "告警")
        self._tabs.addTab(self._settings, "设置")

        # 顶部滚动告警栏（位于工具栏下方、Tab 上方），只滚动活跃告警
        self._marquee = MarqueeBar()

        # 中央布局
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.addWidget(self._marquee)
        central_layout.addWidget(self._tabs, 1)

        self.setCentralWidget(central)

        # 状态栏
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self._status_online = QLabel("在线: 0/0")
        self._status_monitor = QLabel("监控: 0/0")
        self._status_alerts = QLabel("告警: 0")
        self._status_update = QLabel("最后更新: --")

        self._status_bar.addWidget(self._status_online)
        self._status_bar.addWidget(self._status_monitor)
        self._status_bar.addWidget(self._status_alerts)
        self._status_bar.addPermanentWidget(self._status_update)

    def _connect_signals(self):
        # 采集数据 → UI 更新
        self._scheduler.snapshot_ready.connect(self._on_snapshot)
        self._scheduler.server_offline.connect(self._on_offline)

        # 告警
        self._alert_engine.notifier.alert_triggered.connect(self._on_alert)
        self._alert_engine.notifier.alert_resolved.connect(self._on_alert_resolved)

        # 设置变更
        self._settings.servers_changed.connect(self._on_servers_changed)
        self._settings.poll_interval_changed.connect(self._on_interval_changed)
        self._settings.theme_changed.connect(self._apply_theme)

        # 监控 Tab 选中服务器
        self._monitor.server_selected.connect(self._on_monitor_server_selected)

        # 仪表盘卡片监控切换
        self._dashboard.monitoring_state_changed.connect(self._on_monitor_state_changed)

        # 实时监控 Tab 列表监控切换
        self._monitor.monitoring_state_changed.connect(self._on_monitor_state_changed)

    def start(self):
        """启动应用（显示登录对话框）"""
        is_first_run = not CREDENTIALS_FILE.exists()
        dlg = LoginDialog(is_first_run=is_first_run, parent=self)

        if dlg.exec_() != LoginDialog.Accepted:
            return False

        password = dlg.password
        if is_first_run:
            self._cred.set_password(password)
            self._cred.save()
        else:
            if not self._cred.load(password):
                QMessageBox.critical(self, "错误", "主密码错误或凭据文件损坏")
                return False

        # 加载服务器配置
        for srv in self._cred.get_servers():
            self._state.update_config(srv)

        # 加载已保存的非敏感配置（告警规则、轮询间隔、主题）
        config = load_config()

        # 恢复告警规则
        rules_data = config.get("alert_rules")
        if rules_data:
            self._alert_engine.load_from_dict(rules_data)

        # 恢复轮询间隔
        saved_interval = config.get("poll_interval", DEFAULT_POLL_INTERVAL)
        self._scheduler.set_interval(float(saved_interval))
        self._settings.set_poll_interval(float(saved_interval))

        # 恢复主题（先设置 UI 控件，再应用主题）
        saved_theme = config.get("theme", "dark")
        self._settings.set_theme(saved_theme)
        self._apply_theme(saved_theme)

        # 刷新设置页面
        self._settings.refresh_server_table()
        self._settings.refresh_alert_table()
        self._analysis.refresh_server_list()

        # 启动定时刷新
        self._refresh_timer.start(5000)

        return True

    def _start_all(self):
        self._scheduler.start_all()
        self._update_monitor_state()
        self._status_bar.showMessage("已开始全部监控", 3000)

    def _stop_all(self):
        self._scheduler.stop_all()
        self._update_monitor_state()
        self._status_bar.showMessage("已停止全部监控", 3000)

    def _manual_refresh(self):
        self._dashboard.full_refresh()
        self._monitor.refresh_list()
        self._analysis.refresh_server_list()
        self._status_bar.showMessage("已刷新", 2000)

    def _on_snapshot(self, snapshot: ServerSnapshot):
        """处理采集到的快照"""
        cfg = self._state.get_config(snapshot.server_id)
        name = cfg.name if cfg else snapshot.server_id

        # 记录实际采集时间
        self._last_update_time = snapshot.timestamp

        # 更新各 Tab
        self._dashboard.update_snapshot(snapshot)
        self._monitor.update_snapshot(snapshot)

        # 告警评估
        self._alert_engine.evaluate(snapshot, name)

        # 更新状态栏
        self._update_status_bar()

    def _on_offline(self, server_id: str):
        # 服务器离线时，将其活跃告警标记为已恢复并刷新面板
        self._alert_engine.resolve_server_alerts(server_id)
        self._sync_alert_panel()
        self._update_status_bar()

    def _on_alert(self, alert):
        """处理新告警：刷新面板并弹出提示"""
        self._sync_alert_panel()

        # 弹窗提示
        level_text = "警告" if alert.level.value == "warning" else "严重"
        self._status_bar.showMessage(
            f"[{level_text}] {alert.message}", 5000
        )

    def _on_alert_resolved(self, alert):
        """处理告警恢复：刷新面板状态（已恢复 -> 绿色）"""
        self._sync_alert_panel()

    def _sync_alert_panel(self):
        """以历史记录为唯一数据源刷新告警面板与顶部滚动栏，保证状态与实际一致"""
        alerts = self._alert_engine.history.get_all()
        self._alert_panel.update_alerts(alerts)
        self._marquee.set_alerts(alerts)

    def _on_servers_changed(self):
        """服务器列表变更"""
        self._analysis.refresh_server_list()
        self._dashboard.full_refresh()
        self._monitor.refresh_list()
        self._update_monitor_state()

    def _on_interval_changed(self, interval: float):
        self._scheduler.set_interval(interval)
        self._status_bar.showMessage(f"轮询间隔已更新为 {interval:.0f} 秒", 3000)

    def _on_monitor_server_selected(self, server_id: str):
        pass  # 可扩展：加载进程列表等

    def _on_monitor_state_changed(self):
        """监控状态变更后的同步更新"""
        self._update_monitor_state()
        self._update_status_bar()
        # 同步刷新所有视图的监控状态显示
        self._dashboard.get_list_table().refresh()
        self._monitor.refresh_list()

    def _periodic_refresh(self):
        """定时刷新 UI"""
        self._dashboard.full_refresh()
        self._monitor.refresh_list()
        self._update_monitor_state()
        self._update_status_bar()

    def _update_status_bar(self):
        total = self._state.get_total_count()
        online = self._state.get_online_count()
        alerts = self._alert_engine.history.get_active_count()
        active = len(self._scheduler.get_active_ids())

        self._status_online.setText(f"在线: {online}/{total}")
        self._status_monitor.setText(f"监控: {active}/{total}")
        self._status_alerts.setText(f"告警: {alerts}")
        if self._last_update_time:
            self._status_update.setText(
                f"最后更新: {self._last_update_time.strftime('%H:%M:%S')}"
            )
        else:
            self._status_update.setText("最后更新: --")

    def _update_monitor_state(self):
        """刷新监控状态显示和工具栏按钮可用性"""
        self._dashboard.refresh_monitoring_state()
        active = len(self._scheduler.get_active_ids())
        total = self._state.get_total_count()
        self._start_action.setEnabled(active < total)
        self._stop_action.setEnabled(active > 0)

    def _apply_theme(self, theme: str):
        """切换主题样式"""
        from PyQt5.QtWidgets import QApplication
        import os

        styles_dir = os.path.join(
            os.path.dirname(__file__), "..", "assets", "styles"
        )
        qss_file = "dark.qss" if theme == "dark" else "light.qss"
        qss_path = os.path.join(styles_dir, qss_file)

        try:
            with open(qss_path, "r", encoding="utf-8") as f:
                stylesheet = f.read()
        except FileNotFoundError:
            self._status_bar.showMessage(f"主题文件未找到: {qss_file}", 3000)
            return

        # 应用全局样式
        QApplication.instance().setStyleSheet(stylesheet)

        # 重新应用仪表盘卡片和标签的主题样式
        self._dashboard.apply_theme(theme)

        # 跑马灯栏主题
        self._marquee.set_theme(theme)

        # 监控 Tab 中的仪表盘（环状进度条）主题
        self._monitor._cpu_gauge.set_theme(theme)
        self._monitor._mem_gauge.set_theme(theme)
        self._monitor._disk_gauge.set_theme(theme)

        # pyqtgraph 图表背景需要单独设置（它不走 QSS）
        bg_color = "#1e1e2e" if theme == "dark" else "#f5f5f5"
        fg_color = "#cccccc" if theme == "dark" else "#333333"
        grid_alpha = 0.3

        # 更新监控 Tab 中的图表背景
        for chart in [self._monitor._cpu_chart, self._monitor._mem_chart,
                      self._monitor._disk_chart, self._monitor._net_chart]:
            chart._plot_widget.setBackground(bg_color)
            # 更新坐标轴文字颜色
            for axis_name in ("left", "bottom"):
                axis = chart._plot_widget.getAxis(axis_name)
                axis.setPen(fg_color)
                axis.setTextPen(fg_color)

        # 强制刷新样式
        QApplication.instance().processEvents()

        theme_name = "暗色" if theme == "dark" else "亮色"
        self._status_bar.showMessage(f"已切换到{theme_name}主题", 3000)

    def closeEvent(self, event):
        """关闭时清理"""
        self._scheduler.shutdown()
        self._refresh_timer.stop()
        event.accept()
