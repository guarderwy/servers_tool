"""会话内告警历史（内存存储）"""

from datetime import datetime
from ..core.models import AlertRecord


class AlertHistory:
    """管理会话内的告警历史"""

    def __init__(self, max_records: int = 500):
        self._records: list[AlertRecord] = []
        self._max = max_records

    def add(self, alert: AlertRecord):
        self._records.insert(0, alert)
        if len(self._records) > self._max:
            self._records = self._records[:self._max]

    def get_all(self) -> list[AlertRecord]:
        return list(self._records)

    def get_active(self) -> list[AlertRecord]:
        return [r for r in self._records if not r.is_resolved]

    def resolve_by_server_metric(self, server_id: str, metric: str):
        """标记指定服务器和指标的活跃告警为已恢复"""
        now = datetime.now()
        for r in self._records:
            if r.server_id == server_id and r.metric == metric and not r.is_resolved:
                r.is_resolved = True
                r.resolved_at = now

    def resolve_by_rule(self, server_id: str, metric: str, level: str):
        """按规则（含级别）标记活跃告警为已恢复"""
        now = datetime.now()
        for r in self._records:
            if (r.server_id == server_id and r.metric == metric
                    and r.level.value == level and not r.is_resolved):
                r.is_resolved = True
                r.resolved_at = now

    def clear_resolved(self):
        self._records = [r for r in self._records if not r.is_resolved]

    def get_active_count(self) -> int:
        return sum(1 for r in self._records if not r.is_resolved)
