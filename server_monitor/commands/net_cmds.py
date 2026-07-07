"""网络相关采集命令"""

CMD_NET_DEV = "cat /proc/net/dev"

CMD_NET_TCP_STATS = "ss -s"

CMD_NET_TCP_DETAIL = "ss -tnp state established"

# 列出所有 TCP 连接（含 SYN_RECV 等半连接，便于排查 SYN Flood 类攻击），
# 按来源 IP 统计连接数。ss 不可用时回退到 netstat。
CMD_NET_CONN_IPS = "ss -tn 2>/dev/null || netstat -tn 2>/dev/null"
