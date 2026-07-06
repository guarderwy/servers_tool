"""磁盘目录树控件"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QLabel, QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView,
)
from PyQt5.QtCore import Qt, pyqtSignal
from ...utils.humanize import humanize_kb, humanize_bytes


class DiskTreeWidget(QWidget):
    """磁盘空间分析 —— 目录树 + 大文件列表"""

    scan_requested = pyqtSignal(str, str)  # server_id, target_dir
    large_files_requested = pyqtSignal(str, str)  # server_id, target_dir

    def __init__(self, parent=None):
        super().__init__(parent)
        self._server_id = ""
        self._current_dir = "/"
        self._nav_history: list[str] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 工具栏第一行：目录选择 + 按钮
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("当前目录:"))
        self._dir_input = QComboBox()
        self._dir_input.setEditable(True)
        self._dir_input.addItem("/")
        self._dir_input.addItem("/var")
        self._dir_input.addItem("/home")
        self._dir_input.addItem("/tmp")
        self._dir_input.addItem("/usr")
        toolbar.addWidget(self._dir_input, 1)

        self._back_btn = QPushButton("← 返回上级")
        self._back_btn.clicked.connect(self._on_back)
        self._back_btn.setEnabled(False)
        toolbar.addWidget(self._back_btn)

        self._scan_btn = QPushButton("扫描")
        self._scan_btn.clicked.connect(self._on_scan)
        toolbar.addWidget(self._scan_btn)

        self._large_btn = QPushButton("查找大文件")
        self._large_btn.clicked.connect(self._on_find_large)
        toolbar.addWidget(self._large_btn)

        layout.addLayout(toolbar)

        # 内容区
        content = QHBoxLayout()

        # 左侧：目录树
        left = QVBoxLayout()
        left.addWidget(QLabel("目录占用 (双击进入子目录)"))
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["路径", "大小"])
        self._tree.setColumnWidth(0, 300)
        self._tree.setAlternatingRowColors(True)
        self._tree.itemDoubleClicked.connect(self._on_tree_double_clicked)
        self._tree.setStyleSheet("""
            QTreeWidget {
                background-color: #1e1e2e;
                color: #cccccc;
                alternate-background-color: #252535;
            }
        """)
        left.addWidget(self._tree)
        content.addLayout(left, 1)

        # 右侧：大文件列表
        right = QVBoxLayout()
        right.addWidget(QLabel("大文件列表 (TOP 30)"))
        self._file_table = QTableWidget()
        self._file_table.setColumnCount(2)
        self._file_table.setHorizontalHeaderLabels(["大小", "路径"])
        self._file_table.horizontalHeader().setStretchLastSection(True)
        self._file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._file_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._file_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._file_table.setAlternatingRowColors(True)
        self._file_table.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e2e;
                color: #cccccc;
                alternate-background-color: #252535;
            }
        """)
        right.addWidget(self._file_table)
        content.addLayout(right, 1)

        layout.addLayout(content)

    def _on_scan(self):
        """扫描按钮：只扫描目录占用"""
        target = self._dir_input.currentText().strip() or "/"
        self._current_dir = target
        self.scan_requested.emit("", target)

    def _on_find_large(self):
        """查找大文件按钮"""
        target = self._dir_input.currentText().strip() or "/"
        self.large_files_requested.emit("", target)

    def _on_tree_double_clicked(self, item: QTreeWidgetItem, _column):
        """双击目录进入子目录"""
        path = item.text(0)
        # 跳过非目录项（没有 size_kb 数据的，或根目录自身）
        if not path or path == self._current_dir:
            return
        # 记录当前目录到历史
        self._nav_history.append(self._current_dir)
        self._back_btn.setEnabled(True)
        self._current_dir = path
        # 更新输入框
        idx = self._dir_input.findText(path)
        if idx >= 0:
            self._dir_input.setCurrentIndex(idx)
        else:
            self._dir_input.setEditText(path)
        # 发起扫描
        self.scan_requested.emit("", path)

    def _on_back(self):
        """返回上级目录"""
        if not self._nav_history:
            return
        parent = self._nav_history.pop()
        self._back_btn.setEnabled(len(self._nav_history) > 0)
        self._current_dir = parent
        idx = self._dir_input.findText(parent)
        if idx >= 0:
            self._dir_input.setCurrentIndex(idx)
        else:
            self._dir_input.setEditText(parent)
        self.scan_requested.emit("", parent)

    def set_server_id(self, server_id: str):
        self._server_id = server_id

    def update_dir_data(self, dir_usage: list[dict]):
        """更新目录树"""
        self._tree.clear()
        if not dir_usage:
            return
        # 第一条通常是目标目录自身，跳过
        # 如果第一条的 path 和 _current_dir 一致，跳过
        start = 1 if (dir_usage and dir_usage[0]["path"].rstrip("/") == self._current_dir.rstrip("/")) else 0
        for item in dir_usage[start:]:
            tree_item = QTreeWidgetItem([
                item["path"],
                humanize_kb(item["size_kb"]),
            ])
            self._tree.addTopLevelItem(tree_item)

    def update_file_data(self, large_files: list[dict]):
        """更新大文件列表"""
        self._file_table.setRowCount(len(large_files))
        for i, f in enumerate(large_files):
            self._file_table.setItem(i, 0, QTableWidgetItem(humanize_bytes(f["size_bytes"])))
            self._file_table.setItem(i, 1, QTableWidgetItem(f["path"]))

    def connect_scan(self, handler):
        """连接扫描请求信号"""
        self.scan_requested.connect(handler)

    def connect_find_large(self, handler):
        """连接大文件请求信号"""
        self.large_files_requested.connect(handler)
