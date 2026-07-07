"""ServerMonitor 业务逻辑测试套件

用于在不依赖真实服务器的前提下，验证命令解析、加密、格式化、模型、
规则引擎、状态管理等核心逻辑，并复现已知 bug。
"""
import os
import sys
import types
import unittest

# 让 server_monitor 包可被导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 无界面运行 Qt
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from server_monitor.core.parser import CommandParser
from server_monitor.core.models import (
    ServerConfig, CPUMetric, MemoryMetric, DiskMetric, DiskPartition,
    NetworkMetric, NetworkInterface, ProcessInfo, AuthLogEntry,
    ServerSnapshot, ServerStatus, AlertRecord, AlertLevel,
)
from server_monitor.utils.humanize import (
    humanize_bytes, humanize_bytes_per_sec, humanize_kb, humanize_mb, humanize_gb,
)
from server_monitor.utils.validators import (
    validate_host, validate_port, validate_username, validate_interval,
)
from server_monitor.utils.encryption import (
    encrypt_data, decrypt_data, encrypt_json, decrypt_json, derive_key,
)
from server_monitor.core.state_manager import StateManager
from server_monitor.alerts.rules import AlertRule
from server_monitor.alerts.history import AlertHistory


# ---------------------------------------------------------------------------
# 解析器测试
# ---------------------------------------------------------------------------

class TestParserCPU(unittest.TestCase):
    def setUp(self):
        self.p = CommandParser()

    def test_parse_cpu_normal(self):
        # 两次采样得到的使用率
        out = (
            "cpu  100 0 50 1000 0 0 0 0\n"
            "cpu  200 0 100 2000 0 0 0 0\n"
        )
        load = "0.50 0.10 0.05 1/200 12345\n"
        m = self.p.parse_cpu(out, load)
        self.assertIsNotNone(m)
        # delta = [100, 0, 50, 1000, 0, 0, 0, 0]; total = 1150
        # idle delta = 1000 -> idle ~87.0 ; usage ~13.0
        self.assertAlmostEqual(m.idle_percent, 87.0, places=1)
        self.assertAlmostEqual(m.usage_percent, 13.0, places=1)
        self.assertAlmostEqual(m.user_percent, (100 + 0) / 1150 * 100, places=1)
        self.assertAlmostEqual(m.system_percent, 50 / 1150 * 100, places=1)
        self.assertAlmostEqual(m.load_1m, 0.5, places=2)
        self.assertAlmostEqual(m.load_5m, 0.1, places=2)
        self.assertAlmostEqual(m.load_15m, 0.05, places=2)

    def test_parse_cpu_single_sample_returns_none(self):
        out = "cpu  100 0 50 1000 0 0 0 0\n"
        self.assertIsNone(self.p.parse_cpu(out))

    def test_parse_cpu_idle(self):
        # 完全空闲
        out = (
            "cpu  0 0 0 1000 0 0 0 0\n"
            "cpu  0 0 0 2000 0 0 0 0\n"
        )
        m = self.p.parse_cpu(out)
        self.assertAlmostEqual(m.usage_percent, 0.0, places=1)
        self.assertAlmostEqual(m.idle_percent, 100.0, places=1)

    def test_parse_cpu_per_core(self):
        out = (
            "cpu0 100 0 0 900 0 0 0 0\n"
            "cpu1 0 0 0 1000 0 0 0 0\n"
        )
        cores = self.p.parse_cpu_per_core(out)
        self.assertEqual(cores, [10.0, 0.0])


