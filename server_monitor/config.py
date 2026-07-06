"""全局配置常量"""

import os
from pathlib import Path

# ========== 应用信息 ==========
APP_NAME = "ServerMonitor-GUI"
APP_VERSION = "1.0.0"
APP_TITLE = f"{APP_NAME} v{APP_VERSION}"

# ========== 路径 ==========
APP_DIR = Path(os.path.expanduser("~")) / ".server_monitor"
CREDENTIALS_FILE = APP_DIR / "credentials.enc"
CONFIG_FILE = APP_DIR / "config.json"
APP_DIR.mkdir(parents=True, exist_ok=True)

# ========== SSH 连接参数 ==========
SSH_CONNECT_TIMEOUT = 10       # 连接超时（秒）
SSH_COMMAND_TIMEOUT = 15       # 命令执行超时（秒）
SSH_KEEPALIVE_INTERVAL = 30    # 心跳间隔（秒）
SSH_MAX_CONNECTIONS = 10       # 最大连接数
SSH_RETRY_COUNT = 3            # 采集失败重试次数

# ========== 采集参数 ==========
DEFAULT_POLL_INTERVAL = 5      # 默认轮询间隔（秒）
MIN_POLL_INTERVAL = 3          # 最小轮询间隔
MAX_POLL_INTERVAL = 60         # 最大轮询间隔

# ========== 图表参数 ==========
CHART_WINDOW_1MIN = 60         # 1 分钟窗口（数据点数 = 60/interval）
CHART_WINDOW_5MIN = 300        # 5 分钟窗口
CHART_WINDOW_15MIN = 900       # 15 分钟窗口
CHART_MAX_POINTS = 300         # 图表最大数据点
CHART_REFRESH_MS = 1000        # 图表刷新间隔（毫秒）

# ========== 阈值 ==========
THRESHOLD_WARNING = 80.0       # 警告阈值（%）
THRESHOLD_CRITICAL = 90.0      # 严重阈值（%）

# ========== 颜色定义 ==========
COLOR_NORMAL_BG = "#e8f8e8"
COLOR_NORMAL_FG = "#27ae60"
COLOR_NORMAL_BAR = "#2ecc71"

COLOR_WARNING_BG = "#fef9e7"
COLOR_WARNING_FG = "#d68910"
COLOR_WARNING_BAR = "#f39c12"

COLOR_CRITICAL_BG = "#fdeaea"
COLOR_CRITICAL_FG = "#c0392b"
COLOR_CRITICAL_BAR = "#e74c3c"

COLOR_OFFLINE_BG = "#f2f3f4"
COLOR_OFFLINE_FG = "#7f8c8d"
COLOR_OFFLINE_BAR = "#bdc3c7"

# ========== 默认告警规则 ==========
DEFAULT_ALERT_RULES = [
    {"metric": "cpu", "condition": "gte", "threshold": 90.0, "duration": 3, "level": "critical"},
    {"metric": "cpu", "condition": "gte", "threshold": 80.0, "duration": 5, "level": "warning"},
    {"metric": "memory", "condition": "gte", "threshold": 90.0, "duration": 3, "level": "critical"},
    {"metric": "memory", "condition": "gte", "threshold": 80.0, "duration": 5, "level": "warning"},
    {"metric": "disk", "condition": "gte", "threshold": 90.0, "duration": 3, "level": "critical"},
    {"metric": "disk", "condition": "gte", "threshold": 80.0, "duration": 5, "level": "warning"},
]

# ========== 网络接口过滤 ==========
NETWORK_IGNORE_IFACES = {"lo"}  # 忽略的网卡名

# ========== 磁盘分区类型过滤 ==========
DISK_IGNORE_FS = {"tmpfs", "devtmpfs", "squashfs", "overlay"}
