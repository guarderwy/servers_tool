"""SSH 凭据加密存储管理"""

import json
import logging
from pathlib import Path
from typing import Optional

from ..config import CREDENTIALS_FILE, CONFIG_FILE
from ..utils.encryption import encrypt_json, decrypt_json
from ..core.models import ServerConfig

logger = logging.getLogger(__name__)


class CredentialsManager:
    """管理加密的 SSH 凭据"""

    def __init__(self):
        self._password: Optional[str] = None
        self._servers: dict[str, ServerConfig] = {}
        self._loaded = False

    def set_password(self, password: str):
        """设置主密码"""
        self._password = password

    @property
    def is_unlocked(self) -> bool:
        return self._password is not None

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def save(self):
        """加密并保存所有服务器配置到文件"""
        if not self._password:
            raise RuntimeError("未设置主密码")

        data = {}
        for sid, srv in self._servers.items():
            d = srv.to_dict()
            # 敏感字段单独保存
            d["password"] = srv.password
            d["key_path"] = srv.key_path
            d["passphrase"] = srv.passphrase
            data[sid] = d

        encrypted = encrypt_json(data, self._password)
        CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        CREDENTIALS_FILE.write_text(encrypted, encoding="utf-8")
        logger.info("Credentials saved to %s", CREDENTIALS_FILE)

    def load(self, password: str) -> bool:
        """
        尝试用密码加载凭据。
        返回 True 表示成功。
        """
        self._password = password

        if not CREDENTIALS_FILE.exists():
            self._servers = {}
            self._loaded = True
            return True

        try:
            encrypted = CREDENTIALS_FILE.read_text(encoding="utf-8")
            data = decrypt_json(encrypted, password)
            self._servers = {}
            for sid, d in data.items():
                self._servers[sid] = ServerConfig(
                    id=d["id"],
                    name=d["name"],
                    host=d["host"],
                    port=d.get("port", 22),
                    username=d.get("username", "root"),
                    auth_type=d.get("auth_type", "password"),
                    password=d.get("password"),
                    key_path=d.get("key_path"),
                    passphrase=d.get("passphrase"),
                    tags=d.get("tags", []),
                    enabled=d.get("enabled", True),
                )
            self._loaded = True
            logger.info("Loaded %d servers", len(self._servers))
            return True
        except Exception as e:
            logger.error("Failed to load credentials: %s", e)
            self._password = None
            self._loaded = False
            return False

    def get_servers(self) -> list[ServerConfig]:
        return list(self._servers.values())

    def get_server(self, server_id: str) -> Optional[ServerConfig]:
        return self._servers.get(server_id)

    def add_server(self, server: ServerConfig):
        self._servers[server.id] = server
        self.save()

    def update_server(self, server: ServerConfig):
        self._servers[server.id] = server
        self.save()

    def remove_server(self, server_id: str):
        self._servers.pop(server_id, None)
        self.save()


# ========== 非敏感配置（不需要加密） ==========

def load_config() -> dict:
    """加载非敏感配置"""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_config(data: dict):
    """保存非敏感配置"""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
