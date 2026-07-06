# ServerMonitor-GUI

基于 PyQt5 的桌面端服务器监控管理工具，通过 SSH 无代理方式连接 Linux 服务器（支持最多 10 台），实时采集并展示 CPU、内存、磁盘、网络等核心指标。

## 功能特性

- **仪表盘总览**：卡片视图 / 列表视图双模式切换，一览所有服务器状态
- **实时监控**：CPU / 内存 / 磁盘 / 网络实时曲线图，支持 1min / 5min / 15min 时间窗口
- **颜色阈值标色**：<80% 绿色（正常），≥80% 黄色（警告），≥90% 红色（严重）
- **百分比进度条**：CPU / 内存 / 磁盘列同时显示数值与进度条
- **磁盘分析**：目录级钻取，定位大文件
- **进程排行**：按 CPU / 内存排序的实时进程列表
- **登录记录**：成功/失败登录日志，支持按用户、IP、类型筛选
- **告警系统**：可配置阈值规则，界面弹窗 + 告警日志
- **凭据安全**：AES-256-GCM 加密存储 SSH 凭据，启动时需主密码解锁
- **多列排序**：点击表头可按任意列升序/降序排列

## 环境要求

- Python 3.10+
- 目标服务器：Linux（CentOS 7+ / Ubuntu 18.04+ / Debian 10+）

## 安装

```bash
# 安装依赖
pip install -r server_monitor/requirements.txt
```

## 运行

```bash
# 从项目根目录运行
python run_monitor.py
```

首次运行会要求设置主密码（用于加密存储 SSH 凭据），之后每次启动需要输入主密码解锁。

## 打包为独立可执行文件

```bash
# 安装 PyInstaller
pip install pyinstaller

# 打包
pyinstaller server_monitor.spec
```

打包后的可执行文件位于 `dist/ServerMonitor.exe`。

## 项目结构

```
server_monitor/
├── main.py                  # 应用入口
├── config.py                # 全局配置常量
├── ui/                      # UI 层
│   ├── main_window.py       # 主窗口框架
│   ├── dashboard_tab.py     # 仪表盘 Tab
│   ├── monitor_tab.py       # 实时监控 Tab
│   ├── analysis_tab.py      # 分析 Tab
│   ├── settings_tab.py      # 设置 Tab
│   └── widgets/             # 自定义控件
├── core/                    # 业务逻辑层
│   ├── collector.py         # 采集调度器
│   ├── parser.py            # 命令输出解析器
│   ├── alert_engine.py      # 告警引擎
│   ├── models.py            # 数据模型
│   └── state_manager.py     # 运行时状态管理
├── ssh/                     # SSH 传输层
│   ├── connection_pool.py   # SSH 连接池
│   ├── executor.py          # 远程命令执行器
│   └── credentials.py       # 凭据加密存储
├── alerts/                  # 告警层
│   ├── rules.py             # 告警规则
│   ├── notifier.py          # 通知接口
│   └── history.py           # 告警历史
├── commands/                # 采集命令定义
│   ├── cpu_cmds.py
│   ├── mem_cmds.py
│   ├── disk_cmds.py
│   ├── net_cmds.py
│   ├── process_cmds.py
│   └── auth_cmds.py
├── utils/                   # 工具层
│   ├── encryption.py        # AES 加密/解密
│   ├── humanize.py          # 字节格式化
│   └── validators.py        # 输入校验
└── assets/                  # 静态资源
    └── styles/dark.qss      # 暗色主题样式表
```

## SSH 配置建议

建议为监控创建专用受限账号，通过 sudoers 白名单授权只读命令：

```bash
sudo visudo -f /etc/sudoers.d/server_monitor

monitor_user ALL=(ALL) NOPASSWD: \
  /usr/bin/top -bn1 *, \
  /usr/bin/mpstat *, \
  /usr/bin/free *, \
  /usr/bin/df *, \
  /usr/bin/du *, \
  /bin/cat /proc/*, \
  /bin/cat /var/log/auth.log, \
  /bin/cat /var/log/secure, \
  /usr/bin/last *, \
  /usr/bin/ss *
```
