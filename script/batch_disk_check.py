import asyncio
import csv
import logging
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ssh import SSHManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("batch_disk")

INPUT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "1.csv")
OUTPUT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "disk_usage_result.csv")
MAX_CONCURRENT = 3

# Regex to extract "precent 90" -> 90
PERCENT_RE = re.compile(r"precent\s+(\d+)", re.IGNORECASE)


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


async def check_one_device(sem, car_id, ip):
    """Connect to one device and return (car_id, ip, percent, error)."""
    async with sem:
        ssh = SSHManager(ip,"","")
        try:
            success, err = await ssh.agv_auto_connect()
            if not success:
                return (car_id, ip, None, f"connect failed: {err}")
            _, output = await ssh.run_command(
                "sh -c 'export PATH=$PATH:/usr/sbin && castor_show_log_record_monitor'"
            )
            m = PERCENT_RE.search(output or "")
            if m:
                return (car_id, ip, int(m.group(1)), None)
            else:
                return (car_id, ip, None, f"no match: {output[:120] if output else 'empty'}")
        except Exception as e:
            return (car_id, ip, None, str(e))
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
        car_id, ip, percent, err = result
        if err:
            logger.warning(f"[{done}/{total}] {car_id} {ip} -> ERROR: {err}")
        else:
            logger.info(f"[{done}/{total}] {car_id} {ip} -> {percent}%")

    # Sort by car_id numerically
    results.sort(key=lambda x: int(x[0]) if x[0].isdigit() else 0)

    # Write output CSV
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["car_id", "ip", "disk_percent", "error"])
        for car_id, ip, percent, err in results:
            writer.writerow([car_id, ip, percent if percent is not None else "", err or ""])

    ok = sum(1 for r in results if r[3] is None)
    fail = sum(1 for r in results if r[3] is not None)
    logger.info(f"完成: {ok} 成功, {fail} 失败, 结果保存至 {OUTPUT_CSV}")


if __name__ == "__main__":
    asyncio.run(main())
