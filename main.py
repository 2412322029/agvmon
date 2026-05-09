import argparse
import time

from util.config import cfg
from util.logger import logger

logger.setLevel("INFO")


def main():
    parser = argparse.ArgumentParser(description="AGV监控系统命令行界面")
    parser.add_argument("--test", action="store_true", help="测试模式")

    # 创建子命令解析器
    subparsers = parser.add_subparsers(dest="command", help="可用子命令")

    # ===== build 子命令组 =====
    build_parser = subparsers.add_parser("build", help="模型构建相关操作")
    build_subparsers = build_parser.add_subparsers(
        dest="build_command", help="构建子命令"
    )

    # build raw
    build_subparsers.add_parser("raw", help="从原始数据构建模型并创建缓存")

    # build cache
    build_subparsers.add_parser("cache", help="从缓存构建模型")

    # build genmap
    build_subparsers.add_parser("genmap", help="从模型生成地图图片")
    # build saveport
    build_subparsers.add_parser("saveport", help="保存bufferPort和machinePort到缓存")

    # build transport
    build_subparsers.add_parser(
        "transport", help="从缓存中读取bufferPort和machinePort并转换"
    )

    # ===== run 子命令组 =====
    run_parser = subparsers.add_parser("run", help="运行服务相关操作")
    run_subparsers = run_parser.add_subparsers(dest="run_command", help="运行子命令")

    # run zeromq
    run_zeromq_parser = run_subparsers.add_parser(
        "zeromq", help="运行ZeroMQ更新以刷新Redis地图信息"
    )
    run_zeromq_parser.add_argument(
        "-i", "--interval", type=float, default=None, help="更新间隔时间（秒）"
    )

    # run rabbitmq
    run_subparsers.add_parser("rabbitmq", help="运行RabbitMQ更新服务器")

    # run web
    run_subparsers.add_parser("web", help="运行FastAPI WebSocket服务器")

    # ===== tools 子命令组 =====
    tools_parser = subparsers.add_parser("tools", help="工具相关操作")
    tools_subparsers = tools_parser.add_subparsers(
        dest="tools_command", help="工具子命令"
    )

    # tools show-robot
    tools_show_robot_parser = tools_subparsers.add_parser(
        "show-robot", help="显示机器人状态"
    )
    tools_show_robot_parser.add_argument(
        "-i", "--interval", type=float, default=None, help="更新间隔时间（秒）"
    )

    # tools rk (remove key)
    tools_subparsers.add_parser("rk", help="remove key")

    # tools clean
    tools_clean_parser = tools_subparsers.add_parser(
        "clean", help="清理日志文件"
    )
    tools_clean_subparsers = tools_clean_parser.add_subparsers(
        dest="clean_target", help="清理目标"
    )
    tools_clean_subparsers.add_parser("wcslog", help="清理WCS日志文件")
    tools_clean_subparsers.add_parser("agvlog", help="清理AGV日志文件")

    # tools wcslog
    tools_wcslog_parser = tools_subparsers.add_parser("wcslog", help="解析WCS日志文件")
    tools_wcslog_parser.add_argument(
        "files",
        nargs="*",
        default=None,
        help="要解析的日志文件路径，不指定则扫描 ./data/wcslog/",
    )
    tools_wcslog_parser.add_argument(
        "-c",
        "--code",
        default=None,
        help="探测器短码过滤，如 528000 或 5280xx (xx=通配符)",
    )

    # tools agvlog
    tools_agvlog_parser = tools_subparsers.add_parser(
        "agvlog", help="下载并分析AGV日志"
    )
    tools_agvlog_parser.add_argument(
        "ip_or_carid", metavar="IP_OR_CARID", help="AGV IP地址或carid"
    )
    tools_agvlog_parser.add_argument(
        "--pio",
        action="store",
        help="解析pio日志，可选值: print(直接打印), browse(分页浏览)",
    )
    tools_agvlog_parser.add_argument(
        "--download",
        action="store",
        help="下载文件，后面指定要下载的文件路径，--files 指定文件名",
    )
    tools_agvlog_parser.add_argument(
        "--ls",
        action="store",
        help="列出目录，后面指定路径",
    )
    tools_agvlog_parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="下载最新的文件数量（默认1）,指定后files参数无效",
    )
    tools_agvlog_parser.add_argument(
        "--files", nargs="+", help="指定要下载的文件名列表，指定后count参数无效"
    )

    args = parser.parse_args()

    if args.test:
        cfg.set("test", True)
        print(f"测试模式: {cfg.get('test')}")

    subcmd = {
        "build": getattr(args, "build_command", None),
        "run": getattr(args, "run_command", None),
        "tools": getattr(args, "tools_command", None),
    }.get(args.command)

    match (args.command, subcmd):
        # -- build raw --
        case ("build", "raw"):
            from util.rcms_api import RcmsApi

            RcmsApi().build_from_raw()

        # -- build cache --
        case ("build", "cache"):
            from util.rcms_api import RcmsApi

            rapi = RcmsApi()
            retmsg = rapi.build_from_cache()
            if retmsg:
                logger.error(f"构建模型缓存失败: {retmsg}")
            else:
                logger.info("从缓存构建模型成功")

        # -- build genmap --
        case ("build", "genmap"):
            from util.rcms_api import RcmsApi

            rapi = RcmsApi()
            rapi.build_from_cache()
            rapi.genmapimage()

        # -- build saveport --
        case ("build", "saveport"):
            import asyncio

            from util.rcs_web_api import RcsWebApi

            async def _saveport():
                async with RcsWebApi() as rcs_api:
                    await rcs_api.saveallport()

            asyncio.run(_saveport())

        # -- build transport --
        case ("build", "transport"):
            from util.rcs_web_api import RcsWebApi

            RcsWebApi().transport()

        # -- run zeromq --
        case ("run", "zeromq"):
            from util.rcms_api import RcmsApi
            from util.zeromq import Map_info_update

            rapi = RcmsApi()
            rapi.build_from_cache()
            if args.interval is not None:
                Map_info_update(rapi, interval=args.interval)
            else:
                Map_info_update(rapi)

        # -- run rabbitmq --
        case ("run", "rabbitmq"):
            from util.rabbitmq import run_rabbitmq_server
            from util.rcms_api import RcmsApi

            rapi = RcmsApi()
            rapi.build_from_cache()
            run_rabbitmq_server(rapi)

        # -- run web --
        case ("run", "web"):
            from backend.app import run_api_server

            run_api_server()

        # -- tools show-robot --
        case ("tools", "show-robot"):
            from util.showrobot import show_robot_status

            if args.interval is not None:
                show_robot_status(args.interval)
            else:
                show_robot_status()

        # -- tools rk --
        case ("tools", "rk"):
            from util.zeromq import removekey

            removekey()

        # -- tools clean --
        case ("tools", "clean"):
            import os
            from util.clean import interactive_clean

            target = getattr(args, "clean_target", None)
            base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "util", "data")
            dirs = {
                "wcslog": os.path.join(base, "wcslog"),
                "agvlog": os.path.join(base, "agvlog"),
            }
            if target in dirs:
                interactive_clean(dirs[target], label=target)
            else:
                print(f"Unknown clean target: {target}")
                print("  Available: wcslog, agvlog")

        # -- tools wcslog --
        case ("tools", "wcslog"):
            from util.parse_wcs_log import run
            run(args.files, args.code)

        # -- tools agvlog --
        case ("tools", "agvlog"):
            import asyncio

            from util.agvlog import (
                browse_merged_info,
                download_agv_logs,
                get_pio_result,
                lsagv,
                print_merged_info,
            )

            if args.pio:
                input_val = args.ip_or_carid
                if args.files:
                    files = asyncio.run(
                        download_agv_logs(input_val, filenames=args.files)
                    )
                else:
                    files = asyncio.run(
                        download_agv_logs(input_val, new_count=args.count)
                    )
                merged_logs = get_pio_result(files)
                if args.pio.startswith("b"):
                    browse_merged_info(merged_logs)
                elif args.pio.startswith("p"):
                    print_merged_info(merged_logs)
            elif args.download:
                if args.files:
                    asyncio.run(
                        download_agv_logs(
                            args.ip_or_carid,
                            filenames=args.files,
                            prefix=args.download,
                            is_agvlog=False,
                        )
                    )
                elif args.count:
                    asyncio.run(
                        download_agv_logs(
                            args.ip_or_carid,
                            new_count=int(args.count),
                            prefix=args.download,
                            is_agvlog=False,
                        )
                    )
            elif args.ls:
                asyncio.run(lsagv(ip_or_carid=args.ip_or_carid, path=args.ls))
            else:
                print("请指定--pio选项等操作 明确要解析的类型")

        # -- unknown subcommand: print group help --
        case ("build", _):
            build_parser.print_help()
        case ("run", _):
            run_parser.print_help()
        case ("tools", _):
            tools_parser.print_help()

        # -- unknown command: start default server --
        case _:
            parser.print_help()
            print("3秒后启动FastAPI服务器")
            time.sleep(3)
            from backend.app import run_api_server

            run_api_server()


if __name__ == "__main__":
    main()
