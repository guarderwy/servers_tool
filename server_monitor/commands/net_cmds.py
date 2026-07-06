"""网络相关采集命令"""

CMD_NET_DEV = "cat /proc/net/dev"

CMD_NET_TCP_STATS = "ss -s"

CMD_NET_TCP_DETAIL = "ss -tnp state established"
