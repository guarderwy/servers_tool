"""命令输出解析器 —— 将 shell 输出解析为结构化 dataclass"""

import re
import logging
from datetime import datetime
from typing import Optional

from .models import (
    CPUMetric, MemoryMetric, DiskMetric, DiskPartition,
    NetworkMetric, NetworkInterface, ProcessInfo, AuthLogEntry,
)
from ..config import DISK_IGNORE_FS, NETWORK_IGNORE_IFACES

logger = logging.getLogger(__name__)


class CommandParser:
    """解析各种 Linux 命令的输出"""

    # ========== CPU ==========

    def parse_cpu(self, output: str, load_output: str = "") -> Optional[CPUMetric]:
        """
        解析 /proc/stat 两次采样的差值计算 CPU 使用率。
        output: 两次 head -1 /proc/stat 的结果
        """
        lines = [l for l in output.strip().splitlines() if l.startswith("cpu ")]
        if len(lines) < 2:
            return None

        def parse_stat_line(line):
            parts = line.split()
            # cpu user nice system idle iowait irq softirq steal
            vals = [int(x) for x in parts[1:]]
            while len(vals) < 8:
                vals.append(0)
            return vals

        v1 = parse_stat_line(lines[0])
        v2 = parse_stat_line(lines[1])

        deltas = [v2[i] - v1[i] for i in range(len(v1))]
        total = sum(deltas)
        if total == 0:
            idle_pct = 100.0
            user_pct = system_pct = 0.0
        else:
            idle_pct = deltas[3] / total * 100
            user_pct = (deltas[0] + deltas[1]) / total * 100  # user + nice
            system_pct = deltas[2] / total * 100

        usage = 100.0 - idle_pct

        # 解析负载
        load_1m = load_5m = load_15m = 0.0
        if load_output:
            parts = load_output.strip().split()
            if len(parts) >= 3:
                try:
                    load_1m = float(parts[0])
                    load_5m = float(parts[1])
                    load_15m = float(parts[2])
                except ValueError:
                    pass

        return CPUMetric(
            timestamp=datetime.now(),
            usage_percent=round(usage, 1),
            user_percent=round(user_pct, 1),
            system_percent=round(system_pct, 1),
            idle_percent=round(idle_pct, 1),
            load_1m=load_1m,
            load_5m=load_5m,
            load_15m=load_15m,
        )

    def parse_cpu_per_core(self, output: str) -> list[float]:
        """解析各核心使用率"""
        cores = {}
        for line in output.strip().splitlines():
            m = re.match(r"cpu(\d+)\s+(.*)", line)
            if m:
                core_id = int(m.group(1))
                vals = [int(x) for x in m.group(2).split()]
                total = sum(vals)
                idle = vals[3] if len(vals) > 3 else 0
                usage = (1.0 - idle / total) * 100 if total else 0
                cores[core_id] = round(usage, 1)
        return [cores[k] for k in sorted(cores.keys())]

    # ========== 内存 ==========

    def parse_memory(self, output: str) -> Optional[MemoryMetric]:
        """解析 /proc/meminfo 输出"""
        info = {}
        for line in output.strip().splitlines():
            m = re.match(r"(\w+):\s+(\d+)", line)
            if m:
                info[m.group(1)] = int(m.group(2))  # kB

        total = info.get("MemTotal", 0)
        free = info.get("MemFree", 0)
        available = info.get("MemAvailable", free)
        buffers = info.get("Buffers", 0)
        cached = info.get("Cached", 0)
        used = total - free - buffers - cached
        if used < 0:
            used = total - free

        usage_pct = (total - available) / total * 100 if total else 0

        return MemoryMetric(
            timestamp=datetime.now(),
            total_mb=round(total / 1024, 1),
            used_mb=round(used / 1024, 1),
            free_mb=round(free / 1024, 1),
            available_mb=round(available / 1024, 1),
            cached_mb=round(cached / 1024, 1),
            buffers_mb=round(buffers / 1024, 1),
            usage_percent=round(usage_pct, 1),
        )

    # ========== 磁盘 ==========

    def parse_disk(self, output: str) -> Optional[DiskMetric]:
        """解析 df -kT 输出"""
        partitions = []
        for line in output.strip().splitlines()[1:]:  # 跳过表头
            parts = line.split()
            if len(parts) < 7:
                continue
            fs_type = parts[1]
            if fs_type in DISK_IGNORE_FS:
                continue
            try:
                total_kb = int(parts[2])
                used_kb = int(parts[3])
                avail_kb = int(parts[4])
                use_pct_str = parts[5].replace("%", "")
                use_pct = float(use_pct_str) if use_pct_str != "-" else 0
                mount = parts[6]
            except (ValueError, IndexError):
                continue

            partitions.append(DiskPartition(
                filesystem=fs_type,
                device=parts[0],
                total_gb=round(total_kb / 1024 / 1024, 2),
                used_gb=round(used_kb / 1024 / 1024, 2),
                available_gb=round(avail_kb / 1024 / 1024, 2),
                usage_percent=use_pct,
                mount_point=mount,
            ))

        return DiskMetric(timestamp=datetime.now(), partitions=partitions)

    def parse_disk_dir_usage(self, output: str) -> list[dict]:
        """解析 du 输出"""
        results = []
        for line in output.strip().splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2:
                try:
                    size_kb = int(parts[0])
                    path = parts[1]
                    results.append({"path": path, "size_kb": size_kb})
                except ValueError:
                    pass
        return results

    def parse_large_files(self, output: str) -> list[dict]:
        """解析 find -exec ls -l 输出（第5列为字节数）"""
        results = []
        for line in output.strip().splitlines():
            parts = line.split()
            if len(parts) >= 9:
                try:
                    size_bytes = int(parts[4])  # ls -l 第5列是字节
                    path_parts = parts[8:]
                    path = " ".join(path_parts)
                    results.append({"path": path, "size_bytes": size_bytes})
                except ValueError:
                    pass
        return results

    # ========== 网络 ==========

    def parse_network(self, dev_output: str, ss_output: str = "") -> Optional[NetworkMetric]:
        """解析 /proc/net/dev 和 ss -s"""
        interfaces = []
        for line in dev_output.strip().splitlines()[2:]:  # 跳过两行表头
            line = line.strip()
            if ":" not in line:
                continue
            iface_name, data = line.split(":", 1)
            iface_name = iface_name.strip()
            if iface_name in NETWORK_IGNORE_IFACES:
                continue
            vals = data.split()
            if len(vals) >= 10:
                try:
                    interfaces.append(NetworkInterface(
                        name=iface_name,
                        rx_bytes=int(vals[0]),
                        rx_packets=int(vals[1]),
                        tx_bytes=int(vals[8]),
                        tx_packets=int(vals[9]),
                    ))
                except ValueError:
                    pass

        tcp_total = tcp_established = 0
        if ss_output:
            for line in ss_output.splitlines():
                # ss -s 输出形如: "TCP: 50 (estab 30, closed 10, ...)"
                m = re.search(r"TCP:\s*(\d+)", line)
                if m:
                    tcp_total = int(m.group(1))
                m = re.search(r"estab\s+(\d+)", line)
                if m:
                    tcp_established = int(m.group(1))

        return NetworkMetric(
            timestamp=datetime.now(),
            interfaces=interfaces,
            tcp_total=tcp_total,
            tcp_established=tcp_established,
        )

    # ========== 进程 ==========

    def parse_processes(self, output: str) -> list[ProcessInfo]:
        """解析 ps aux 输出"""
        procs = []
        for line in output.strip().splitlines()[1:]:  # 跳过表头
            parts = line.split(None, 10)
            if len(parts) < 11:
                continue
            try:
                procs.append(ProcessInfo(
                    user=parts[0],
                    pid=int(parts[1]),
                    cpu_percent=float(parts[2]),
                    mem_percent=float(parts[3]),
                    mem_rss_kb=float(parts[5]),
                    status=parts[7],
                    command=parts[10],
                ))
            except (ValueError, IndexError):
                continue
        return procs

    # ========== 登录记录 ==========

    def parse_auth_log(self, output: str) -> list[AuthLogEntry]:
        """解析 /var/log/auth.log 或 /var/log/secure"""
        entries = []
        now = datetime.now()

        for line in output.strip().splitlines():
            entry = None
            # Accepted publickey/password
            m = re.search(
                r"Accepted\s+(\w+)\s+for\s+(\S+)\s+from\s+(\S+)\s+port\s+(\d+)",
                line,
            )
            if m:
                entry = AuthLogEntry(
                    timestamp=self._parse_syslog_time(line, now),
                    event_type="accepted",
                    user=m.group(2),
                    source_ip=m.group(3),
                    method="ssh",
                    port=int(m.group(4)),
                    raw_line=line,
                )
            else:
                # Failed password
                m = re.search(
                    r"Failed\s+password\s+for\s+(?:invalid\s+user\s+)?(\S+)\s+from\s+(\S+)\s+port\s+(\d+)",
                    line,
                )
                if m:
                    entry = AuthLogEntry(
                        timestamp=self._parse_syslog_time(line, now),
                        event_type="failed",
                        user=m.group(1),
                        source_ip=m.group(2),
                        method="ssh",
                        port=int(m.group(3)),
                        raw_line=line,
                    )

            if entry:
                entries.append(entry)

        return entries

    def _parse_syslog_time(self, line: str, now: datetime) -> datetime:
        """解析 syslog 时间戳 (e.g., 'Jul  6 12:00:05')"""
        try:
            time_str = line[:15]
            return datetime.strptime(
                f"{now.year} {time_str}", "%Y %b %d %H:%M:%S"
            )
        except (ValueError, IndexError):
            return now
