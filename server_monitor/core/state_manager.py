"""运行时状态管理 —— 内存中保存所有服务器的最新快照"""

from datetime import datetime
from typing import Optional

from .models import ServerSnapshot, ServerStatus, ServerConfig


class StateManager:
    """管理所有服务器的运行时状态"""

    def __init__(self):
        self._snapshots: dict[str, ServerSnapshot] = {}
        self._configs: dict[str, ServerConfig] = {}
        self._listeners: list = []
        self._prev_network: dict[str, tuple] = {}  # server_id -> (rx_bytes, tx_bytes, timestamp)

    def register_listener(self, callback):
        """注册状态变更监听器"""
        self._listeners.append(callback)

    def unregister_listener(self, callback):
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self, server_id: str):
        for cb in self._listeners:
            try:
                cb(server_id)
            except Exception:
                pass

    def update_config(self, config: ServerConfig):
        self._configs[config.id] = config

    def remove_config(self, server_id: str):
        self._configs.pop(server_id, None)
        self._snapshots.pop(server_id, None)

    def get_configs(self) -> list[ServerConfig]:
        return list(self._configs.values())

    def get_config(self, server_id: str) -> Optional[ServerConfig]:
        return self._configs.get(server_id)

    def update_snapshot(self, snapshot: ServerSnapshot):
        """更新某台服务器的快照"""
        self._compute_network_rate(snapshot)
        self._snapshots[snapshot.server_id] = snapshot
        self._notify(snapshot.server_id)

    def _compute_network_rate(self, snapshot: ServerSnapshot):
        """根据前后两次累计值计算网络速率（bytes/sec）"""
        if not snapshot.network or not snapshot.network.interfaces:
            return
        total_rx = sum(i.rx_bytes for i in snapshot.network.interfaces)
        total_tx = sum(i.tx_bytes for i in snapshot.network.interfaces)

        prev = self._prev_network.get(snapshot.server_id)
        if prev:
            dt = (snapshot.timestamp - prev[2]).total_seconds()
            if dt > 0:
                snapshot.network.rx_rate = max(0, (total_rx - prev[0]) / dt)
                snapshot.network.tx_rate = max(0, (total_tx - prev[1]) / dt)
            else:
                snapshot.network.rx_rate = 0.0
                snapshot.network.tx_rate = 0.0
        else:
            # 第一次采集，没有历史值，速率为 0
            snapshot.network.rx_rate = 0.0
            snapshot.network.tx_rate = 0.0

        self._prev_network[snapshot.server_id] = (total_rx, total_tx, snapshot.timestamp)

    def mark_offline(self, server_id: str):
        """标记服务器为离线"""
        self._snapshots[server_id] = ServerSnapshot(
            server_id=server_id,
            timestamp=datetime.now(),
            status=ServerStatus.OFFLINE,
        )
        self._notify(server_id)

    def get_snapshot(self, server_id: str) -> Optional[ServerSnapshot]:
        return self._snapshots.get(server_id)

    def get_all_snapshots(self) -> list[ServerSnapshot]:
        """获取所有服务器的最新快照（按配置顺序）"""
        results = []
        for cfg in self._configs.values():
            snap = self._snapshots.get(cfg.id)
            if snap:
                results.append(snap)
            else:
                # 未采集过的显示为离线
                results.append(ServerSnapshot(
                    server_id=cfg.id,
                    timestamp=datetime.now(),
                    status=ServerStatus.OFFLINE,
                ))
        return results

    def get_online_count(self) -> int:
        return sum(
            1 for s in self._snapshots.values()
            if s.status != ServerStatus.OFFLINE
        )

    def get_total_count(self) -> int:
        return len(self._configs)

    def get_alert_count(self) -> int:
        """返回处于 warning 或 critical 状态的服务器数"""
        return sum(
            1 for s in self._snapshots.values()
            if s.status in (ServerStatus.WARNING, ServerStatus.CRITICAL)
        )
