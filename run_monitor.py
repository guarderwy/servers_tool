"""ServerMonitor-GUI 启动脚本"""
import sys
import os

# 将 server_monitor 包的父目录添加到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server_monitor.main import main

if __name__ == "__main__":
    main()