class TestParserMemory(unittest.TestCase):
    def setUp(self):
        self.p = CommandParser()

    def test_parse_memory(self):
        out = (
            "MemTotal:       16384000 kB\n"
            "MemFree:         2000000 kB\n"
            "MemAvailable:   10000000 kB\n"
            "Buffers:          500000 kB\n"
            "Cached:          3000000 kB\n"
        )
        m = self.p.parse_memory(out)
        self.assertAlmostEqual(m.total_mb, 16384000 / 1024, places=1)
        # usage = (total - available)/total*100
        self.assertAlmostEqual(m.usage_percent, (16384000 - 10000000) / 16384000 * 100, places=1)
        # round(x/1024, 1) 使用银行家舍入，允许 0.1MB 误差
        self.assertAlmostEqual(m.available_mb, 10000000 / 1024, places=1)
        self.assertAlmostEqual(m.cached_mb, 3000000 / 1024, places=1)
        self.assertAlmostEqual(m.buffers_mb, 500000 / 1024, places=1)

    def test_parse_memory_no_available(self):
        out = (
            "MemTotal:       16384000 kB\n"
            "MemFree:         2000000 kB\n"
            "Buffers:          500000 kB\n"
            "Cached:          3000000 kB\n"
        )
        m = self.p.parse_memory(out)
        # available 回退到 free
        self.assertAlmostEqual(m.available_mb, 2000000 / 1024, places=1)
        # used 回退计算
        self.assertAlmostEqual(m.used_mb, (16384000 - 2000000 - 500000 - 3000000) / 1024, places=1)


class TestParserDisk(unittest.TestCase):
    def setUp(self):
        self.p = CommandParser()

    def test_parse_disk(self):
        out = (
            "Filesystem     Type 1K-blocks     Used Available Use% Mounted on\n"
            "/dev/sda1      ext4 102684600 55231700  42084000  57% /\n"
            "tmpfs          tmpfs   8192000        0   8192000   0% /dev/shm\n"
            "/dev/sdb1      xfs   51200000 10000000  41200000  20% /data\n"
        )
        m = self.p.parse_disk(out)
        self.assertEqual(len(m.partitions), 2)  # tmpfs 被忽略
        # 第一个为 /dev/sda1
        p0 = m.partitions[0]
        self.assertEqual(p0.device, "/dev/sda1")
        self.assertEqual(p0.filesystem, "ext4")
        self.assertEqual(p0.mount_point, "/")
        self.assertAlmostEqual(p0.total_gb, 102684600 / 1024 / 1024, places=2)
        self.assertAlmostEqual(p0.usage_percent, 57.0, places=1)

    def test_parse_disk_use_percent_dash(self):
        out = (
            "Filesystem     Type 1K-blocks     Used Available Use% Mounted on\n"
            "/dev/sda1      ext4 102684600 55231700  42084000   - /some\n"
        )
        m = self.p.parse_disk(out)
        self.assertEqual(len(m.partitions), 1)
        self.assertEqual(m.partitions[0].usage_percent, 0.0)


