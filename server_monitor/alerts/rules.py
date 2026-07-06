"""告警规则定义"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class AlertRule:
    """告警规则"""
    metric: str            # cpu | memory | disk | load
    condition: str         # gt | lt | eq | gte | lte
    threshold: float       # 阈值
    duration: int = 3      # 持续次数（防抖动）
    enabled: bool = True
    level: str = "warning" # warning | critical

    def matches(self, value: float) -> bool:
        """检查值是否满足条件"""
        if self.condition == "gt":
            return value > self.threshold
        elif self.condition == "gte":
            return value >= self.threshold
        elif self.condition == "lt":
            return value < self.threshold
        elif self.condition == "lte":
            return value <= self.threshold
        elif self.condition == "eq":
            return abs(value - self.threshold) < 0.01
        return False

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "condition": self.condition,
            "threshold": self.threshold,
            "duration": self.duration,
            "enabled": self.enabled,
            "level": self.level,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AlertRule":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
