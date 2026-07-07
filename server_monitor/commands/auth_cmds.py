"""登录日志相关采集命令"""

# 尝试多种日志路径，兼容 Ubuntu / RHEL / Amazon Linux 2023
CMD_AUTH_LOG = (
    "tail -500 /var/log/auth.log 2>/dev/null || "
    "tail -500 /var/log/secure 2>/dev/null || "
    "journalctl -u sshd -n 500 --no-pager 2>/dev/null || "
    "journalctl -u ssh -n 500 --no-pager 2>/dev/null"
)

CMD_LAST_LOGIN = "last -50 2>/dev/null"

CMD_LASTB_FAILED = "lastb -50 2>/dev/null"
    