class TestParserNetwork(unittest.TestCase):
    def setUp(self):
        self.p = CommandParser()

    def test_parse_network(self):
        out = (
            "Inter-|   Receive                                                |  Transmit\n"
            " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed\n"
            "    lo:    1000       10    0    0    0     0          0         0     1000       10    0    0    0     0       0          0\n"
            "  eth0: 1000000     5000    0    0    0     0          0         0  500000     2500    0    0    0     0       0          0\n"
        )
        ss = "Total: 100 (kernel 120)\nTCP: 50 (estab 30, closed 10, orphaned 1, timewait 5)\n"
        m = self.p.parse_network(out, ss)
        self.assertEqual(len(m.interfaces), 1)  # lo 被忽略
        eth = m.interfaces[0]
        self.assertEqual(eth.name, "eth0")
        self.assertEqual(eth.rx_bytes, 1000000)
        self.assertEqual(eth.tx_bytes, 500000)
        self.assertEqual(eth.rx_packets, 5000)
        self.assertEqual(eth.tx_packets, 2500)
        self.assertEqual(m.tcp_total, 50)
        self.assertEqual(m.tcp_established, 30)

    def test_parse_connection_ips(self):
        out = (
            "State      Recv-Q Send-Q Local Address:Port               Peer Address:Port\n"
            "ESTAB      0      0      10.0.0.1:22                      203.0.113.5:51012\n"
            "ESTAB      0      0      10.0.0.1:22                      203.0.113.5:51013\n"
            "SYN-RECV   0      0      10.0.0.1:22                      198.51.100.23:41234\n"
            "ESTAB      0      0      10.0.0.1:22                      198.51.100.23:41235\n"
            "ESTAB      0      0      10.0.0.1:22                      192.0.2.50:33000\n"
            "ESTAB      0      0      10.0.0.1:3306                   192.0.2.50:33001\n"
            "ESTAB      0      0      10.0.0.1:22                     [2001:db8::1]:54432\n"
            "LISTEN     0      128    :::22                            :::*\n"
            "ESTAB      0      0      127.0.0.1:6379                   127.0.0.1:55555\n"
        )
        conns = self.p.parse_connection_ips(out)
        ips = [c.ip for c in conns]
        self.assertIn("203.0.113.5", ips)
        self.assertIn("198.51.100.23", ips)
        self.assertIn("192.0.2.50", ips)
        self.assertIn("2001:db8::1", ips)  # IPv6 带方括号解析
        self.assertNotIn("127.0.0.1", ips)  # 回环排除
        # 各来源连接数：IPv4 各 2 条，IPv6 仅 1 条
        counts = {c.ip: c.count for c in conns}
        self.assertEqual(counts["203.0.113.5"], 2)
        self.assertEqual(counts["198.51.100.23"], 2)
        self.assertEqual(counts["192.0.2.50"], 2)
        self.assertEqual(counts["2001:db8::1"], 1)
        # top_n 限制生效
        self.assertEqual(len(self.p.parse_connection_ips(out, top_n=2)), 2)

    def test_parse_connection_ips_empty(self):
        self.assertEqual(self.p.parse_connection_ips(""), [])
        # 仅监听/表头，无具体对端
        self.assertEqual(self.p.parse_connection_ips("State Recv-Q foo\nLISTEN 0 0 :::22 :::*"), [])


class TestParserProcess(unittest.TestCase):
    def setUp(self):
        self.p = CommandParser()

    def test_parse_processes(self):
        out = (
            "USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND\n"
            "root         1  0.0  0.1  22568   1234 ?        Ss   Jul06   0:01 /sbin/init\n"
            "mysql      123  5.2  12.3 102400  45678 ?        Sl   Jul06   2:30 /usr/sbin/mysqld --defaults\n"
        )
        procs = self.p.parse_processes(out)
        self.assertEqual(len(procs), 2)
        p1 = procs[1]
        self.assertEqual(p1.pid, 123)
        self.assertEqual(p1.user, "mysql")
        self.assertAlmostEqual(p1.cpu_percent, 5.2)
        self.assertAlmostEqual(p1.mem_percent, 12.3)
        self.assertEqual(p1.mem_rss_kb, 45678.0)
        self.assertEqual(p1.status, "Sl")
        self.assertEqual(p1.command, "/usr/sbin/mysqld --defaults")


class TestParserAuthLog(unittest.TestCase):
    def setUp(self):
        self.p = CommandParser()

    def test_parse_auth_accepted(self):
        out = (
            "Jul  6 12:00:05 hostname sshd[1234]: Accepted password for alice from 10.0.0.1 port 52234 ssh2\n"
        )
        entries = self.p.parse_auth_log(out)
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual(e.event_type, "accepted")
        self.assertEqual(e.user, "alice")
        self.assertEqual(e.source_ip, "10.0.0.1")
        self.assertEqual(e.port, 52234)

    def test_parse_auth_failed(self):
        out = (
            "Jul  6 12:05:10 hostname sshd[2222]: Failed password for root from 192.168.1.5 port 44444 ssh2\n"
            "Jul  6 12:05:15 hostname sshd[2223]: Failed password for invalid user bob from 8.8.8.8 port 55555 ssh2\n"
        )
        entries = self.p.parse_auth_log(out)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].user, "root")
        self.assertEqual(entries[1].user, "bob")
        self.assertEqual(entries[1].source_ip, "8.8.8.8")

    def test_parse_syslog_time_double_space(self):
        # syslog 单数字日期用两个空格填充："Jul  6 12:00:05"
        line = "Jul  6 12:00:05 hostname sshd[1234]: Accepted password for alice from 10.0.0.1 port 52234 ssh2\n"
        e = self.p.parse_auth_log(line)[0]
        # 时间解析成功，年份为当前年，月份为 7，日为 6
        self.assertEqual(e.timestamp.month, 7)
        self.assertEqual(e.timestamp.day, 6)
        self.assertEqual(e.timestamp.hour, 12)


