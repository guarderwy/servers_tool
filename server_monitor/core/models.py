"""数据模型定义"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
from enum import Enum


class ServerStatus(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class ServerConfig:
    """服务器配置"""
    id: str
    name: str
    host: str
    port: int = 22
    username: str = "root"
    auth_type: str = "password"  # password | key
    password: Optional[str] = None
    key_path: Optional[str] = None
    passphrase: Optional[str] = None
    tags: list = field(default_factory=list)
    enabled: bool = True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "auth_type": self.auth_type,
            "tags": self.tags,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ServerConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class CPUMetric:
    """CPU 指标"""
    timestamp: datetime
    usage_percent: float
    user_percent: float
    system_percent: float
    idle_percent: float
    per_core: list = field(default_factory=list)
    load_1m: float = 0.0
    load_5m: float = 0.0
    load_15m: float = 0.0


@dataclass
class MemoryMetric:
    """内存指标"""
    timestamp: datetime
    total_mb: float
    used_mb: float
    free_mb: float
    available_mb: float
    cached_mb: float = 0.0
    buffers_mb: float = 0.0
    usage_percent: float = 0.0


@dataclass
class DiskPartition:
    """磁盘分区信息"""
    filesystem: str
    device: str
    total_gb: float
    used_gb: float
    available_gb: float
    usage_percent: float
    mount_point: str


@dataclass
class DiskMetric:
    """磁盘指标"""
    timestamp: datetime
    partitions: list = field(default_factory=list)


@dataclass
class NetworkInterface:
    """网络接口信息"""
    name: str
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_packets: int = 0
    tx_packets: int = 0


@dataclass
class IPConnectionCount:
    """单个来源 IP 的连接数统计（用于排查恶意连接 / 攻击）"""
    ip: str
    count: int


@dataclass
class NetworkMetric:
    """网络指标"""
    timestamp: datetime
    interfaces: list = field(default_factory=list)
    tcp_total: int = 0
    tcp_established: int = 0
    top_ips: list = field(default_factory=list)  # list[IPConnectionCount]，按连接数降序
    rx_rate: float = 0.0  # 下载速率 bytes/sec（由 StateManager 计算）
    tx_rate: float = 0.0  # 上传速率 bytes/sec（由 StateManager 计算）


@dataclass
class ProcessInfo:
    """进程信息"""
    pid: int
    user: str
    cpu_percent: float
    mem_percent: float
    mem_rss_kb: float
    command: str
    status: str = ""


@dataclass
class AuthLogEntry:
    """认证日志条目"""
    timestamp: datetime
    event_type: str  # accepted | failed | invalid | closed
    user: str
    source_ip: str
    method: str = "ssh"
    port: int = 0
    raw_line: str = ""


@dataclass
class ServerStaticInfo:
    """服务器静态配置信息（首次采集，不频繁变更）"""
    cpu_cores: int = 0
    mem_total_mb: int = 0
    os_name: str = ""
    kernel: str = ""


@dataclass
class ServerSnapshot:
    """服务器快照 —— 一次完整的采集结果"""
    server_id: str
    timestamp: datetime
    status: ServerStatus
    cpu: Optional[CPUMetric] = None
    memory: Optional[MemoryMetric] = None
    disk: Optional[DiskMetric] = None
    network: Optional[NetworkMetric] = None
    top_cpu_procs: list = field(default_factory=list)
    top_mem_procs: list = field(default_factory=list)
    static_info: Optional[ServerStaticInfo] = None


@dataclass
class AlertRecord:
    """告警记录"""
    id: str
    server_id: str
    server_name: str
    rule_name: str
    level: AlertLevel
    metric: str
    current_value: float
    threshold: float
    message: str
    triggered_at: datetime
    resolved_at: Optional[datetime] = None
    is_resolved: bool = False
