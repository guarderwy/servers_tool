"""分析 Tab —— 磁盘分析、Top 进程、登录记录"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QComboBox,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from .widgets.disk_tree_widget import DiskTreeWidget
from .widgets.log_table_widget import LogTableWidget
from ..core.collector import CollectorScheduler
from ..core.state_manager import StateManager


class ProcessThread(QThread):
    """后台进程采集线程"""
    result_ready = pyqtSignal(list, list)

    def __init__(self, scheduler, server_id):
        super().__init__()
        self._scheduler = scheduler
        self._server_id = server_id

    def run(self):
        import logging; logging.getLogger(__name__).info("ProcessThread.run() called server=%s", self._server_id)
        cpu_procs, mem_procs = self._scheduler.collect_processes(self._server_id)
        self.result_ready.emit(cpu_procs, mem_procs)


class _LogThread(QThread):
    """登录记录采集线程"""
    result_ready = pyqtSignal(list)

    def __init__(self, scheduler, server_id):
        super().__init__()
        self._scheduler = scheduler
        self._server_id = server_id

    def run(self):
        import logging; logging.getLogger(__name__).info("_LogThread.run() called server=%s", self._server_id)
        entries = self._scheduler.collect_auth_logs(self._server_id)
        self.result_ready.emit(entries)


class _DirThread(QThread):
    """目录占用采集线程"""
    result_ready = pyqtSignal(list)

    def __init__(self, scheduler, server_id, target_dir):
        super().__init__()
        self._scheduler = scheduler
        self._server_id = server_id
        self._target_dir = target_dir

    def run(self):
        import logging; logging.getLogger(__name__).info("_DirThread.run() called server=%s dir=%s", self._server_id, self._target_dir)
        dirs = self._scheduler.collect_dir_usage(
            self._server_id, self._target_dir
        )
        self.result_ready.emit(dirs)


class _LargeFileThread(QThread):
    """大文件采集线程"""
    result_ready = pyqtSignal(list)

    def __init__(self, scheduler, server_id, target_dir):
        super().__init__()
        self._scheduler = scheduler
        self._server_id = server_id
        self._target_dir = target_dir

    def run(self):
        import logging; logging.getLogger(__name__).info("_LargeFileThread.run() called server=%s dir=%s", self._server_id, self._target_dir)
        files = self._scheduler.collect_large_files(
            self._server_id, self._target_dir
        )
        self.result_ready.emit(files)


class AnalysisTab(QWidget):
    """分析 Tab"""

    def __init__(self, state_manager: StateManager,
                 scheduler: CollectorScheduler, parent=None):
        super().__init__(parent)
        self._state = state_manager
        self._scheduler = scheduler
        self._selected_server = ""
        self._analysis_threads: set[QThread] = set()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 服务器选择
        server_row = QHBoxLayout()
        server_row.addWidget(QLabel("选择服务器:"))
        self._server_combo = QComboBox()
        self._server_combo.setMinimumWidth(200)
        self._server_combo.currentIndexChanged.connect(self._on_server_changed)
        server_row.addWidget(self._server_combo)
        server_row.addStretch()
        layout.addLayout(server_row)

        # 子页面 Tab
        self._sub_tabs = QTabWidget()
        # 子页面 1: 磁盘空间分析
        self._disk_widget = DiskTreeWidget()
        self._disk_widget.connect_scan(self.scan_dir)
        self._disk_widget.connect_find_large(self.find_large_files)
        self._sub_tabs.addTab(self._disk_widget, "磁盘空间分析")

        # 子页面 2: Top 进程
        self._process_widget = self._create_process_tab()
        self._sub_tabs.addTab(self._process_widget, "Top 进程")

        # 子页面 3: 登录记录
        self._log_widget = LogTableWidget()
        self._log_widget.connect_refresh(self._refresh_logs)
        self._sub_tabs.addTab(self._log_widget, "登录记录")

        layout.addWidget(self._sub_tabs, 1)

    def _create_process_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        toolbar = QHBoxLayout()
        self._proc_sort_combo = QComboBox()
        self._proc_sort_combo.addItems(["按 CPU 排序", "按内存排序"])
        toolbar.addWidget(self._proc_sort_combo)

        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_processes)
        toolbar.addWidget(refresh_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._proc_table = QTableWidget()
        self._proc_table.setColumnCount(6)
        self._proc_table.setHorizontalHeaderLabels([
            "PID", "用户", "CPU%", "MEM%", "RSS(KB)", "命令"
        ])
        self._proc_table.horizontalHeader().setStretchLastSection(True)
        self._proc_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._proc_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._proc_table.setAlternatingRowColors(True)
        layout.addWidget(self._proc_table)

        self._cpu_procs = []
        self._mem_procs = []

        return widget

    def refresh_server_list(self):
        """刷新服务器选择下拉"""
        import logging; log = logging.getLogger(__name__)
        self._server_combo.blockSignals(True)
        current = self._server_combo.currentText()
        self._server_combo.clear()
        configs = self._state.get_configs()
        log.info("refresh_server_list: got %d configs", len(configs))
        for cfg in configs:
            if cfg.enabled:
                self._server_combo.addItem(f"{cfg.name} ({cfg.host})", cfg.id)
        # 恢复选择
        for i in range(self._server_combo.count()):
            if self._server_combo.itemText(i).startswith(current.split(" (")[0]):
                self._server_combo.setCurrentIndex(i)
                break
        self._server_combo.blockSignals(False)
        # 初始化当前选中的服务器
        self._on_server_changed(self._server_combo.currentIndex())

    def _on_server_changed(self, index):
        server_id = self._server_combo.currentData()
        import logging; logging.getLogger(__name__).info("_on_server_changed: index=%d server_id=%s", index, server_id)
        if server_id:
            self._selected_server = server_id
            self._disk_widget.set_server_id(server_id)

    def _refresh_processes(self):
        if not self._selected_server:
            import logging; logging.getLogger(__name__).warning("_refresh_processes: _selected_server is empty")
            return

        import logging; logging.getLogger(__name__).info("_refresh_processes: starting for server=%s", self._selected_server)
        thread = ProcessThread(self._scheduler, self._selected_server)
        self._analysis_threads.add(thread)
        thread.result_ready.connect(self._on_processes_ready)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._analysis_threads.discard(thread))
        thread.start()

    def _on_processes_ready(self, cpu_procs, mem_procs):
        import logging; logging.getLogger(__name__).info("_on_processes_ready: cpu=%d mem=%d", len(cpu_procs), len(mem_procs))
        self._cpu_procs = cpu_procs
        self._mem_procs = mem_procs

        # 根据排序选择显示
        procs = self._cpu_procs if self._proc_sort_combo.currentIndex() == 0 else self._mem_procs

        self._proc_table.setRowCount(len(procs))
        for i, p in enumerate(procs):
            self._proc_table.setItem(i, 0, QTableWidgetItem(str(p.pid)))
            self._proc_table.setItem(i, 1, QTableWidgetItem(p.user))
            self._proc_table.setItem(i, 2, QTableWidgetItem(f"{p.cpu_percent:.1f}"))
            self._proc_table.setItem(i, 3, QTableWidgetItem(f"{p.mem_percent:.1f}"))
            self._proc_table.setItem(i, 4, QTableWidgetItem(f"{p.mem_rss_kb:.0f}"))
            self._proc_table.setItem(i, 5, QTableWidgetItem(p.command[:80]))

    def _refresh_logs(self):
        if not self._selected_server:
            import logging; logging.getLogger(__name__).warning("_refresh_logs: _selected_server is empty")
            return

        import logging; logging.getLogger(__name__).info("_refresh_logs: starting for server=%s", self._selected_server)
        thread = _LogThread(self._scheduler, self._selected_server)
        self._analysis_threads.add(thread)
        thread.result_ready.connect(self._log_widget.update_entries)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._analysis_threads.discard(thread))
        thread.start()

    def scan_dir(self, server_id: str, target_dir: str):
        """触发目录扫描"""
        sid = server_id or self._selected_server
        if not sid:
            import logging; logging.getLogger(__name__).warning("scan_dir: no server_id")
            return

        import logging; logging.getLogger(__name__).info("scan_dir: server=%s dir=%s", sid, target_dir)

        thread = _DirThread(self._scheduler, sid, target_dir)
        self._analysis_threads.add(thread)
        thread.result_ready.connect(self._disk_widget.update_dir_data)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._analysis_threads.discard(thread))
        thread.start()

    def find_large_files(self, server_id: str, target_dir: str):
        """触发大文件查找"""
        sid = server_id or self._selected_server
        if not sid:
            import logging; logging.getLogger(__name__).warning("find_large_files: no server_id")
            return

        import logging; logging.getLogger(__name__).info("find_large_files: server=%s dir=%s", sid, target_dir)

        thread = _LargeFileThread(self._scheduler, sid, target_dir)
        self._analysis_threads.add(thread)
        thread.result_ready.connect(self._disk_widget.update_file_data)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._analysis_threads.discard(thread))
        thread.start()