# ---------------------------------------------------------------------------
# 格式化 / 校验测试
# ---------------------------------------------------------------------------

class TestHumanize(unittest.TestCase):
    def test_bytes(self):
        self.assertEqual(humanize_bytes(0), "0.0 B")
        self.assertEqual(humanize_bytes(1023), "1023.0 B")
        self.assertEqual(humanize_bytes(1024), "1.0 KB")
        self.assertEqual(humanize_bytes(1024 * 1024), "1.0 MB")
        self.assertEqual(humanize_bytes(1024 ** 3), "1.0 GB")
        self.assertEqual(humanize_bytes(1024 ** 4), "1.0 TB")

    def test_bytes_none(self):
        self.assertEqual(humanize_bytes(None), "--")

    def test_per_sec(self):
        self.assertTrue(humanize_bytes_per_sec(2048).endswith("/s"))

    def test_negative(self):
        # 负值应安全处理（不应抛异常）
        self.assertIn("B", humanize_bytes(-500))


class TestValidators(unittest.TestCase):
    def test_validate_host(self):
        self.assertIsNone(validate_host("192.168.1.1"))
        self.assertIsNone(validate_host("example.com"))
        self.assertIsNone(validate_host("sub.example.co.uk"))
        self.assertIsNotNone(validate_host("256.1.1.1"))   # 非法 IP
        self.assertIsNotNone(validate_host(""))
        self.assertIsNotNone(validate_host("   "))
        self.assertIsNotNone(validate_host("not a host"))

    def test_validate_port(self):
        self.assertIsNone(validate_port(22))
        self.assertIsNone(validate_port("22"))
        self.assertIsNotNone(validate_port(0))
        self.assertIsNotNone(validate_port(70000))
        self.assertIsNotNone(validate_port("abc"))

    def test_validate_username(self):
        self.assertIsNone(validate_username("root"))
        self.assertIsNone(validate_username("deploy_user-1"))
        self.assertIsNotNone(validate_username("1bad"))  # 不能以数字开头
        self.assertIsNotNone(validate_username(""))

    def test_validate_interval(self):
        self.assertIsNone(validate_interval(5))
        self.assertIsNone(validate_interval("3"))
        self.assertIsNotNone(validate_interval(2))
        self.assertIsNotNone(validate_interval(61))


# ---------------------------------------------------------------------------
# 加密测试
# ---------------------------------------------------------------------------

class TestEncryption(unittest.TestCase):
    def test_roundtrip(self):
        secret = "super-secret-master-password"
        data = "hello world 你好"
        enc = encrypt_data(data, secret)
        self.assertNotEqual(enc, data)
        self.assertEqual(decrypt_data(enc, secret), data)

    def test_wrong_password_fails(self):
        enc = encrypt_data("data", "right")
        with self.assertRaises(Exception):
            decrypt_data(enc, "wrong")

    def test_json_roundtrip(self):
        obj = {"a": 1, "b": ["x", "y"], "c": {"k": "v"}}
        enc = encrypt_json(obj, "pw")
        self.assertEqual(decrypt_json(enc, "pw"), obj)

    def test_unique_iv(self):
        # 相同明文两次加密结果应不同（随机 salt/nonce）
        e1 = encrypt_data("same", "pw")
        e2 = encrypt_data("same", "pw")
        self.assertNotEqual(e1, e2)


# ---------------------------------------------------------------------------
# 模型 / 规则 / 历史测试
# ---------------------------------------------------------------------------

