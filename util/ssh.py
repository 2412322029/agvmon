import json
import logging
import pathlib
import re

# import traceback
import uuid
from datetime import datetime
from typing import Dict, List, Union

import paramiko

logger = logging.getLogger(__name__)
# logging.basicConfig(level=logging.INFO)


class SSHManager:
    all_ssh_managers = []

    def __init__(self, host: str, username: str, password: str, port: int = 22):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self.client = None
        self.name = f"{self.username}@{self.host}"
        self.create_time = datetime.now()

    def connect(self) -> tuple[bool, str]:
        """建立SSH连接"""
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
            )
            self.id = uuid.uuid4().hex
            SSHManager.all_ssh_managers.append(
                {"id": self.id, "manager": self, "create_time": self.create_time, "name": self.name}
            )
            logger.info(f"SSH连接到 {self.name} 成功")
            return True, None
        except Exception as e:
            # traceback.print_exc()
            logger.error(f"SSH连接失败: {e}")
            return False, str(e)

    def disconnect(self):
        """断开SSH连接"""
        if self.client:
            self.client.close()
            logger.info(f"SSH连接 {self.name} 已断开")
            self.client = None
            for item in SSHManager.all_ssh_managers:
                if item["id"] == self.id:
                    SSHManager.all_ssh_managers.remove(item)
                    break
    
    def get_ssh_manager(id: str) -> "SSHManager":
        """根据id获取SSHManager实例"""
        for item in SSHManager.all_ssh_managers:
            if item["id"] == id:
                return item["manager"]
        return None
    
    def get_all_ssh_managers() -> List[Dict[str, Union[str, "SSHManager", datetime]]]:
        """获取所有SSHManager实例"""
        return [{"id": item["id"], "name": item["name"], "create_time": item["create_time"]} for item in SSHManager.all_ssh_managers]
    
    def execute_command(self, command: str, return_bytes: bool = False) -> tuple:
        """执行SSH命令并返回结果"""
        if not self.client:
            raise Exception("SSH连接未建立")

        try:
            stdin, stdout, stderr = self.client.exec_command(command)
            error = stderr.read().decode("utf-8", errors="ignore")

            if return_bytes:
                # 返回原始字节数据，用于二进制文件
                output = stdout.read()
            else:
                # 返回解码后的文本数据
                output = stdout.read().decode("utf-8", errors="ignore")

            return output, error
        except Exception as e:
            logger.error(f"执行命令失败: {e}")
            raise

    def execute_interactive_command(self, command: str):
        """执行交互式命令，返回stdin, stdout, stderr"""
        if not self.client:
            raise Exception("SSH连接未建立")

        try:
            stdin, stdout, stderr = self.client.exec_command(command)
            return stdin, stdout, stderr
        except Exception as e:
            logger.error(f"执行命令失败: {e}")
            raise

    def execute_command_text(self, command: str) -> tuple:
        """执行SSH命令并返回文本结果"""
        return self.execute_command(command, return_bytes=False)

    def parse_ls_output(self, ls_output: str) -> List[Dict[str, Union[str, int, bool]]]:
        """解析ls -l命令的输出为JSON格式"""
        lines = ls_output.strip().split("\n")
        result = []

        # 跳过第一行（如果是总计信息）并处理每一行
        for line in lines:
            # 跳过空行和总计行
            if not line.strip() or line.startswith("total"):
                continue

            # 解析ls -l的输出格式
            # 例如: -rw-r--r-- 1 user group 1024 Dec 10 12:34 filename
            # 或者带链接目标的格式: lrwxrwxrwx 1 user group 7 Dec 10 12:34 linkname -> target
            parts = re.split(r"\s+", line.strip(), 8)

            if len(parts) >= 9:
                try:
                    links = int(parts[1])
                except ValueError:
                    links = 0  # 如果链接数不是数字，则设为0

                try:
                    size = int(parts[4])
                except ValueError:
                    size = 0  # 如果大小不是数字，则设为0

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

                # 处理符号链接的情况，如果文件名包含 "->" 表示指向目标
                if " -> " in parts[8]:
                    name_parts = parts[8].split(" -> ")
                    file_info["name"] = name_parts[0]
                    file_info["link_target"] = name_parts[1]

                result.append(file_info)

        return result

    def list_directory(
        self, path: str = ".", parse: bool = True
    ) -> Union[List[Dict], str]:
        """列出目录内容"""
        command = f"ls -l '{path}'"
        output, error = self.execute_command_text(command)

        if error and not output:  # 只有在没有输出但有错误时才报错
            raise Exception(f"执行ls命令出错: {error}")

        if parse:
            return self.parse_ls_output(output)
        else:
            return output

    def list_directory_json(self, path: str = ".") -> str:
        """以JSON格式返回目录列表"""
        file_list = self.list_directory(path)
        return json.dumps(file_list, indent=2, ensure_ascii=False)

    def download_file(
        self, remote_path: str, local_path: str, block_size: int = 8192, callback=None
    ) -> bool:
        """下载远程文件到本地（非阻塞方式，支持进度回调）"""
        # 检查远程文件是否存在
        if not self.file_exists(remote_path):
            logger.error(f"错误: 远程文件 '{remote_path}' 不存在")
            return False
        local_file = pathlib.Path(local_path) / pathlib.Path(remote_path).name
        try:
            file_size = self.get_file_size(remote_path)
            if file_size < 0:
                # 如果无法获取文件大小，仍然可以下载，只是无法显示百分比进度
                file_size = 0
                logger.warning(
                    f"警告: 无法获取文件 '{remote_path}' 的大小，将只显示已下载字节"
                )

            # 使用dd命令读取文件，然后通过SSH传输到本地
            command = f"dd if='{remote_path}' bs={block_size}k 2>/dev/null"
            stdin, stdout, stderr = self.execute_interactive_command(command)

            # 非阻塞方式读取文件内容并写入本地文件
            downloaded_size = 0
            with open(local_file, "wb") as f:
                # 设置stdout为非阻塞模式
                import select

                while True:
                    # 检查是否有数据可读
                    ready, _, _ = select.select(
                        [stdout.channel], [], [], 1.0
                    )  # 1秒超时
                    if ready:
                        chunk = stdout.read(8192)  # 每次读取8KB
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded_size += len(chunk)

                        # 更新进度 - 传递已下载大小和总大小
                        if callback:
                            callback(downloaded_size, file_size)
                    else:
                        # 如果没有数据可读且通道关闭，则退出循环
                        if stdout.channel.exit_status_ready():
                            break

            logger.info(f"文件已通过dd命令下载到: {local_file}")
            return True
        except Exception as e2:
            logger.error(f"使用dd下载文件失败: {e2}")
            return False

    def stream_file(self, remote_path: str, chunk_size: int = 8192, callback=None):
        """流式读取远程文件内容，用于直接传输到HTTP响应"""
        # 检查远程文件是否存在
        if not self.file_exists(remote_path):
            logger.error(f"错误: 远程文件 '{remote_path}' 不存在")
            return
            
        try:
            file_size = self.get_file_size(remote_path)
            if file_size < 0:
                file_size = 0  # 无法获取文件大小时设为0
            
            # 使用dd命令读取文件，然后通过SSH传输
            command = f"dd if='{remote_path}' bs={chunk_size}k 2>/dev/null"
            stdin, stdout, stderr = self.execute_interactive_command(command)

            # 分块读取文件内容并生成返回
            downloaded_size = 0
            while True:
                chunk = stdout.read(chunk_size)
                if not chunk:
                    break
                downloaded_size += len(chunk)
                
                # 调用进度回调函数
                if callback:
                    callback(downloaded_size, file_size)
                # import time
                # time.sleep(1)
                yield chunk
        except Exception as e:
            logger.error(f"流式读取文件失败: {e}")

    def file_exists(self, remote_path: str) -> bool:
        """检查远程文件是否存在，使用ls命令"""
        try:
            # 使用ls命令检查文件是否存在
            command = f"ls -la '{remote_path}' 2>/dev/null"
            output, error = self.execute_command(command)
            # 如果命令执行成功且有输出，说明文件存在
            return len(output.strip()) > 0
        except Exception:
            # 如果出现异常，认为文件不存在
            return False

    def get_file_size(self, remote_path: str) -> int:
        """获取远程文件大小，使用ls -l命令"""
        if not self.file_exists(remote_path):
            return -1
        try:
            command = f"ls -l '{remote_path}'"
            output, error = self.execute_command_text(command)
            if error or not output:
                raise Exception(f"获取文件大小出错: {error}")
            # 解析ls -l输出，获取文件大小（第5个字段）
            parts = output.strip().split()
            if len(parts) >= 5:
                return int(parts[4])  # 第5个字段是文件大小
            else:
                return -1
        except Exception as e:
            logger.error(f"获取文件大小失败: {e}")
            return -1


def main():
    # 连接参数
    host = "172.26.126.120"
    username = "lolik"
    password = "123456"

    # 创建SSH管理器实例
    ssh_manager = SSHManager(host, username, password)

    try:
        ssh_manager.connect()
        file_size = ssh_manager.get_file_size("/home/lolik/22.pcapng")
        logger.info(f"文件大小: {file_size} bytes")
        logger.info("尝试下载一个文件...")

        # 测试带进度回调的下载
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

        success = ssh_manager.download_file(
            "/home/lolik/22.pcapng",
            "D:\\24123\\code\\py\\agvmon",
            callback=progress_callback,
        )
        if success:
            logger.info("文件下载成功!")
        else:
            logger.error("文件下载失败!")
    finally:
        # 断开连接
        ssh_manager.disconnect()


if __name__ == "__main__":
    main()
