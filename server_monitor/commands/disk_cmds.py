"""磁盘相关采集命令"""

CMD_DISK_USAGE = "df -kT"

CMD_DISK_INODE = "df -i"

# {target_dir} 需替换为实际目录
CMD_DISK_DIR_USAGE = "du -k --max-depth=2 --exclude=/proc --exclude=/sys --exclude=/dev {target_dir} 2>/dev/null | sort -rn | head -50"

CMD_DISK_LARGE_FILES = (
    "find {target_dir} -type f -size +100M "
    "-not -path '/proc/*' -not -path '/sys/*' -not -path '/dev/*' "
    "-exec ls -l {{}} \\; 2>/dev/null | sort -k5 -rn | head -30"
)
