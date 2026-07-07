"""GUI 组件与告警引擎测试（无界面 offscreen 模式）

验证：
- ServerCard 多次刷新后样式字符串不再无限膨胀（修复前的 bug）
- ServerCard 从离线恢复在线后进度条文本恢复为百分比
- AlertEngine.evaluate 的防抖 / 触发 / 恢复逻辑
- 告警恢复时面板状态应更新为「已恢复」（修复前一直显示「活跃」的 bug）
- 告警引擎在恢复 / 离线时应发出信号，UI 才能正确刷新
- 同指标已有 critical 告警活跃时不再触发 warning（规则优化）
"""
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication
from PyQt5.QtTest import QSignalSpy

from server_monitor.ui.widgets.server_card import ServerCard
from server_monitor.alerts.alert_engine import AlertEngine
from server_monitor.alerts.rules import AlertRule
from server_monitor.alerts.rules import AlertRule
from server_monitor.ui.widgets.alert_panel import AlertPanel
from server_monitor.ui.widgets.conn_ip_table import ConnIPTable
from server_monitor.ui.widgets.marquee_bar import MarqueeBar
from server_monitor.core.models import (
    ServerConfig, ServerSnapshot, ServerStatus, AlertLevel, AlertRecord,
    CPUMetric, MemoryMetric, DiskMetric, DiskPartition, NetworkMetric,
    NetworkInterface, IPConnectionCount,
)
from server_monitor.core.state_manager import StateManager

_APP = QApplication.instance() or QApplication([])


def _make_snapshot(server_id="s1", cpu=10.0, mem=10.0, disk=10.0, offline=False):
    ts = datetime(2026, 1, 1, 0, 0, 0)
    if offline:
        return ServerSnapshot(
            server_id=server_id, timestamp=ts, status=ServerStatus.OFFLINE,
        )
    return ServerSnapshot(
        server_id=server_id,
        timestamp=ts,
        status=ServerStatus.ONLINE,
        cpu=CPUMetric(
            timestamp=ts, usage_percent=cpu, user_percent=cpu / 2,
            system_percent=cpu / 2, idle_percent=100 - cpu,
        ),
        memory=MemoryMetric(
            timestamp=ts, total_mb=1000, used_mb=mem * 10,
            free_mb=1000 - mem * 10, available_mb=1000 - mem * 10,
            cached_mb=0, buffers_mb=0, usage_percent=mem,
        ),
        disk=DiskMetric(timestamp=ts, partitions=[
            DiskPartition(filesystem="ext4", device="/dev/sda1",
                          total_gb=100, used_gb=disk, available_gb=100 - disk,
                          usage_percent=disk, mount_point="/"),
        ]),
        network=NetworkMetric(timestamp=ts, interfaces=[
            NetworkInterface(name="eth0", rx_bytes=1000, tx_bytes=500),
        ]),
    )


class TestServerCard(unittest.TestCase):
    def test_style_sheet_not_grow(self):
        """多次刷新后进度条样式字符串长度应保持稳定（不无限膨胀）"""
        card = ServerCard()
        cfg = ServerConfig(id="s1", name="web1", host="10.0.0.1")
        snap = _make_snapshot(cpu=10, mem=10, disk=10)
        card.update_snapshot(snap, cfg)
        bar = card._bar_cpu
        base_len = len(bar.styleSheet())

        # 连续刷新 50 次（模拟轮询）
        for _ in range(50):
            card.update_snapshot(_make_snapshot(cpu=95, mem=95, disk=95), cfg)

        grown = len(bar.styleSheet())
        self.assertLessEqual(grown, base_len + 50,
                             "样式字符串不应随刷新次数无限增长")
        # 关键：不应包含数十个重复 chunk 规则
        self.assertLessEqual(bar.styleSheet().count("QProgressBar::chunk"),
                             2, "样式中 chunk 规则应只出现一次（基础 1 + 内联 1）")

    def test_offline_then_online_resets_format(self):
        """离线 -> 在线 后，进度条文本应恢复为百分比而非 '离线'"""
        card = ServerCard()
        cfg = ServerConfig(id="s1", name="web1", host="10.0.0.1")
        card.update_snapshot(_make_snapshot(offline=True), cfg)
        self.assertEqual(card._bar_cpu.format(), "离线")

        card.update_snapshot(_make_snapshot(cpu=50, mem=50, disk=50), cfg)
        self.assertEqual(card._bar_cpu.format(), "%p%")


