"""工具函数：字节数人性化格式化"""


def humanize_bytes(size_bytes: float) -> str:
    """将字节数转换为人类可读的格式"""
    if size_bytes is None:
        return "--"
    size_bytes = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} EB"


def humanize_bytes_per_sec(bytes_per_sec: float) -> str:
    """将每秒字节数转换为可读速率"""
    if bytes_per_sec is None:
        return "--"
    return humanize_bytes(bytes_per_sec) + "/s"


def humanize_kb(kb: float) -> str:
    """将 KB 转换为可读格式"""
    return humanize_bytes(kb * 1024)


def humanize_mb(mb: float) -> str:
    """将 MB 转换为可读格式"""
    return humanize_bytes(mb * 1024 * 1024)


def humanize_gb(gb: float) -> str:
    """将 GB 转换为可读格式"""
    return humanize_bytes(gb * 1024 * 1024 * 1024)