class TestModels(unittest.TestCase):
    def test_server_config_roundtrip(self):
        cfg = ServerConfig(
            id="s1", name="web1", host="10.0.0.1", port=2222,
            username="deploy", auth_type="key", key_path="/k",
            tags=["web"], enabled=True,
        )
        d = cfg.to_dict()
        cfg2 = ServerConfig.from_dict(d)
        self.assertEqual(cfg2.id, "s1")
        self.assertEqual(cfg2.port, 2222)
        self.assertEqual(cfg2.tags, ["web"])
        # 敏感字段不应出现在 to_dict
        self.assertNotIn("password", d)
        self.assertNotIn("key_path", d)


class TestAlertRule(unittest.TestCase):
    def test_matches(self):
        r = AlertRule(metric="cpu", condition="gte", threshold=90.0)
        self.assertTrue(r.matches(90.0))
        self.assertTrue(r.matches(95.0))
        self.assertFalse(r.matches(89.9))
        r2 = AlertRule(metric="cpu", condition="gt", threshold=90.0)
        self.assertFalse(r2.matches(90.0))
        self.assertTrue(r2.matches(90.1))
        r3 = AlertRule(metric="cpu", condition="lt", threshold=10.0)
        self.assertTrue(r3.matches(5.0))
        r4 = AlertRule(metric="cpu", condition="eq", threshold=50.0)
        self.assertTrue(r4.matches(50.0))
        self.assertFalse(r4.matches(50.5))


class TestAlertHistory(unittest.TestCase):
    def test_resolve_by_rule(self):
        h = AlertHistory()
        a1 = AlertRecord(
            id="1", server_id="s1", server_name="web1",
            rule_name="cpu gte 90", level=AlertLevel.CRITICAL,
            metric="cpu", current_value=95.0, threshold=90.0,
            message="x", triggered_at=__import__("datetime").datetime.now(),
        )
        h.add(a1)
        self.assertEqual(h.get_active_count(), 1)
        h.resolve_by_rule("s1", "cpu", "critical")
        self.assertEqual(h.get_active_count(), 0)
        self.assertTrue(h.get_active()[0].is_resolved if False else a1.is_resolved)


# ---------------------------------------------------------------------------
# 状态管理测试
# ---------------------------------------------------------------------------

class TestStateManager(unittest.TestCase):
    def test_network_rate(self):
        sm = StateManager()
        cfg = ServerConfig(id="s1", name="web1", host="10.0.0.1")
        sm.update_config(cfg)

        import datetime
        # 第一次：速率为 0
        n1 = NetworkMetric(
            timestamp=datetime.datetime(2026, 1, 1, 0, 0, 0),
            interfaces=[NetworkInterface(name="eth0", rx_bytes=1000, tx_bytes=500)],
        )
        snap1 = ServerSnapshot(server_id="s1", timestamp=n1.timestamp, status=ServerStatus.ONLINE, network=n1)
        sm.update_snapshot(snap1)
        self.assertEqual(sm.get_snapshot("s1").network.rx_rate, 0.0)

        # 1 秒后累计到 3000 -> 速率 2000 B/s
        n2 = NetworkMetric(
            timestamp=datetime.datetime(2026, 1, 1, 0, 0, 1),
            interfaces=[NetworkInterface(name="eth0", rx_bytes=3000, tx_bytes=1500)],
        )
        snap2 = ServerSnapshot(server_id="s1", timestamp=n2.timestamp, status=ServerStatus.ONLINE, network=n2)
        sm.update_snapshot(snap2)
        self.assertAlmostEqual(sm.get_snapshot("s1").network.rx_rate, 2000.0, places=3)
        self.assertAlmostEqual(sm.get_snapshot("s1").network.tx_rate, 1000.0, places=3)

    def test_counts(self):
        sm = StateManager()
        sm.update_config(ServerConfig(id="a", name="a", host="h"))
        sm.update_config(ServerConfig(id="b", name="b", host="h"))
        # 未采集 -> 离线
        self.assertEqual(sm.get_total_count(), 2)
        self.assertEqual(sm.get_online_count(), 0)
        self.assertEqual(sm.get_alert_count(), 0)
        off = sm.get_all_snapshots()
        self.assertTrue(all(s.status == ServerStatus.OFFLINE for s in off))


if __name__ == "__main__":
    unittest.main(verbosity=2)
