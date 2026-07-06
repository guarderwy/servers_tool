"""输入校验器"""

import re
from typing import Optional


def validate_host(host: str) -> Optional[str]:
    """校验主机名/IP，返回错误信息或 None"""
    if not host or not host.strip():
        return "主机地址不能为空"
    host = host.strip()
    # IPv4
    ipv4_pattern = r"^(\d{1,3}\.){3}\d{1,3}$"
    if re.match(ipv4_pattern, host):
        parts = host.split(".")
        if all(0 <= int(p) <= 255 for p in parts):
            return None
        return "IP 地址无效"
    # 域名
    domain_pattern = r"^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*$"
    if re.match(domain_pattern, host) and len(host) <= 253:
        return None
    return "无效的主机地址"


def validate_port(port) -> Optional[str]:
    """校验端口号"""
    try:
        p = int(port)
        if 1 <= p <= 65535:
            return None
        return "端口号必须在 1-65535 之间"
    except (ValueError, TypeError):
        return "端口号必须是数字"


def validate_username(username: str) -> Optional[str]:
    """校验用户名"""
    if not username or not username.strip():
        return "用户名不能为空"
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_.\-]*$", username.strip()):
        return "用户名格式不正确"
    return None


def validate_interval(interval) -> Optional[str]:
    """校验轮询间隔"""
    try:
        v = float(interval)
        if 3 <= v <= 60:
            return None
        return "轮询间隔必须在 3-60 秒之间"
    except (ValueError, TypeError):
        return "请输入有效的数字"