class TestAlertEngine(unittest.TestCase):
    def test_trigger_after_duration(self):
        eng = AlertEngine()
        # 仅保留一条 critical cpu 规则，duration=3
        from server_monitor.alerts.rules import AlertRule
        eng.set_rules([AlertRule("cpu", "gte", 90.0, duration=3, level="critical")])

        snap = _make_snapshot(cpu=95)
        for _ in range(2):
            eng.evaluate(snap, "web1")
        self.assertEqual(eng.history.get_active_count(), 0, "未达到持续次数前不应触发")

        eng.evaluate(snap, "web1")
        self.assertEqual(eng.history.get_active_count(), 1, "达到持续次数后应触发")

    def test_recover_after_duration(self):
        eng = AlertEngine()
        from server_monitor.alerts.rules import AlertRule
        eng.set_rules([AlertRule("cpu", "gte", 90.0, duration=2, level="critical")])

        snap_hi = _make_snapshot(cpu=95)
        snap_lo = _make_snapshot(cpu=10)
        eng.evaluate(snap_hi, "web1")
        eng.evaluate(snap_hi, "web1")  # 触发
        self.assertEqual(eng.history.get_active_count(), 1)

        eng.evaluate(snap_lo, "web1")  # 1 次不满足
        self.assertEqual(eng.history.get_active_count(), 1, "恢复计数未达阈值，仍活跃")
        eng.evaluate(snap_lo, "web1")  # 2 次不满足 -> 恢复
        self.assertEqual(eng.history.get_active_count(), 0, "连续不满足应恢复")

    def test_no_duplicate_active(self):
        eng = AlertEngine()
        from server_monitor.alerts.rules import AlertRule
        eng.set_rules([AlertRule("cpu", "gte", 90.0, duration=1, level="critical")])

        snap = _make_snapshot(cpu=95)
        eng.evaluate(snap, "web1")
        eng.evaluate(snap, "web1")  # 再次满足，不应重复
        self.assertEqual(eng.history.get_active_count(), 1)

    def test_offline_skipped(self):
        eng = AlertEngine()
        eng.set_rules([AlertRule("cpu", "gte", 90.0, duration=1, level="critical")])
        eng.evaluate(_make_snapshot(offline=True), "web1")
        self.assertEqual(eng.history.get_active_count(), 0)


