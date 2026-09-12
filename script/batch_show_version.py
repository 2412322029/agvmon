import asyncio
import csv
import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from util.ssh import SSHManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("batch_version")

INPUT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "2.csv")
OUTPUT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "version_result.csv")
MAX_CONCURRENT = 3

# 批量提取 castor_show_version 输出的 key/value 行, 如:
#   MAIN_VERSION       : V4.0.200build260623svn1854151
VERSION_LINE_RE = re.compile(r"^\s*([A-Z_]+)\s*:\s*(.+?)\s*$")


def parse_csv(filepath):
    """Read the device CSV, return list of (car_id, ip)."""
    devices = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) < 2:
                continue
            car_id = parts[0].strip()
            ip = parts[1].strip()
            devices.append((car_id, ip))
    return devices


def parse_versions(output):
    """从 castor_show_version 输出中解析 {KEY: value}。

    只取冒号左侧是全大写字母/下划线的行, 因此忽略
    "***********VERSION***INFO***********"、"castor running time:23h" 等噪声。
    """
    versions = {}
    for line in (output or "").splitlines():
        m = VERSION_LINE_RE.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        if key not in versions:
            versions[key] = value
    return versions


async def check_one_device(sem, car_id, ip):
    """Connect to one device and return (car_id, ip, versions, error)."""
    async with sem:
        ssh = SSHManager(ip, "", "")
        try:
            success, err = await ssh.agv_auto_connect()
            if not success:
                return (car_id, ip, {}, f"connect failed: {err}")
            _, output = await ssh.run_command(
                "sh -c 'export PATH=$PATH:/usr/sbin && castor_show_version'"
            )
            versions = parse_versions(output)
            if versions.get("MAIN_VERSION"):
                return (car_id, ip, versions, None)
            return (
                car_id,
                ip,
                versions,
                f"no MAIN_VERSION: {output[:120] if output else 'empty'}",
            )
        except Exception as e:
            return (car_id, ip, {}, str(e))
        finally:
            await ssh.disconnect()


async def main():
    devices = parse_csv(INPUT_CSV)
    logger.info(f"共 {len(devices)} 台设备待检查")

    sem = asyncio.Semaphore(MAX_CONCURRENT)
    tasks = [check_one_device(sem, car_id, ip) for car_id, ip in devices]

    results = []
    total = len(tasks)
    done = 0
    for coro in asyncio.as_completed(tasks):
        result = await coro
        results.append(result)
        done += 1
        car_id, ip, versions, err = result
        if err:
            logger.warning(f"[{done}/{total}] {car_id} {ip} -> ERROR: {err}")
        else:
            logger.info(
                f"[{done}/{total}] {car_id} {ip} -> MAIN_VERSION: {versions['MAIN_VERSION']}"
            )

    # Sort by car_id numerically
    results.sort(key=lambda x: int(x[0]) if x[0].isdigit() else 0)

    # Write output CSV
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["car_id", "ip", "MAIN_VERSION", "error"])
        for car_id, ip, versions, err in results:
            writer.writerow([car_id, ip, versions.get("MAIN_VERSION", ""), err or ""])

    ok = sum(1 for r in results if r[3] is None)
    fail = sum(1 for r in results if r[3] is not None)
    logger.info(f"完成: {ok} 成功, {fail} 失败, 结果保存至 {OUTPUT_CSV}")


if __name__ == "__main__":
    asyncio.run(main())
