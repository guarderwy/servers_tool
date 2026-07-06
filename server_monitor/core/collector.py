"""采集调度器 —— 管理 QThread 池进行并发数据采集"""

import logging
from datetime import datetime

from PyQt5.QtCore import QObject, QThread, QThreadPool, QRunnable, pyqtSignal

from .models import ServerConfig, ServerSnapshot, ServerStatus
from .parser import CommandParser
from .state_manager import StateManager
from ..ssh.connection_pool import SSHConnectionPool
from ..ssh.executor import SSHExecutor
from ..commands.cpu_cmds import CMD_CPU_USAGE, CMD_LOAD_AVG, CMD_CPU_PER_CORE
from ..commands.mem_cmds import CMD_MEM_INFO
from ..commands.disk_cmds import CMD_DISK_USAGE
from ..commands.net_cmds import CMD_NET_DEV, CMD_NET_TCP_STATS
from ..commands.process_cmds import CMD_TOP_CPU_PROCS, CMD_TOP_MEM_PROCS
from ..config import DEFAULT_POLL_INTERVAL, SSH_RETRY_COUNT

logger = logging.getLogger(__name__)


class CollectorSignals(QObject):
    """采集工作线程的信号"""
    snapshot_ready = pyqtSignal(object)     # ServerSnapshot
    server_offline = pyqtSignal(str)        # server_id
    error_occurred = pyqtSignal(str, str)   # server_id, error_message


class CollectorWorker(QRunnable):
    """单台服务器的采集任务"""

    def __init__(self, server_config: ServerConfig,
                 executor: SSHExecutor, parser: CommandParser,
                 signals: CollectorSignals, interval: float = DEFAULT_POLL_INTERVAL):
        super().__init__()
        self.config = server_config
        self.executor = executor
        self.parser = parser
        self.signals = signals
        self.interval = interval
        self._running = True
        self.setAutoDelete(False)

    def stop(self):
        self._running = False

    def run(self):
        """采集循环"""
        while self._running:
            try:
                snapshot = self._collect_once()
                if snapshot:
                    self.signals.snapshot_ready.emit(snapshot)
            except Exception as e:
                logger.error("Collect error for %s: %s", self.config.name, e)
                self.signals.server_offline.emit(self.config.id)
                self.signals.error_occurred.emit(self.config.id, str(e))

            # 分段 sleep，以便能及时响应 stop
            import time
            steps = int(self.interval * 10)
            for _ in range(max(steps, 1)):
                if not self._running:
                    break
                time.sleep(0.1)

    def _collect_once(self) -> ServerSnapshot:
        """执行一次完整采集"""
        server_id = self.config.id

        # 执行所有采集命令
        commands = [
            CMD_CPU_USAGE, CMD_LOAD_AVG, CMD_MEM_INFO,
            CMD_DISK_USAGE, CMD_NET_DEV, CMD_NET_TCP_STATS,
        ]
        results = self.executor.exec_commands(self.config, commands)

        # 解析 CPU
        cpu_metric = self.parser.parse_cpu(
            results.get(CMD_CPU_USAGE, ""),
            results.get(CMD_LOAD_AVG, ""),
        )

        # 解析内存
        mem_metric = self.parser.parse_memory(results.get(CMD_MEM_INFO, ""))

        # 解析磁盘
        disk_metric = self.parser.parse_disk(results.get(CMD_DISK_USAGE, ""))

        # 解析网络
        net_metric = self.parser.parse_network(
            results.get(CMD_NET_DEV, ""),
            results.get(CMD_NET_TCP_STATS, ""),
        )

        # 确定服务器状态
        status = ServerStatus.ONLINE
        if cpu_metric and cpu_metric.usage_percent >= 90:
            status = ServerStatus.CRITICAL
        elif mem_metric and mem_metric.usage_percent >= 90:
            status = ServerStatus.CRITICAL
        elif cpu_metric and cpu_metric.usage_percent >= 80:
            status = ServerStatus.WARNING
        elif mem_metric and mem_metric.usage_percent >= 80:
            status = ServerStatus.WARNING

        return ServerSnapshot(
            server_id=server_id,
            timestamp=datetime.now(),
            status=status,
            cpu=cpu_metric,
            memory=mem_metric,
            disk=disk_metric,
            network=net_metric,
        )

    def collect_processes(self):
        """采集进程列表（按需调用，不在常规循环中）"""
        try:
            cpu_out = self.executor.exec_command(self.config, CMD_TOP_CPU_PROCS)
            mem_out = self.executor.exec_command(self.config, CMD_TOP_MEM_PROCS)
            return (
                self.parser.parse_processes(cpu_out),
                self.parser.parse_processes(mem_out),
            )
        except Exception as e:
            logger.error("Failed to collect processes: %s", e)
            return [], []