class TestAlertResolution(unittest.TestCase):
    def test_recover_emits_resolved_signal(self):
        """告警恢复时应发出 alert_resolved 信号（驱动 UI 刷新）"""
        eng = AlertEngine()
        eng.set_rules([AlertRule("cpu", "gte", 90.0, duration=1, level="critical")])
        spy = QSignalSpy(eng.notifier.alert_resolved)

        eng.evaluate(_make_snapshot(cpu=95), "web1")  # 触发
        self.assertEqual(eng.history.get_active_count(), 1)
        self.assertEqual(len(spy), 0, "触发阶段不应发恢复信号")

        eng.evaluate(_make_snapshot(cpu=10), "web1")  # 恢复
        self.assertEqual(eng.history.get_active_count(), 0)
        self.assertEqual(len(spy), 1, "恢复时应恰好发出一次 alert_resolved")

    def test_panel_shows_resolved_after_recovery(self):
        """告警面板在告警恢复后应显示「已恢复」而非一直「活跃」"""
        eng = AlertEngine()
        eng.set_rules([AlertRule("cpu", "gte", 90.0, duration=1, level="critical")])

        eng.evaluate(_make_snapshot(cpu=95), "web1")  # 触发
        eng.evaluate(_make_snapshot(cpu=10), "web1")  # 恢复

        # 关键：UI 必须从 history 重新渲染，才能反映已恢复状态
        panel = AlertPanel()
        panel.update_alerts(eng.history.get_all())

        self.assertEqual(panel._table.rowCount(), 1)
        status_item = panel._table.item(0, 5)
        self.assertEqual(status_item.text(), "已恢复")
        self.assertEqual(panel.get_active_count(), 0)

    def test_offline_resolves_active_alerts(self):
        """服务器离线时应将其活跃告警标记为已恢复"""
        eng = AlertEngine()
        eng.set_rules([AlertRule("cpu", "gte", 90.0, duration=1, level="critical")])
        spy = QSignalSpy(eng.notifier.alert_resolved)

        eng.evaluate(_make_snapshot(cpu=95), "web1")  # 触发
        self.assertEqual(eng.history.get_active_count(), 1)

        resolved = eng.resolve_server_alerts("s1")
        self.assertEqual(len(resolved), 1)
        self.assertEqual(eng.history.get_active_count(), 0)
        self.assertEqual(len(spy), 1, "离线恢复应发信号")

    def test_warning_suppressed_while_critical_active(self):
        """同指标已有 critical 告警活跃时，不重复触发 warning（规则优化）"""
        eng = AlertEngine()
        eng.set_rules([
            AlertRule("cpu", "gte", 90.0, duration=1, level="critical"),
            AlertRule("cpu", "gte", 80.0, duration=1, level="warning"),
        ])
        eng.evaluate(_make_snapshot(cpu=95), "web1")  # 同时满足两条规则

        active = eng.history.get_active()
        self.assertEqual(len(active), 1, "不应同时产生 warning 与 critical 两条")
        self.assertEqual(active[0].level, AlertLevel.CRITICAL)


class TestRuleChangeClearsAlerts(unittest.TestCase):
    """用户修改/禁用/删除规则后，旧告警应被自动清除（本次修复核心诉求）"""

    def _trigger_cpu_critical(self, eng):
        eng.set_rules([AlertRule("cpu", "gte", 90.0, duration=1, level="critical")])
        eng.evaluate(_make_snapshot(cpu=95), "web1")
        self.assertEqual(eng.history.get_active_count(), 1)

    def test_disabling_rule_clears_alert(self):
        """禁用规则后，原活跃告警应被清除并发出恢复信号"""
        eng = AlertEngine()
        spy = QSignalSpy(eng.notifier.alert_resolved)
        self._trigger_cpu_critical(eng)

        eng.set_rules([AlertRule("cpu", "gte", 90.0, duration=1,
                                 level="critical", enabled=False)])
        self.assertEqual(eng.history.get_active_count(), 0, "禁用后旧告警应清除")
        self.assertEqual(len(spy), 1, "应发出恢复信号驱动 UI 刷新")

    def test_raising_threshold_clears_alert(self):
        """放宽阈值（提高）后当前值不再越界，旧告警应清除"""
        eng = AlertEngine()
        spy = QSignalSpy(eng.notifier.alert_resolved)
        self._trigger_cpu_critical(eng)

        eng.set_rules([AlertRule("cpu", "gte", 99.0, duration=1, level="critical")])
        self.assertEqual(eng.history.get_active_count(), 0, "阈值放宽后旧告警应清除")
        self.assertEqual(len(spy), 1)

    def test_still_violating_keeps_alert(self):
        """阈值改得更严但仍被违反时，告警应保持活跃（不误清）"""
        eng = AlertEngine()
        self._trigger_cpu_critical(eng)  # cpu=95, 原规则 >=90

        eng.set_rules([AlertRule("cpu", "gte", 80.0, duration=1, level="critical")])
        self.assertEqual(eng.history.get_active_count(), 1, "仍越界不应清除")

    def test_unrelated_active_alert_kept(self):
        """修改某条规则不应清除其它指标的活跃告警"""
        eng = AlertEngine()
        eng.set_rules([
            AlertRule("cpu", "gte", 90.0, duration=1, level="critical"),
            AlertRule("memory", "gte", 90.0, duration=1, level="critical"),
        ])
        eng.evaluate(_make_snapshot(cpu=95, mem=95), "web1")
        self.assertEqual(eng.history.get_active_count(), 2)

        eng.set_rules([
            AlertRule("cpu", "gte", 90.0, duration=1, level="critical",
                      enabled=False),
            AlertRule("memory", "gte", 90.0, duration=1, level="critical"),
        ])
        self.assertEqual(eng.history.get_active_count(), 1, "只清除 cpu 告警")
        self.assertEqual(eng.history.get_active()[0].metric, "memory")


