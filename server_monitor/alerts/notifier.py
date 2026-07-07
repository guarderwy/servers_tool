"""通知接口 —— 所有通知渠道须实现此接口"""

from PyQt5.QtCore import QObject, pyqtSignal

from ..core.models import AlertRecord


class Notifier:
    """通知接口基类 —— 子类须实现 send() 方法"""

    def send(self, alert: AlertRecord) -> bool:
        raise NotImplementedError("Subclasses must implement send()")


class UINotifier(QObject):
    """界面通知（弹窗 + 面板）"""

    alert_triggered = pyqtSignal(object)  # AlertRecord
    alert_resolved = pyqtSignal(object)   # AlertRecord（已恢复的告警）

    def send(self, alert: AlertRecord) -> bool:
        self.alert_triggered.emit(alert)
        return True

    def send_resolved(self, alert: AlertRecord) -> bool:
        self.alert_resolved.emit(alert)
        return True


# ===== 预留扩展 =====
# class EmailNotifier(Notifier):
#     def send(self, alert: AlertRecord) -> bool:
#         # 发送邮件通知
#         ...
#
# class DingTalkNotifier(Notifier):
#     def send(self, alert: AlertRecord) -> bool:
#         # 发送钉钉通知
#         ...
#
# class WebhookNotifier(Notifier):
#     def send(self, alert: AlertRecord) -> bool:
#         # 发送 Webhook
#         ...
