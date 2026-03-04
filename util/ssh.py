import asyncio
import json
import logging
import pathlib
import re

# import traceback
import uuid
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple, Union

import asyncssh

logger = logging.getLogger(__name__)


def validate_remote_path(path: str) -> bool:
    """
    验证远程路径，防止命令注入
    
    参数:
        path: 远程文件路径
        
    返回:
        bool: 路径是否有效
    """
    if not path:
        return False
    
    if not isinstance(path, str):
        return False
    
    path = path.strip()
    
    if not path:
        return False
    
    forbidden_patterns = [
        r";\s*",
        r"\|\s*",
        r"&\s*",
        r"\$\(",
        r"`",
        r"\\",
        r"\n",
        r"\r",
        r"\x00",
    ]
    
    for pattern in forbidden_patterns:
        if re.search(pattern, path):
            logger.warning(f"检测到非法字符，路径被拒绝: {path}")
            return False
    
    if path.startswith("-"):
        logger.warning(f"路径不能以连字符开头: {path}")
        return False
    
    if ".." in path:
        logger.warning(f"路径不能包含 '..': {path}")
        return False
    
    if not re.match(r'^[a-zA-Z0-9_\-./]+$', path):
        logger.warning(f"路径包含非法字符: {path}")
        return False
    
    return True


def validate_local_path(path: str) -> bool:
    """
    验证本地路径，防止命令注入和路径遍历
    
    参数:
        path: 本地文件路径
        
    返回:
        bool: 路径是否有效
    """
    if not path:
        return False
    
    if not isinstance(path, str):
        return False
    
    path = path.strip()
    
    if not path:
        return False
    
    forbidden_patterns = [
        r";\s*",
        r"\|\s*",
        r"&\s*",
        r"\$\(",
        r"`",
        r"\n",
        r"\r",
        r"\x00",
    ]
    
    for pattern in forbidden_patterns:
        if re.search(pattern, path):
            logger.warning(f"检测到非法字符，路径被拒绝: {path}")
            return False
    
    try:
        path_obj = pathlib.Path(path)
        resolved = path_obj.resolve()
        
        if ".." in str(resolved.relative_to(resolved.anchor)):
            logger.warning(f"路径包含非法的相对路径: {path}")
            return False
    except Exception as e:
        logger.warning(f"路径验证失败: {path}, 错误: {e}")
        return False
    
    return True

# 配置 asyncssh 日志级别,只显示关键信息
asyncssh.set_log_level(logging.WARNING)


