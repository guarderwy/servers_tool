"""告警判断引擎"""

import uuid
import logging
from datetime import datetime

from ..core.models import ServerSnapshot, AlertRecord, AlertLevel, ServerStatus
from .rules import AlertRule
from .notifier import UINotifier
from .history import AlertHistory
from ..config import DEFAULT_ALERT_RULES

logger = logging.getLogger(__name__)


class AlertEngine:
    """告警引擎 —— 根据规则评估采集数据"""

    def __init__(self):
        self._rules: list[AlertRule] = [
            AlertRule.from_dict(d) for d in DEFAULT_ALERT_RULES
        ]
        self._notifier = UINotifier()
        self._history = AlertHistory()

        # 防抖计数器：{(server_id, metric, level): count}
        self._counters: dict[tuple, int] = {}
        # 恢复计数器：{("recover", server_id, metric, level): count}
        self._recovery_counters: dict[tuple, int] = {}

    @property
    def notifier(self) -> UINotifier:
        return self._notifier

    @property
    def history(self) -> AlertHistory:
        return self._history

    def get_rules(self) -> list[AlertRule]:
        return list(self._rules)

    def set_rules(self, rules: list[AlertRule]):
        self._rules = rules
        self._reconcile_active_alerts()

    def to_dict_list(self) -> list[dict]:
        """导出规则为可序列化的字典列表"""
        return [rule.to_dict() for rule in self._rules]

    def load_from_dict(self, rules_data: list[dict]):
        """从字典列表加载规则"""
        self._rules = [AlertRule.from_dict(d) for d in rules_data]
        self._counters.clear()
        self._recovery_counters.clear()
        self._reconcile_active_alerts()

    def _reconcile_active_alerts(self):
        """规则变化后，清理已不再适用的活跃告警。

        触发场景：
        - 规则被禁用 / 删除 → 没有任何启用的同类规则，旧告警失去依据；
        - 阈值/条件被修改 → 按新规则，已记录的值已不再越界。

        解析出的告警会发出 alert_resolved 信号，驱动 UI 从面板与状态栏清除。
        """
        enabled_pairs = {(r.metric, r.level) for r in self._rules if r.enabled}
        for alert in self._history.get_active():
            rule = next(
                (r for r in self._rules if r.enabled
                 and r.metric == alert.metric
                 and r.level == alert.level.value),
                None,
            )
            should_resolve = False
            if rule is None:
                # 规则被删除或禁用
                should_resolve = True
            elif alert.current_value is not None and not rule.matches(
                alert.current_value
            ):
                # 规则仍在，但按新阈值当前值已不再越界
                should_resolve = True

            if should_resolve:
                resolved = self._history.resolve_by_rule(
                    alert.server_id, alert.metric, alert.level.value
                )
                for rec in resolved:
                    self._notifier.send_resolved(rec)
                    logger.info("ALERT RESOLVED (rule changed): %s", rec.message)

        # 清理与新规则集不匹配的去抖/恢复计数器，避免脏状态残留误触发
        self._counters = {
            k: c for k, c in self._counters.items()
            if (k[1], k[2]) in enabled_pairs
        }
        self._recovery_counters = {
            k: c for k, c in self._recovery_counters.items()
            if (k[2], k[3]) in enabled_pairs
        }

    def evaluate(self, snapshot: ServerSnapshot, server_name: str = ""):
        """评估快照数据，触发告警"""
        if snapshot.status == ServerStatus.OFFLINE:
            return

        for rule in self._rules:
            if not rule.enabled:
                continue

            value = self._get_metric_value(snapshot, rule.metric)
            if value is None:
                continue

            key = (snapshot.server_id, rule.metric, rule.level)
            recovery_key = ("recover",) + key

            if rule.matches(value):
                count = self._counters.get(key, 0) + 1
                self._counters[key] = count
                # 条件匹配，重置恢复计数器
                self._recovery_counters.pop(recovery_key, None)

                if count >= rule.duration:
                    self._trigger_alert(
                        snapshot, server_name, rule, value
                    )
            else:
                # 条件不满足，递减计数器
                self._counters[key] = max(0, self._counters.get(key, 0) - 1)
                # 连续不满足达到 duration 次后，才恢复
                rec_count = self._recovery_counters.get(recovery_key, 0) + 1
                self._recovery_counters[recovery_key] = rec_count
                if rec_count >= rule.duration:
                    self._recovery_counters.pop(recovery_key, None)
                    resolved = self._history.resolve_by_rule(
                        snapshot.server_id, rule.metric, rule.level
                    )
                    for rec in resolved:
                        self._notifier.send_resolved(rec)
                        logger.info("ALERT RESOLVED: %s", rec.message)

    def resolve_server_alerts(self, server_id: str):
        """服务器离线/移除时，将其活跃告警标记为已恢复并通知 UI。

        返回被恢复的告警记录列表。
        """
        resolved = self._history.resolve_all_for_server(server_id)
        for rec in resolved:
            self._notifier.send_resolved(rec)
            logger.info("ALERT RESOLVED (offline): %s", rec.message)
        # 同时清理未完成的去抖/恢复计数，避免恢复后误触发
        self._counters = {
            k: c for k, c in self._counters.items() if k[0] != server_id
        }
        self._recovery_counters = {
            k: c for k, c in self._recovery_counters.items()
            if k[1] != server_id
        }
        return resolved

    def _get_metric_value(self, snapshot: ServerSnapshot, metric: str):
        """从快照中提取指标值"""
        if metric == "cpu" and snapshot.cpu:
            return snapshot.cpu.usage_percent
        elif metric == "memory" and snapshot.memory:
            return snapshot.memory.usage_percent
        elif metric == "disk" and snapshot.disk and snapshot.disk.partitions:
            return max(p.usage_percent for p in snapshot.disk.partitions)
        elif metric == "load" and snapshot.cpu:
            return snapshot.cpu.load_1m
        return None

    def _trigger_alert(self, snapshot: ServerSnapshot, server_name: str,
                     rule: AlertRule, value: float):
        """触发告警"""
        # 检查是否已有活跃告警
        for existing in self._history.get_active():
            if (existing.server_id == snapshot.server_id and
                    existing.metric == rule.metric and
                    existing.level.value == rule.level):
                return  # 已有同级别活跃告警，不重复触发
            # 优化：同一指标已有更高级别（critical）告警活跃时，
            # 不再触发低级别（warning）告警，避免重复刷屏
            if (existing.server_id == snapshot.server_id and
                    existing.metric == rule.metric and
                    existing.level == AlertLevel.CRITICAL and
                    rule.level == "warning"):
                return

        alert = AlertRecord(
            id=str(uuid.uuid4())[:8],
            server_id=snapshot.server_id,
            server_name=server_name or snapshot.server_id,
            rule_name=f"{rule.metric} {rule.condition} {rule.threshold}",
            level=AlertLevel(rule.level),
            metric=rule.metric,
            current_value=value,
            threshold=rule.threshold,
            message=f"[{server_name}] {rule.metric.upper()} = {value:.1f}, 阈值 {rule.threshold}",
            triggered_at=datetime.now(),
        )

        self._history.add(alert)
        self._notifier.send(alert)
        logger.warning("ALERT: %s", alert.message)