class TestConnIPTable(unittest.TestCase):
    def test_renders_top5_with_counts(self):
        table = ConnIPTable(top_n=5)
        conns = [
            IPConnectionCount(ip="203.0.113.5", count=120),
            IPConnectionCount(ip="198.51.100.23", count=80),
            IPConnectionCount(ip="192.0.2.50", count=50),
            IPConnectionCount(ip="10.0.0.9", count=10),
            IPConnectionCount(ip="10.0.0.10", count=2),
            IPConnectionCount(ip="10.0.0.11", count=1),  # 超出 top_n 应被截断
        ]
        table.update_data(conns)
        self.assertEqual(table._table.rowCount(), 5, "只显示前 5 条")
        # 第一行应为连接数最多的 IP
        self.assertEqual(table._table.item(0, 0).text(), "203.0.113.5")
        self.assertEqual(table._table.item(0, 1).text(), "120")
        # 第二行
        self.assertEqual(table._table.item(1, 0).text(), "198.51.100.23")
        self.assertEqual(table._table.item(1, 1).text(), "80")

    def test_empty_shows_placeholder(self):
        table = ConnIPTable(top_n=5)
        table.update_data([])
        self.assertEqual(table._table.rowCount(), 1)
        self.assertEqual(table._table.item(0, 0).text(), "暂无连接数据")


class TestMarqueeBar(unittest.TestCase):
    """顶部滚动告警栏：只滚动活跃告警，恢复后移除"""

    def _make_record(self, message, level="critical", resolved=False):
        rec = AlertRecord(
            id="x1", server_id="s1", server_name="web1",
            rule_name="cpu gte 90", level=AlertLevel(level),
            metric="cpu", current_value=95.0, threshold=90.0,
            message=message, triggered_at=datetime(2026, 1, 1, 0, 0, 0),
        )
        rec.is_resolved = resolved
        return rec

    def test_active_starts_scrolling(self):
        bar = MarqueeBar()
        bar.set_alerts([self._make_record("[web1] CPU = 95.0, 阈值 90.0")])
        self.assertTrue(bar._timer.isActive(), "有活跃告警应开始滚动")
        self.assertIn("CPU = 95.0", bar._label.text())
        self.assertNotIn("当前无活跃告警", bar._label.text())

    def test_resolved_only_stops_scrolling(self):
        bar = MarqueeBar()
        bar.set_alerts([self._make_record("x", resolved=True)])
        self.assertFalse(bar._timer.isActive(), "只有已恢复告警不应滚动")
        self.assertIn("当前无活跃告警", bar._label.text())

    def test_only_active_included(self):
        bar = MarqueeBar()
        active = self._make_record("[web1] CPU = 95.0, 阈值 90.0")
        resolved = self._make_record("[web1] MEM = 92.0, 阈值 90.0",
                                     level="warning", resolved=True)
        bar.set_alerts([active, resolved])
        # 滚动文本只包含活跃告警，不含已恢复的 MEM
        self.assertIn("CPU = 95.0", bar._label.text())
        self.assertNotIn("MEM = 92.0", bar._label.text())

    def test_recover_removes_from_scroll(self):
        bar = MarqueeBar()
        bar.set_alerts([self._make_record("[web1] CPU = 95.0, 阈值 90.0")])
        self.assertTrue(bar._timer.isActive())
        # 告警恢复后再次刷新，应停止滚动并回到占位
        bar.set_alerts([self._make_record("x", resolved=True)])
        self.assertFalse(bar._timer.isActive())
        self.assertIn("当前无活跃告警", bar._label.text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
