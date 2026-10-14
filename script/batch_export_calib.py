import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from util.net.ssh import SSHManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("batch_export")

INPUT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "1.csv")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calib_export")
MAX_CONCURRENT = 3

# 远程文件路径
SEC_BIN_REMOTE = "/mnt/sec.bin"
CALIB_JSON_REMOTE = "/mnt/all_calib_data.json"


def parse_csv(filepath):
    """读取设备CSV，返回 (car_id, ip) 列表"""
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


async def export_one_device(sem, car_id, ip):
    """连接一台设备，导出 sec.bin 和 all_calib_data.json"""
    async with sem:
        car_dir = os.path.join(OUTPUT_DIR, car_id)
        os.makedirs(car_dir, exist_ok=True)

        ssh = SSHManager(ip, "", "")
        try:
            # 1. 连接
            success, err = await ssh.agv_auto_connect()
            if not success:
                return (car_id, ip, f"connect failed: {err}")

            # 2. 导出 sec.bin
            ok, output = await ssh.run_command(
                "sh -c 'export PATH=$PATH:/usr/sbin && castor_export_sec_bin'"
            )
            if not ok:
                return (car_id, ip, f"castor_export_sec_bin failed: {output}")
            logger.info(f"[{car_id}] castor_export_sec_bin 完成")

            # 3. 下载 sec.bin
            ok = await ssh.download_file(
                remote_path=SEC_BIN_REMOTE,
                local_path=car_dir,
            )
            if not ok:
                return (car_id, ip, f"download {SEC_BIN_REMOTE} failed")
            logger.info(f"[{car_id}] sec.bin 下载完成")

            # 4. 导出 all_calib_data.json
            ok, output = await ssh.run_command(
                "sh -c 'export PATH=$PATH:/usr/sbin && castor_export_all_calib_data_to_json'"
            )
            if not ok:
                return (car_id, ip, f"castor_export_all_calib_data_to_json failed: {output}")
            logger.info(f"[{car_id}] castor_export_all_calib_data_to_json 完成")

            # 5. 下载 all_calib_data.json
            ok = await ssh.download_file(
                remote_path=CALIB_JSON_REMOTE,
                local_path=car_dir,
            )
            if not ok:
                return (car_id, ip, f"download {CALIB_JSON_REMOTE} failed")
            logger.info(f"[{car_id}] all_calib_data.json 下载完成")

            return (car_id, ip, None)

        except Exception as e:
            return (car_id, ip, str(e))
        finally:
            await ssh.disconnect()


async def main():
    parser = argparse.ArgumentParser(description="批量导出AGV标定数据")
    parser.add_argument("--ip", help="测试单个IP（与 --car 配合使用）")
    parser.add_argument("--car", help="测试单个车号（与 --ip 配合使用）")
    args = parser.parse_args()

    # 命令行指定车号/IP 时，仅处理这一台
    if args.ip and args.car:
        devices = [(args.car, args.ip)]
    elif args.ip or args.car:
        logger.error("--ip 和 --car 必须同时指定")
        return
    else:
        devices = parse_csv(INPUT_CSV)

    logger.info(f"共 {len(devices)} 台设备待导出")
    logger.info(f"输出目录: {OUTPUT_DIR}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    sem = asyncio.Semaphore(MAX_CONCURRENT)
    tasks = [export_one_device(sem, car_id, ip) for car_id, ip in devices]

    results = []
    total = len(tasks)
    done = 0
    for coro in asyncio.as_completed(tasks):
        result = await coro
        results.append(result)
        done += 1
        car_id, ip, err = result
        if err:
            logger.warning(f"[{done}/{total}] {car_id} {ip} -> ERROR: {err}")
        else:
            logger.info(f"[{done}/{total}] {car_id} {ip} -> OK")

    # 统计
    ok = sum(1 for r in results if r[2] is None)
    fail = sum(1 for r in results if r[2] is not None)
    logger.info(f"完成: {ok} 成功, {fail} 失败")
    if fail:
        logger.info("失败列表:")
        for car_id, ip, err in results:
            if err:
                logger.info(f"  {car_id} {ip}: {err}")


if __name__ == "__main__":
    asyncio.run(main())
