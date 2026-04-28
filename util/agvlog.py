import asyncio
import datetime
import logging
import os
import subprocess
from ipaddress import ip_address

# import time
from util.logger import logger
from util.ssh import SSHManager

agv_log_dir = os.path.join(os.path.dirname(__file__), "data", "agvlog")
if not os.path.exists(agv_log_dir):
    os.makedirs(agv_log_dir)


def parse_time_from_filename(filename: str):
    """
    解析时间字符串为时间对象

    Args:
        filename: 时间字符串，格式为 AGV_2026_04_24_13_01_15_CASTOR_1032

    Returns:
        datetime.datetime: 时间对象
    """
    return datetime.datetime.strptime(
        "_".join(filename.split("_")[1:7]), "%Y_%m_%d_%H_%M_%S"
    )


def parse_agv_log(log_filename: str):
    """
    使用 parsezlib_2_7_8.exe 工具解析 AGV 日志文件

    Args:
        log_filename: AGV 日志文件名

    Returns:
        tuple: 生成的 txt 文件路径和AGV编号
    """
    if not log_filename.startswith("AGV_"):
        raise ValueError(f"AGV 日志文件名必须以 AGV_ 开头: {log_filename}")
    carid = log_filename.split("_CASTOR_")[1]

    # 先检查当前目录
    log_file_path = os.path.join(os.path.dirname(__file__), log_filename)
    if not os.path.exists(log_file_path):
        # 再检查 data/agvlog 目录
        log_file_path = os.path.join(agv_log_dir, log_filename)
        if not os.path.exists(log_file_path):
            raise FileNotFoundError(f"AGV 日志文件不存在: {log_file_path}")

    # 获取文件所在目录
    log_dir = os.path.dirname(log_file_path)
    log_filename = os.path.basename(log_file_path)

    # 构建 parsezlib 工具路径
    parsezlib_exe = os.path.join(
        os.path.dirname(__file__), "tool", "parsezlib_2_7_8.exe"
    )

    if not os.path.exists(parsezlib_exe):
        raise FileNotFoundError(f"parsezlib 工具不存在: {parsezlib_exe}")

    # 生成的 txt 文件名格式: {编号}_{原文件名}_CASTOR.txt
    # 从原文件名提取编号，例如 AGV_2026_04_24_15_15_12_CASTOR_1032 -> 1032
    parts = log_filename.split("_")
    if len(parts) > 0:
        suffix = parts[-1]
        if suffix.isdigit():
            txt_filename = f"{suffix}_{'_'.join(parts[:-1])}.txt"
            txt_file_path = os.path.join(log_dir, txt_filename)
            if os.path.exists(txt_file_path):
                logger.info(f"AGV日志文件 {log_filename} 已解析，直接返回 txt 文件")
                return txt_file_path, carid

    # 执行解析命令
    try:
        result = subprocess.run(
            [parsezlib_exe, log_filename],
            cwd=log_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        logger.info(f"解析AGV日志文件 {log_filename} 输出: {result.stdout.strip()}")

        # 生成的 txt 文件名格式: {编号}_{原文件名}_CASTOR.txt
        # 从原文件名提取编号，例如 AGV_2026_04_24_15_15_12_CASTOR_1032 -> 1032
        parts = log_filename.split("_")
        if len(parts) > 0:
            suffix = parts[-1]
            if suffix.isdigit():
                txt_filename = f"{suffix}_{'_'.join(parts[:-1])}.txt"
                txt_file_path = os.path.join(log_dir, txt_filename)
                if os.path.exists(txt_file_path):
                    return txt_file_path, carid

        # 如果无法解析文件名格式，返回目录下最新的 txt 文件
        txt_files = [f for f in os.listdir(log_dir) if f.endswith(".txt")]
        if txt_files:
            txt_files.sort(
                key=lambda x: os.path.getmtime(os.path.join(log_dir, x)), reverse=True
            )
            return os.path.join(log_dir, txt_files[0])

        raise Exception("解析成功但未找到生成的 txt 文件")

    except subprocess.CalledProcessError as e:
        raise Exception(f"解析失败: {e.stderr.strip()}")
    except Exception as e:
        raise Exception(f"解析过程出错: {str(e)}")


def parse_agv_logs(log_filenames: list[str]):
    if len(log_filenames) == 0:
        raise ValueError("AGV 日志文件列表不能为空")
    if len(log_filenames) > 5:
        raise ValueError("AGV 日志文件列表最多只能包含5个文件")
    if len(set(log_filenames)) != len(log_filenames):
        raise ValueError("AGV 日志文件列表中包含重复文件")

    carids = []
    for log_filename in log_filenames:
        carid = log_filename.split("_CASTOR_")[1]
        carids.append(carid)
    if len(set(carids)) != 1:
        raise ValueError(
            f"AGV 日志文件必须是同一个AGV的多个文件,当前文件包含多个AGV编号: {set(carids)}"
        )
    carid = carids[0]
    # 按时间排序
    log_filenames.sort(key=lambda x: parse_time_from_filename(x))

    txt_files = []
    for log_filename in log_filenames:
        txt_file_path, _ = parse_agv_log(log_filename)
        txt_files.append(txt_file_path)
    return txt_files, carid


def find_str(log_file_paths: list[str], search_pattern):
    """
    高效查找日志文件中包含指定字符串 的所有行

    Args:
        log_file_paths: 日志文件路径列表

    Returns:
        list: 包含匹配行的列表，每个元素为 (行号, 行内容)
    """
    matching_lines = []
    for log_file_path in log_file_paths:
        if not os.path.exists(log_file_path):
            logger.warning(f"日志文件不存在: {log_file_path}")
            continue

        # 使用生成器逐行读取，避免一次性加载整个文件到内存
        with open(log_file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line_number, line in enumerate(f, 1):
                if search_pattern in line:
                    matching_lines.append((line_number, line.strip()))

    return matching_lines


def parse_pio_log_line(log_line):
    """
    解析AGV PIO检查日志行

    Args:
        log_line: 日志行字符串，格式如：[2026-04-24 15:19:00][60984][NOTIC][ROL]agv_check_pio_input result 1 pio_value 8d

    Returns:
        dict: 包含解析结果的字典，包括：
            - time: 时间字符串
            - line_number: 日志轮转行数
            - pio_result: 得到的pio值
            - pio_value: 需要的pio值
    """
    import re

    # 匹配日志行格式
    pattern = r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\[(\d+)\].*?agv_check_pio_input result (\d+) pio_value (\w+)"
    match = re.match(pattern, log_line)

    if not match:
        raise ValueError(f"无效的日志行格式: {log_line}")

    return {
        "time": match.group(1),
        "line_number": int(match.group(2)),
        "pio_result": int(match.group(3)),
        "pio_value": match.group(4),
    }


def merge_pio_logs(log_lines):
    """
    合并result和pio_value相同的日志行

    Args:
        log_lines: 日志行列表，每个元素为 (行号, 行内容)

    Returns:
        list: 合并后的结果列表，每个元素为：
            {
                'start_time': 开始时间,
                'end_time': 结束时间,
                'start_line': 开始行号,
                'end_line': 结束行号,
                'pio_result': 得到的pio值（十进制）,
                'pio_result_bin': 得到的pio值（二进制）,
                'pio_value': 需要的pio值（16进制）,
                'pio_value_bin': 需要的pio值（二进制）,
                'count': 合并的行数
            }
    """
    if not log_lines:
        return []

    # 先解析所有日志行
    parsed_logs = []
    for line_num, line in log_lines:
        try:
            parsed = parse_pio_log_line(line)
            parsed_logs.append(parsed)
        except ValueError:
            continue

    if not parsed_logs:
        return []

    # 按时间排序
    parsed_logs.sort(key=lambda x: x["time"])

    # 合并相同result和pio_value的记录
    merged = []
    current_group = None

    for log in parsed_logs:
        key = (log["pio_result"], log["pio_value"])

        if not current_group:
            # 开始新组
            # 将16进制转换为二进制
            try:
                pio_value_bin = bin(int(log["pio_value"], 16))[2:].zfill(8)  # 8位二进制
            except ValueError:
                pio_value_bin = log["pio_value"]

            # 将得到的pio值转换为二进制
            pio_result_bin = bin(log["pio_result"])[2:].zfill(8)  # 8位二进制

            current_group = {
                "start_time": log["time"],
                "end_time": log["time"],
                "start_line": log["line_number"],
                "end_line": log["line_number"],
                "pio_result": log["pio_result"],
                "pio_result_bin": pio_result_bin,
                "pio_value": log["pio_value"],
                "pio_value_bin": pio_value_bin,
                "count": 1,
            }
        else:
            current_key = (current_group["pio_result"], current_group["pio_value"])
            if current_key == key:
                # 同一组，更新结束时间和行数
                current_group["end_time"] = log["time"]
                current_group["end_line"] = log["line_number"]
                current_group["count"] += 1
            else:
                # 不同组，保存当前组并开始新组
                merged.append(current_group)

                # 将16进制转换为二进制
                try:
                    pio_value_bin = bin(int(log["pio_value"], 16))[2:].zfill(
                        8
                    )  # 8位二进制
                except ValueError:
                    pio_value_bin = log["pio_value"]

                # 将得到的pio值转换为二进制
                pio_result_bin = bin(log["pio_result"])[2:].zfill(8)  # 8位二进制

                current_group = {
                    "start_time": log["time"],
                    "end_time": log["time"],
                    "start_line": log["line_number"],
                    "end_line": log["line_number"],
                    "pio_result": log["pio_result"],
                    "pio_result_bin": pio_result_bin,
                    "pio_value": log["pio_value"],
                    "pio_value_bin": pio_value_bin,
                    "count": 1,
                }

    # 保存最后一组
    if current_group:
        merged.append(current_group)

    return merged


def get_pio_result(filenames: list[str]):
    """
    从日志文件中提取pio_result合并分析

    Args:
        filenames: 日志文件列表

    Returns:
        list: 包含pio_result的列表
    """
    log_filenames, carid = parse_agv_logs(filenames)
    logger.info(f"parsed AGV ID: {carid}")
    # 从文件中查找并解析日志行
    lines = find_str(log_filenames, "agv_check_pio_input")
    logger.info(f"找到 {len(lines)} 行包含 agv_check_pio_input")
    merged_logs = merge_pio_logs(lines)
    return merged_logs


async def download_agv_logs(
    ip_or_carid: str, filenames: list[str] = [], prefix: str = "/mnt/agv_log/", new_count=1
):
    """
     从AGV下载日志文件
    : ip_or_carid: AGV IP地址
    : new_count: 最新的几个文件
    : filenames: 日志文件列表
    : prefix: 日志文件路径前缀，默认"/mnt/agv_log/"
    :return: 下功下载的文件列表
    """
    ip = getip_from_carid(ip_or_carid) or ip_or_carid
    if not ip_address(ip):
        raise ValueError(f"IP地址 {ip_or_carid} 无效")
    carid = ip_or_carid if "." not in ip_or_carid else None
    for filename in filenames:
        if not filename.startswith("AGV_"):
            raise ValueError(f"文件 {filename} 不以AGV_开头!")
    ssh_manager = SSHManager(ip, username="", password="")
    if not prefix.endswith("/"):
        prefix += "/"

    def format_size(size):
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"

    def progress_callback(downloaded: int, total: int):
        if total > 0:
            # time.sleep(0.5)
            percentage = (downloaded / total) * 100
            print(
                f"\r下载进度: {percentage:.1f}% ({format_size(downloaded)}/{format_size(total)})",
                end="",
                flush=True,
            )
        else:
            print(f"\r已下载: {format_size(downloaded)}", end="", flush=True)

    try:
        success_download_file = []
        await ssh_manager.agv_auto_connect()
        if not filenames:  # 如果没有指定文件名，从AGV获取最新文件
            res = await ssh_manager.list_directory(path=f"/{prefix.strip('/')}")
            agv_files = [
                f for f in res if f.get("is_file") and f.get("name", "").startswith("AGV_")
            ]
            agv_files.sort(key=lambda x: parse_time_from_filename(x["name"]), reverse=True)
            filenames = [f["name"] for f in agv_files[:new_count]]
            logger.info(f"找到 {len(filenames)} 个最新AGV日志文件: {filenames}")
        existsfile = os.listdir(agv_log_dir)
        for filename in filenames:
            if carid and not filename.endswith(carid):
                logger.warning(f"文件 {filename} 不匹配AGV ID {carid}, 跳过")
                continue
                
            if filename in existsfile:
                logger.info(f"文件已存在: {filename}, 跳过")
                success_download_file.append(filename)
                continue
            logger.info(f"开始下载: {filename}")
            success = await ssh_manager.download_file(
                remote_path=f"{prefix}{filename}",
                local_path=agv_log_dir,
                callback=progress_callback,
            )
            print()
            if not success:
                logger.error(f"下载日志失败: {filename}")
                continue
            else:
                logger.info(f"下载日志成功: {filename}")
                success_download_file.append(filename)
        logger.info(f"成功下载 {len(success_download_file)} 个文件")
        return success_download_file
    finally:
        await ssh_manager.disconnect()


pio_info_map = [
    "正常状态  ",
    "上仓位    ",
    "下仓位    ",
    "上料请求  ",
    "下料请求  ",
    "滚动信号  ",
    "完成信号  ",
    "tray盘大小",
]


def print_merged_info(merged_logs):
    def format_binary_comparison(result_bin, value_bin):
        result_bin = result_bin.zfill(len(result_bin))
        value_bin = value_bin.zfill(len(value_bin))
        mismatches = []
        lines = []
        for idx in range(len(result_bin)):
            r_bit = result_bin[idx]
            v_bit = value_bin[idx]
            bit_pos = len(result_bin) - 1 - idx
            if r_bit != v_bit:
                lines.append(
                    f" {bit_pos} {pio_info_map[::-1][idx]} : {r_bit} | {v_bit} \033[31m[X]\033[0m "
                )
            else:
                lines.append(
                    f" {bit_pos} {pio_info_map[::-1][idx]} : {r_bit} | {v_bit} \033[32m[√]\033[0m"
                )
        result_lines = lines[::-1]
        if mismatches:
            result_lines.extend(mismatches[::-1])
        return "\n".join(result_lines)

    for i, group in enumerate(merged_logs, 1):
        print(f"\n组 {i}:")
        print(
            f"[{group['start_time']} ~ {group['end_time']}], line ({group['start_line']} ~ {group['end_line']}) 合并行数: {group['count']}"
        )
        print(
            f"  得到,需要的pio值(16进制): {group['pio_result']}, {group['pio_value']}"
        )
        print(format_binary_comparison(group["pio_result_bin"], group["pio_value_bin"]))

def getip_from_carid(carid: str) -> str:
    d = {"1032": "172.26.126.120","3002": "172.26.126.120" }
    return d.get(carid, "")


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    files = asyncio.run(
        download_agv_logs(
            "172.26.126.120",
            prefix="/mnt/d/24123/code/py/agvmon/util/data/agvlog/",
            new_count=2,
        )
    )
    merged_logs = get_pio_result(files)
    print_merged_info(merged_logs)