class CollectorScheduler(QObject):
    """采集调度器 —— 管理所有服务器的采集任务"""

    snapshot_ready = pyqtSignal(object)
    server_offline = pyqtSignal(str)
    error_occurred = pyqtSignal(str, str)

    def __init__(self, pool: SSHConnectionPool, state_manager: StateManager,
                 interval: float = DEFAULT_POLL_INTERVAL):
        super().__init__()
        self._pool = pool
        self._state = state_manager
        self._executor = SSHExecutor(pool)
        self._parser = CommandParser()
        self._interval = interval
        self._thread_pool = QThreadPool()
        self._thread_pool.setMaxThreadCount(10)
        self._workers: dict[str, CollectorWorker] = {}
        self._signals = CollectorSignals()

        # 连接信号
        self._signals.snapshot_ready.connect(self._on_snapshot)
        self._signals.server_offline.connect(self._on_offline)
        self._signals.error_occurred.connect(self.error_occurred)

    def set_interval(self, interval: float):
        self._interval = interval
        # 重启所有运行中的 worker，使新间隔立即生效
        running = list(self._workers.keys())
        if running:
            logger.info("Restarting %d workers with new interval %.1f", len(running), interval)
            for sid in running:
                self.stop(sid)
                self.start(sid)

    def start_all(self):
        """启动所有已启用服务器的采集"""
        for cfg in self._state.get_configs():
            if cfg.enabled:
                self.start(cfg.id)

    def stop_all(self):
        """停止所有采集"""
        for sid in list(self._workers.keys()):
            self.stop(sid)

    def get_active_ids(self) -> list[str]:
        """返回当前正在监控的服务器 ID 列表"""
        return list(self._workers.keys())

    def is_running(self, server_id: str) -> bool:
        """指定服务器是否正在监控中"""
        return server_id in self._workers

    def start(self, server_id: str):
        """启动单台服务器的采集"""
        if server_id in self._workers:
            return

        cfg = self._state.get_config(server_id)
        if not cfg:
            return

        worker = CollectorWorker(
            cfg, self._executor, self._parser,
            self._signals, self._interval,
        )
        self._workers[server_id] = worker
        self._thread_pool.start(worker)
        logger.info("Started collecting: %s", cfg.name)

    def stop(self, server_id: str):
        """停止单台服务器的采集"""
        worker = self._workers.pop(server_id, None)
        if worker:
            worker.stop()
            logger.info("Stopped collecting: %s", server_id)

    def collect_processes(self, server_id: str):
        """按需采集进程列表"""
        logger.info("collect_processes called for server=%s", server_id)
        worker = self._workers.get(server_id)
        if worker:
            return worker.collect_processes()
        # 没有运行中的 worker，临时创建
        cfg = self._state.get_config(server_id)
        if cfg:
            logger.info("collect_processes: creating temp worker for %s", server_id)
            temp_worker = CollectorWorker(
                cfg, self._executor, self._parser, self._signals
            )
            return temp_worker.collect_processes()
        logger.warning("collect_processes: no config found for %s", server_id)
        return [], []

    def collect_disk_analysis(self, server_id: str, target_dir: str = "/"):
        """按需采集磁盘目录分析（兼容旧调用）"""
        dirs = self.collect_dir_usage(server_id, target_dir)
        files = self.collect_large_files(server_id, target_dir)
        return dirs, files

    def collect_dir_usage(self, server_id: str, target_dir: str = "/"):
        """采集目录占用"""
        logger.info("collect_dir_usage called for server=%s dir=%s", server_id, target_dir)
        from ..commands.disk_cmds import CMD_DISK_DIR_USAGE
        cfg = self._state.get_config(server_id)
        if not cfg:
            logger.warning("collect_dir_usage: no config for %s", server_id)
            return []
        try:
            du_out = self._executor.exec_command(
                cfg, CMD_DISK_DIR_USAGE.format(target_dir=target_dir)
            )
            logger.info("collect_dir_usage: du=%d bytes", len(du_out))
            return self._parser.parse_disk_dir_usage(du_out)
        except Exception as e:
            logger.error("collect_dir_usage error: %s", e)
            return []

    def collect_large_files(self, server_id: str, target_dir: str = "/"):
        """采集大文件列表"""
        logger.info("collect_large_files called for server=%s dir=%s", server_id, target_dir)
        from ..commands.disk_cmds import CMD_DISK_LARGE_FILES
        cfg = self._state.get_config(server_id)
        if not cfg:
            logger.warning("collect_large_files: no config for %s", server_id)
            return []
        try:
            large_out = self._executor.exec_command(
                cfg, CMD_DISK_LARGE_FILES.format(target_dir=target_dir)
            )
            logger.info("collect_large_files: large=%d bytes", len(large_out))
            return self._parser.parse_large_files(large_out)
        except Exception as e:
            logger.error("collect_large_files error: %s", e)
            return []

    def collect_auth_logs(self, server_id: str):
        """按需采集登录记录"""
        logger.info("collect_auth_logs called for server=%s", server_id)
        from ..commands.auth_cmds import CMD_AUTH_LOG
        cfg = self._state.get_config(server_id)
        if not cfg:
            logger.warning("collect_auth_logs: no config for %s", server_id)
            return []
        try:
            output = self._executor.exec_command(cfg, CMD_AUTH_LOG, timeout=20)
            logger.info("collect_auth_logs: got %d bytes", len(output))
            return self._parser.parse_auth_log(output)
        except Exception as e:
            logger.error("Auth log error: %s", e)
            return []

    def _on_snapshot(self, snapshot: ServerSnapshot):
        """处理采集到的快照"""
        self._state.update_snapshot(snapshot)
        self.snapshot_ready.emit(snapshot)

    def _on_offline(self, server_id: str):
        """处理离线事件"""
        self._state.mark_offline(server_id)
        self.server_offline.emit(server_id)

    def shutdown(self):
        """完全停止调度器"""
        self.stop_all()
        self._thread_pool.waitForDone(5000)
        self._pool.close_all()
