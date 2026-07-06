"""SSH 连接池 —— 管理多台服务器的 SSH 连接复用"""

import threading
import logging
import paramiko

from ..config import SSH_CONNECT_TIMEOUT, SSH_KEEPALIVE_INTERVAL, SSH_MAX_CONNECTIONS

logger = logging.getLogger(__name__)


class SSHConnectionPool:
    """SSH 连接池，支持连接复用与并发控制"""

    def __init__(self, max_connections: int = SSH_MAX_CONNECTIONS):
        self._max = max_connections
        self._connections: dict[str, paramiko.SSHClient] = {}
        self._lock = threading.Lock()

    def _make_key(self, host: str, port: int, username: str) -> str:
        return f"{username}@{host}:{port}"

    def get_connection(self, server_config) -> paramiko.SSHClient:
        """获取或创建 SSH 连接（带复用）"""
        from ..core.models import ServerConfig
        cfg: ServerConfig = server_config
        key = self._make_key(cfg.host, cfg.port, cfg.username)

        with self._lock:
            conn = self._connections.get(key)
            if conn and conn.get_transport() and conn.get_transport().is_active():
                return conn

        # 新建连接
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs = {
            "hostname": cfg.host,
            "port": cfg.port,
            "username": cfg.username,
            "timeout": SSH_CONNECT_TIMEOUT,
            "allow_agent": False,
            "look_for_keys": False,
        }

        if cfg.auth_type == "key" and cfg.key_path:
            pkey = None
            if cfg.passphrase:
                pkey = paramiko.RSAKey.from_private_key_file(
                    cfg.key_path, password=cfg.passphrase
                )
            else:
                pkey = paramiko.RSAKey.from_private_key_file(cfg.key_path)
            connect_kwargs["pkey"] = pkey
        else:
            connect_kwargs["password"] = cfg.password

        client.connect(**connect_kwargs)

        # 设置 keepalive
        transport = client.get_transport()
        if transport:
            transport.set_keepalive(SSH_KEEPALIVE_INTERVAL)

        with self._lock:
            # 如果超出最大连接数，关闭最旧的连接
            if len(self._connections) >= self._max:
                oldest_key = next(iter(self._connections))
                old_conn = self._connections.pop(oldest_key)
                try:
                    old_conn.close()
                except Exception:
                    pass
            self._connections[key] = client

        logger.info("SSH connected: %s", key)
        return client

    def close_connection(self, host: str, port: int, username: str):
        """关闭指定连接"""
        key = self._make_key(host, port, username)
        with self._lock:
            conn = self._connections.pop(key, None)
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
                logger.info("SSH disconnected: %s", key)

    def close_all(self):
        """关闭所有连接"""
        with self._lock:
            for key, conn in self._connections.items():
                try:
                    conn.close()
                except Exception:
                    pass
                logger.info("SSH disconnected: %s", key)
            self._connections.clear()

    def test_connectivity(self, server_config) -> tuple[bool, str]:
        """测试连通性，返回 (成功, 消息)"""
        try:
            client = self.get_connection(server_config)
            stdin, stdout, stderr = client.exec_command("echo ok", timeout=10)
            output = stdout.read().decode("utf-8").strip()
            if output == "ok":
                return True, "连接成功"
            return False, f"意外响应: {output}"
        except Exception as e:
            return False, f"连接失败: {e}"
