"""SSH 远程命令执行器"""

import logging
import paramiko

from ..config import SSH_COMMAND_TIMEOUT

logger = logging.getLogger(__name__)


class SSHExecutor:
    """通过 SSH 执行远程命令"""

    def __init__(self, pool):
        """
        pool: SSHConnectionPool 实例
        """
        self._pool = pool

    def exec_command(self, server_config, command: str,
                     timeout: int = SSH_COMMAND_TIMEOUT) -> str:
        """
        执行远程命令，返回 stdout 文本。
        失败时抛出异常。
        """
        client = self._pool.get_connection(server_config)
        try:
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            exit_code = stdout.channel.recv_exit_status()

            if exit_code != 0 and not out:
                logger.warning("Command failed (exit=%d): %s -> %s",
                               exit_code, command[:80], err[:200])
                raise RuntimeError(f"Command exited {exit_code}: {err[:200]}")

            return out
        except (paramiko.SSHException, OSError, EOFError) as e:
            # 连接可能已断开，从池中移除
            self._pool.close_connection(
                server_config.host, server_config.port, server_config.username
            )
            raise RuntimeError(f"SSH error: {e}") from e

    def exec_commands(self, server_config, commands: list[str],
                      timeout: int = SSH_COMMAND_TIMEOUT) -> dict[str, str]:
        """
        批量执行命令，返回 {command: output} 字典。
        单条失败不影响其他命令。
        """
        results = {}
        for cmd in commands:
            try:
                results[cmd] = self.exec_command(server_config, cmd, timeout)
            except Exception as e:
                logger.error("Failed to exec '%s': %s", cmd[:60], e)
                results[cmd] = ""
        return results
