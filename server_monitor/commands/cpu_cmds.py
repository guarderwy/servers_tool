"""CPU 相关采集命令"""

# 总体 CPU 使用率
CMD_CPU_USAGE = (
    "head -1 /proc/stat; sleep 1; head -1 /proc/stat"
)

# 各核心使用率
CMD_CPU_PER_CORE = (
    "cat /proc/stat | grep '^cpu[0-9]'"
)

# CPU 负载均值
CMD_LOAD_AVG = "cat /proc/loadavg"

# CPU 信息（核心数等）
CMD_CPU_INFO = "nproc"
