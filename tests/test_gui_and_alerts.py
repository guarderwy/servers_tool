"""GUI 组件与告警引擎测试（无界面 offscreen 模式）

验证：
- ServerCard 多次刷新后样式字符串不再无限膨胀（修复前的 bug）
- ServerCard 从离线恢复在线后进度条文本恢复为百分比
- AlertEngine.evaluate 的防抖 / 触发 / 恢复逻辑
"""
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from server_monitor.ui.widgets.server_card import ServerCard
from server_monitor.core.models import (
    ServerConfig, ServerSnapshot, ServerStatus, CPUMetric, MemoryMetric,
    DiskMetric, DiskPartition, NetworkMetric, NetworkInterface,
)
from server_monitor.alerts.alert_engine import AlertEngine
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
        from server_monitor.alerts.rules import AlertRule
        eng.set_rules([AlertRule("cpu", "gte", 90.0, duration=1, level="critical")])
        eng.evaluate(_make_snapshot(offline=True), "web1")
        self.assertEqual(eng.history.get_active_count(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
