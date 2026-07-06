"""登录日志相关采集命令"""

# 尝试两种日志路径
CMD_AUTH_LOG = (
    "tail -500 /var/log/auth.log 2>/dev/null || tail -500 /var/log/secure 2>/dev/null"
)

CMD_LAST_LOGIN = "last -50 2>/dev/null"

CMD_LASTB_FAILED = "lastb -50 2>/dev/null"
