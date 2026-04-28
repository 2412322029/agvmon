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
    build_subparsers = build_parser.add_subparsers(dest="build_command", help="构建子命令")

    # build raw
    build_raw_parser = build_subparsers.add_parser("raw", help="从原始数据构建模型并创建缓存")

    # build cache
    build_cache_parser = build_subparsers.add_parser("cache", help="从缓存构建模型")

    # build genmap
    build_genmap_parser = build_subparsers.add_parser("genmap", help="从模型生成地图图片")
    # build saveport
    build_saveport_parser = build_subparsers.add_parser("saveport", help="保存bufferPort和machinePort到缓存")

    # build transport
    build_transport_parser = build_subparsers.add_parser("transport", help="从缓存中读取bufferPort和machinePort并转换")

    # ===== run 子命令组 =====
    run_parser = subparsers.add_parser("run", help="运行服务相关操作")
    run_subparsers = run_parser.add_subparsers(dest="run_command", help="运行子命令")

    # run zeromq
    run_zeromq_parser = run_subparsers.add_parser("zeromq", help="运行ZeroMQ更新以刷新Redis地图信息")
    run_zeromq_parser.add_argument(
        "-i", "--interval", type=float, default=None, help="更新间隔时间（秒）"
    )

    # run rabbitmq
    run_rabbitmq_parser = run_subparsers.add_parser("rabbitmq", help="运行RabbitMQ更新服务器")

    # run web
    run_web_parser = run_subparsers.add_parser("web", help="运行FastAPI WebSocket服务器")

    # ===== tools 子命令组 =====
    tools_parser = subparsers.add_parser("tools", help="工具相关操作")
    tools_subparsers = tools_parser.add_subparsers(dest="tools_command", help="工具子命令")


    # tools show-robot
    tools_show_robot_parser = tools_subparsers.add_parser("show-robot", help="显示机器人状态")
    tools_show_robot_parser.add_argument(
        "-i", "--interval", type=float, default=None, help="更新间隔时间（秒）"
    )

    # tools rk (remove key)
    tools_rk_parser = tools_subparsers.add_parser("rk", help="remove key")

    # tools agvlog
    tools_agvlog_parser = tools_subparsers.add_parser("agvlog", help="下载并分析AGV日志")
    tools_agvlog_parser.add_argument("ip_or_carid", metavar="IP_OR_CARID", help="AGV IP地址或carid")
    tools_agvlog_parser.add_argument("--pio", action="store_true", help="解析pio日志")
    tools_agvlog_parser.add_argument("--count", type=int, default=1, help="下载最新的文件数量（默认1）,指定后files参数无效")
    tools_agvlog_parser.add_argument("--files", nargs="+", help="指定要下载的文件名列表，指定后count参数无效")

    args = parser.parse_args()

    if args.test:
        cfg.set("test", True)
        print(f"测试模式: {cfg.get('test')}")

    # 导入所需模块
    if args.command == "build" or args.command == "run":
        from util.rcms_api import RcmsApi
        from util.rcs_web_api import RcsWebApi
        rapi = RcmsApi()
        rcs_api = RcsWebApi()

    if args.command == "run" and args.run_command == "zeromq":
        from util.showrobot import show_robot_status
        from util.zeromq import Map_info_update, removekey

    if args.command == "run" and args.run_command == "rabbitmq":
        from util.rabbitmq import run_rabbitmq_server

    if args.command == "run" and args.run_command == "web":
        from backend.app import run_api_server

    # 执行请求的操作
    if args.command == "build":
        if args.build_command == "raw":
            rapi.build_from_raw()
        elif args.build_command == "cache":
            retmsg = rapi.build_from_cache()
            if retmsg:
                logger.error(f"构建模型缓存失败: {retmsg}")
            else:
                logger.info("从缓存构建模型成功")
        elif args.build_command == "genmap":
            rapi.build_from_cache()
            rapi.genmapimage()
        else:
            build_parser.print_help()

    elif args.command == "run":
        if args.run_command == "zeromq":
            rapi.build_from_cache()
            if args.interval is not None:
                Map_info_update(rapi, interval=args.interval)
            else:
                Map_info_update(rapi)
        elif args.run_command == "rabbitmq":
            rapi.build_from_cache()
            run_rabbitmq_server(rapi)
        elif args.run_command == "web":
            run_api_server()
        else:
            run_parser.print_help()

    elif args.command == "tools":
        if args.tools_command == "saveport":
            import asyncio

            from util.rcs_web_api import RcsWebApi
            rcs_api = RcsWebApi()

            async def inner():
                async with rcs_api:
                    await rcs_api.saveallport()

            asyncio.run(inner())

        elif args.tools_command == "transport":
            from util.rcs_web_api import RcsWebApi
            rcs_api = RcsWebApi()
            rcs_api.transport()

        elif args.tools_command == "show-robot":
            from util.showrobot import show_robot_status
            if args.interval is not None:
                show_robot_status(args.interval)
            else:
                show_robot_status()

        elif args.tools_command == "rk":
            from util.zeromq import removekey
            removekey()

        elif args.tools_command == "agvlog":
            import asyncio

            from util.agvlog import (
                download_agv_logs,
                get_pio_result,
                getip_from_carid,
                print_merged_info,
            )
            if args.pio:
                input_val = args.ip_or_carid
                if args.files:
                    files = asyncio.run(download_agv_logs(input_val, filenames=args.files))
                else:
                    files = asyncio.run(download_agv_logs(input_val, new_count=args.count))
                merged_logs = get_pio_result(files)
                print_merged_info(merged_logs)
            else:
                print("请指定--pio选项等操作 明确要解析的类型")
        else:
            tools_parser.print_help()

    else:
        parser.print_help()
        print("3秒后启动FastAPI服务器")
        time.sleep(3)
        from backend.app import run_api_server
        run_api_server()


if __name__ == "__main__":
    main()