"""主密码登录对话框"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox,
)
from PyQt5.QtCore import Qt


class LoginDialog(QDialog):
    """主密码登录对话框"""

    def __init__(self, is_first_run: bool = False, parent=None):
        super().__init__(parent)
        self._is_first_run = is_first_run
        self._password = ""
        self._confirmed = False
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("ServerMonitor - 主密码")
        self.setMinimumWidth(360)
        self.setModal(True)
        self.setStyleSheet("""
            QLineEdit { padding: 8px; font-size: 14px; }
            QPushButton { padding: 8px 20px; font-size: 13px; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # 标题
        title = QLabel("ServerMonitor")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title)

        if self._is_first_run:
            info = QLabel("首次运行，请设置主密码。\n主密码将用于加密存储 SSH 凭据。")
            info.setAlignment(Qt.AlignCenter)
            info.setWordWrap(True)
            layout.addWidget(info)

            self._pw_input = QLineEdit()
            self._pw_input.setPlaceholderText("设置主密码")
            self._pw_input.setEchoMode(QLineEdit.Password)
            layout.addWidget(self._pw_input)

            self._pw_confirm = QLineEdit()
            self._pw_confirm.setPlaceholderText("确认主密码")
            self._pw_confirm.setEchoMode(QLineEdit.Password)
            self._pw_confirm.returnPressed.connect(self._on_confirm)
            layout.addWidget(self._pw_confirm)
        else:
            info = QLabel("请输入主密码以解锁 SSH 凭据")
            info.setAlignment(Qt.AlignCenter)
            layout.addWidget(info)

            self._pw_input = QLineEdit()
            self._pw_input.setPlaceholderText("输入主密码")
            self._pw_input.setEchoMode(QLineEdit.Password)
            self._pw_input.returnPressed.connect(self._on_confirm)
            layout.addWidget(self._pw_input)
            self._pw_confirm = None

        # 按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("确认")
        ok_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(ok_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _on_confirm(self):
        pw = self._pw_input.text()
        if not pw:
            QMessageBox.warning(self, "错误", "密码不能为空")
            return

        if self._is_first_run and self._pw_confirm is not None:
            pw2 = self._pw_confirm.text()
            if pw != pw2:
                QMessageBox.warning(self, "错误", "两次输入的密码不一致")
                return

        self._password = pw
        self._confirmed = True
        self.accept()

    @property
    def password(self) -> str:
        return self._password

    @property
    def confirmed(self) -> bool:
        return self._confirmed
