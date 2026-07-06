"""应用冒烟测试：无界面构造主窗口，捕获构造期错误"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

_APP = QApplication.instance() or QApplication([])


class TestAppSmoke(unittest.TestCase):
    def test_import_all_modules(self):
        """确保所有模块可被导入（捕获导入期语法/循环依赖错误）"""
        import importlib
        mods = [
            "server_monitor.main",
            "server_monitor.config",
            "server_monitor.core.models",
            "server_monitor.core.parser",
            "server_monitor.core.collector",
            "server_monitor.core.state_manager",
            "server_monitor.ssh.connection_pool",
            "server_monitor.ssh.executor",
            "server_monitor.ssh.credentials",
            "server_monitor.alerts.rules",
            "server_monitor.alerts.alert_engine",
            "server_monitor.alerts.history",
            "server_monitor.alerts.notifier",
            "server_monitor.ui.main_window",
            "server_monitor.ui.dashboard_tab",
            "server_monitor.ui.monitor_tab",
            "server_monitor.ui.analysis_tab",
            "server_monitor.ui.settings_tab",
            "server_monitor.ui.widgets.server_card",
            "server_monitor.ui.widgets.server_list_table",
            "server_monitor.ui.widgets.metric_chart",
            "server_monitor.ui.widgets.metric_gauge",
            "server_monitor.ui.widgets.alert_panel",
            "server_monitor.ui.widgets.login_dialog",
            "server_monitor.ui.widgets.disk_tree_widget",
            "server_monitor.ui.widgets.log_table_widget",
        ]
        for m in mods:
            importlib.import_module(m)

    def test_construct_main_window(self):
        """构造 MainWindow，确保各 Tab / 控件初始化无异常"""
        from server_monitor.ui.main_window import MainWindow
        w = MainWindow()
        self.assertIsNotNone(w._dashboard)
        self.assertIsNotNone(w._monitor)
        self.assertIsNotNone(w._analysis)
        self.assertIsNotNone(w._settings)
        # 模拟一次仪表盘刷新（无服务器）
        w._dashboard.full_refresh()
        w._monitor.refresh_list()
        w._update_status_bar()
        w.close()

    def test_construct_login_dialog(self):
        from server_monitor.ui.widgets.login_dialog import LoginDialog
        dlg = LoginDialog(is_first_run=True)
        self.assertFalse(dlg.confirmed)
        dlg2 = LoginDialog(is_first_run=False)
        self.assertIsNotNone(dlg2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