class SSHManager:
    all_ssh_managers = []

    def __init__(self, host: str, username: str, password: str, port: int = 22):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.connection: Optional[asyncssh.SSHClientConnection] = None
        self.name = f"{self.username}@{self.host}"
        self.create_time = datetime.now()

    async def connect(self) -> Tuple[bool, Optional[str]]:
        """建立SSH连接"""
        try:
            self.connection = await asyncssh.connect(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                connect_timeout=8,
            )
            self.id = uuid.uuid4().hex
            SSHManager.all_ssh_managers.append(
                {"id": self.id, "manager": self, "create_time": self.create_time, "name": self.name}
            )
            logger.info(f"SSH连接到 {self.name} 成功")
            return True, None
        except asyncio.TimeoutError:
            logger.error(f"SSH连接超时: {self.name}")
            return False, "连接超时"
        except Exception as e:
            logger.error(f"SSH连接失败: {e}")
            return False, str(e)

    async def disconnect(self):
        """断开SSH连接"""
        if self.connection:
            self.connection.close()
            await self.connection.wait_closed()
            logger.info(f"SSH连接 {self.name} 已断开")
            self.connection = None
            for item in SSHManager.all_ssh_managers:
                if item["id"] == self.id:
                    SSHManager.all_ssh_managers.remove(item)
                    break

    @staticmethod
    def get_ssh_manager(id: str) -> Optional["SSHManager"]:
        """根据id获取SSHManager实例"""
        for item in SSHManager.all_ssh_managers:
            if item["id"] == id:
                return item["manager"]
        return None

    @staticmethod
    def get_all_ssh_managers() -> List[Dict[str, Union[str, "SSHManager", datetime]]]:
        """获取所有SSHManager实例"""
        return [{"id": item["id"], "name": item["name"], "create_time": item["create_time"]} for item in SSHManager.all_ssh_managers]

    async def execute_command(self, command: str, return_bytes: bool = False) -> Tuple[Union[str, bytes], str]:
        """执行SSH命令并返回结果"""
        if not self.connection:
            raise Exception("SSH连接未建立")

        try:
            result = await self.connection.run(command, check=False)
            error = result.stderr

            if return_bytes:
                output = result.stdout_bytes
            else:
                output = result.stdout

            return output, error
        except Exception as e:
            logger.error(f"执行命令失败: {e}")
            raise

    async def execute_interactive_command(self, command: str) -> Tuple[Optional[asyncssh.SSHWriter], asyncssh.SSHReader, asyncssh.SSHReader]:
        """执行交互式命令，返回stdin, stdout, stderr"""
        if not self.connection:
            raise Exception("SSH连接未建立")

        try:
            process = await self.connection.run(command, stdin=asyncssh.PIPE, stdout=asyncssh.PIPE, stderr=asyncssh.PIPE)
            return process.stdin, process.stdout, process.stderr
        except Exception as e:
            logger.error(f"执行命令失败: {e}")
            raise

    async def execute_command_text(self, command: str) -> Tuple[str, str]:
        """执行SSH命令并返回文本结果"""
        output, error = await self.execute_command(command, return_bytes=False)
        return output, error

    def parse_ls_output(self, ls_output: str) -> List[Dict[str, Union[str, int, bool]]]:
        """解析ls -l命令的输出为JSON格式"""
        lines = ls_output.strip().split("\n")
        result = []

        for line in lines:
            if not line.strip() or line.startswith("total"):
                continue

            parts = re.split(r"\s+", line.strip(), 8)

            if len(parts) >= 9:
                try:
                    links = int(parts[1])
                except ValueError:
                    links = 0

                try:
                    size = int(parts[4])
                except ValueError:
                    size = 0

                file_info = {
                    "permissions": parts[0],
                    "links": links,
                    "owner": parts[2],
                    "size": size,
                    "month": parts[5],
                    "day": parts[6],
                    "time_or_year": parts[7],
                    "name": parts[8],
                    "is_directory": parts[0].startswith("d"),
                    "is_link": parts[0].startswith("l"),
                    "is_file": parts[0].startswith("-"),
                }

                if " -> " in parts[8]:
                    name_parts = parts[8].split(" -> ")
                    file_info["name"] = name_parts[0]
                    file_info["link_target"] = name_parts[1]

                result.append(file_info)

        return result

    async def list_directory(
        self, path: str = ".", parse: bool = True
    ) -> Union[List[Dict], str]:
        """列出目录内容"""
        if not validate_remote_path(path):
            raise ValueError(f"无效的远程路径: {path}")
        
        command = f"ls -l '{path}'"
        output, error = await self.execute_command_text(command)

        if error and not output:
            raise Exception(f"执行ls命令出错: {error}")

        if parse:
            return self.parse_ls_output(output)
        else:
            return output

    async def list_directory_json(self, path: str = ".") -> str:
        """以JSON格式返回目录列表"""
        if not validate_remote_path(path):
            raise ValueError(f"无效的远程路径: {path}")
        
        file_list = await self.list_directory(path)
        return json.dumps(file_list, indent=2, ensure_ascii=False)

    async def download_file(
        self, remote_path: str, local_path: str, block_size: int = 8192, callback: Optional[Callable[[int, int], None]] = None
    ) -> bool:
        """下载远程文件到本地（支持进度回调）"""
        if not validate_remote_path(remote_path):
            raise ValueError(f"无效的远程路径: {remote_path}")
        
        if not validate_local_path(local_path):
            raise ValueError(f"无效的本地路径: {local_path}")
        
        local_file = pathlib.Path(local_path) / pathlib.Path(remote_path).name
        
        try:
            file_info = await self._get_file_info(remote_path)
            if not file_info["exists"]:
                logger.error(f"错误: 远程文件 '{remote_path}' 不存在")
                return False
            
            file_size = file_info["size"]
            if file_size < 0:
                file_size = 0
                logger.warning(
                    f"警告: 无法获取文件 '{remote_path}' 的大小，将只显示已下载字节"
                )

            command = f"dd if='{remote_path}' bs={block_size}k 2>/dev/null"
            stdin, stdout, stderr = await self.execute_interactive_command(command)

            downloaded_size = 0
            with open(local_file, "wb") as f:
                while True:
                    chunk = await stdout.read(block_size * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded_size += len(chunk)

                    if callback:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(downloaded_size, file_size)
                        else:
                            callback(downloaded_size, file_size)

            logger.info(f"文件已通过dd命令下载到: {local_file}")
            return True
        except Exception as e:
            logger.error(f"使用dd下载文件失败: {e}")
            return False

    async def stream_file(
        self, remote_path: str, chunk_size: int = 8192, callback: Optional[Callable[[int, int], None]] = None
    ):
        """流式读取远程文件内容，用于直接传输到HTTP响应"""
        if not validate_remote_path(remote_path):
            raise ValueError(f"无效的远程路径: {remote_path}")
        
        try:
            file_info = await self._get_file_info(remote_path)
            if not file_info["exists"]:
                logger.error(f"错误: 远程文件 '{remote_path}' 不存在")
                return
            
            file_size = file_info["size"]
            if file_size < 0:
                file_size = 0
            
            command = f"dd if='{remote_path}' bs={chunk_size}k 2>/dev/null"
            stdin, stdout, stderr = await self.execute_interactive_command(command)

            downloaded_size = 0
            while True:
                chunk = await stdout.read(chunk_size * 1024)
                if not chunk:
                    break
                downloaded_size += len(chunk)
                
                if callback:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(downloaded_size, file_size)
                    else:
                        callback(downloaded_size, file_size)
                
                yield chunk
        except Exception as e:
            logger.error(f"流式读取文件失败: {e}")

    async def _get_file_info(self, remote_path: str) -> Dict[str, Union[bool, int]]:
        """获取文件信息（存在性和大小），单次SSH会话完成"""
        if not validate_remote_path(remote_path):
            raise ValueError(f"无效的远程路径: {remote_path}")
        
        try:
            command = f"ls -la '{remote_path}' 2>/dev/null && echo '---SIZE---' && ls -l '{remote_path}' 2>/dev/null"
            output, error = await self.execute_command(command)
            
            if error or not output.strip():
                return {"exists": False, "size": -1}
            
            lines = output.strip().split("\n")
            
            if len(lines) < 2:
                return {"exists": False, "size": -1}
            
            ls_la_line = lines[0]
            ls_l_line = lines[-1]
            
            if not ls_l_line or ls_l_line.startswith("total"):
                return {"exists": False, "size": -1}
            
            parts = ls_l_line.split()
            if len(parts) >= 5:
                try:
                    size = int(parts[4])
                    return {"exists": True, "size": size}
                except ValueError:
                    return {"exists": True, "size": -1}
            
            return {"exists": True, "size": -1}
        except Exception:
            return {"exists": False, "size": -1}

    async def file_exists(self, remote_path: str) -> bool:
        """检查远程文件是否存在，使用ls命令"""
        if not validate_remote_path(remote_path):
            return False
        
        try:
            command = f"ls -la '{remote_path}' 2>/dev/null"
            output, error = await self.execute_command(command)
            return len(output.strip()) > 0
        except Exception:
            return False

    async def get_file_size(self, remote_path: str) -> int:
        """获取远程文件大小，使用ls -l命令"""
        if not validate_remote_path(remote_path):
            return -1
        
        if not await self.file_exists(remote_path):
            return -1
        try:
            command = f"ls -l '{remote_path}'"
            output, error = await self.execute_command_text(command)
            if error or not output:
                raise Exception(f"获取文件大小出错: {error}")
            parts = output.strip().split()
            if len(parts) >= 5:
                return int(parts[4])
            else:
                return -1
        except Exception as e:
            logger.error(f"获取文件大小失败: {e}")
            return -1


async def main():
    host = "172.26.126.120"
    username = "lolik"
    password = "123456"

    ssh_manager = SSHManager(host, username, password)

    try:
        success, error = await ssh_manager.connect()
        if not success:
            logger.error(f"连接失败: {error}")
            return
        
        file_size = await ssh_manager.get_file_size("/home/lolik/22.pcapng")
        logger.info(f"文件大小: {file_size} bytes")
        logger.info("尝试下载一个文件...")

        def progress_callback(downloaded, total):
            if total and total > 0:
                percent = (downloaded / total) * 100
                bar_length = 30
                filled_length = int(bar_length * downloaded // total)
                bar = "█" * filled_length + "-" * (bar_length - filled_length)
                print(
                    f"\r|{bar}| {percent:.1f}% ({downloaded}/{total} bytes)",
                    end="",
                    flush=True,
                )
            else:
                print(f"\r已下载: {downloaded} bytes", end="", flush=True)

        success = await ssh_manager.download_file(
            "/home/lolik/22.pcapng",
            "D:\\24123\\code\\py\\agvmon",
            callback=progress_callback,
        )
        if success:
            logger.info("文件下载成功!")
        else:
            logger.error("文件下载失败!")
    finally:
        await ssh_manager.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
