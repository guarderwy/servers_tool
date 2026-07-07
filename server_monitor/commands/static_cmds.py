"""服务器静态配置采集命令"""

# 一次采集 CPU 核心数、内存总量、OS 名称、内核版本
CMD_SERVER_INFO = (
    "echo \"cores=$(nproc 2>/dev/null || echo 0)\"; "
    "echo \"mem=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}')\"; "
    "echo \"os=$(head -1 /etc/os-release 2>/dev/null | sed 's/NAME=\"//;s/\"//')\"; "
    "echo \"kernel=$(uname -r 2>/dev/null)\""
)
