import argparse
import sys
import time

# --- 用户 Lua 脚本 worker 快速通道 -------------------------------------
# 必须在导入 util.core.config / util.core.logger 之前分流：这两个模块会拉起 redis 与
# loguru（实测约 200ms 冷启动），而脚本本身通常只跑几毫秒、worker 每次执行都
# 要重启一次进程，这笔开销必须省掉。
# 该子命令不注册进 argparse（内部命令，不出现在 help 里）；若 argv 形态意外
# 不符，argparse 会以 "invalid choice" 报错退出，宿主侧会把 stderr 带回来，
# 因此失败也是可诊断的，而不是静默无输出。
if __name__ == "__main__" and "lua-worker" in sys.argv[1:3]:
    from util.lua.lua_worker import main as _lua_worker_main

    sys.exit(_lua_worker_main())

from util.core.config import cfg
from util.core.logger import logger

#logger.setLevel("INFO")


def main():
    from util.core.__version__ import version, build_time, git_hash

    parser = argparse.ArgumentParser(
        description="AGV监控系统命令行界面",
        epilog=f"AGVmon v{version}  build: {build_time}  git: {git_hash}",
    )
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
    tools_wcslog_parser = tools_subparsers.add_parser("wcslog", help="WCS日志管理")
    tools_wcslog_subparsers = tools_wcslog_parser.add_subparsers(
        dest="wcslog_command", help="WCS子命令"
    )

    # tools wcslog list
    tools_wcslog_subparsers.add_parser("list", help="列出远程WCS default.log文件")

    # tools wcslog download
    wcslog_dl_parser = tools_wcslog_subparsers.add_parser(
        "download", help="列出远程文件并选择下载"
    )
    wcslog_dl_parser.add_argument(
        "-a", "--all", action="store_true", help="下载所有default.log文件（跳过交互选择）"
    )

    # tools wcslog parse
    wcslog_parse_parser = tools_wcslog_subparsers.add_parser(
        "parse", help="解析本地WCS日志文件"
    )
    wcslog_parse_parser.add_argument(
        "files",
        nargs="*",
        default=None,
        help="要解析的日志文件路径，不指定则扫描 ./data/wcslog/",
    )
    wcslog_parse_parser.add_argument(
        "-c",
        "--code",
        default=None,
        help="设备外设编号过滤，如 528000 或 5280xx (xx=通配符)",
    )
    wcslog_parse_parser.add_argument(
        "--taskid",
        default=None,
        help="任务ID过滤，如 324FA059DD00_WCS",
    )
    wcslog_parse_parser.add_argument(
        "--device-type",
        default="Detector",
        help="设备类型过滤，默认 Detector",
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

    # ===== env 子命令组 =====
    env_parser = subparsers.add_parser(
        "env", help="环境变量相关操作（Windows 用户 PATH）"
    )
    env_subparsers = env_parser.add_subparsers(dest="env_command", help="env子命令")

    # env add
    env_subparsers.add_parser("add", help="把 agvmon.exe 所在目录加入用户 PATH")
    # env remove
    env_subparsers.add_parser("remove", help="把 agvmon.exe 所在目录从用户 PATH 移除")
    # env show
    env_subparsers.add_parser("show", help="查看 agvmon.exe 目录与当前用户 PATH")

    # ===== autostart 子命令组 =====
    autostart_parser = subparsers.add_parser(
        "autostart", help="开机自启相关操作（shell:startup）"
    )
    autostart_subparsers = autostart_parser.add_subparsers(
        dest="autostart_command", help="autostart子命令"
    )

    # autostart add
    autostart_subparsers.add_parser(
        "add", help="把 start_agvmon.ps1 写入启动目录（依赖 agvmon env add）"
    )
    # autostart remove
    autostart_subparsers.add_parser("remove", help="从启动目录移除自启脚本")
    # autostart show
    autostart_subparsers.add_parser("show", help="查看自启状态与脚本内容")

    args = parser.parse_args()

    if args.test:
        cfg.set("test", True)
        print(f"测试模式: {cfg.get('test')}")

    subcmd = {
        "build": getattr(args, "build_command", None),
        "run": getattr(args, "run_command", None),
        "tools": getattr(args, "tools_command", None),
        "env": getattr(args, "env_command", None),
        "autostart": getattr(args, "autostart_command", None),
    }.get(args.command)

    match (args.command, subcmd):
        # -- build raw --
        case ("build", "raw"):
            from util.net.rcms_api import RcmsApi

            RcmsApi().build_from_raw()

        # -- build cache --
        case ("build", "cache"):
            from util.net.rcms_api import RcmsApi

            rapi = RcmsApi()
            retmsg = rapi.build_from_cache()
            if retmsg:
                logger.error(f"构建模型缓存失败: {retmsg}")
            else:
                logger.info("从缓存构建模型成功")

        # -- build genmap --
        case ("build", "genmap"):
            from util.net.rcms_api import RcmsApi

            rapi = RcmsApi()
            rapi.build_from_cache()
            rapi.genmapimage()

        # -- build saveport --
        case ("build", "saveport"):
            import asyncio

            from util.net.rcs_web_api import RcsWebApi

            async def _saveport():
                async with RcsWebApi() as rcs_api:
                    await rcs_api.saveallport()

            asyncio.run(_saveport())

        # -- build transport --
        case ("build", "transport"):
            from util.net.rcs_web_api import RcsWebApi

            RcsWebApi().transport()

        # -- run zeromq --
        case ("run", "zeromq"):
            from util.net.rcms_api import RcmsApi
            from util.net.zeromq import Map_info_update

            rapi = RcmsApi()
            rapi.build_from_cache()
            if args.interval is not None:
                Map_info_update(rapi, interval=args.interval)
            else:
                Map_info_update(rapi)

        # -- run rabbitmq --
        case ("run", "rabbitmq"):
            from util.net.rabbitmq import run_rabbitmq_server
            from util.net.rcms_api import RcmsApi

            rapi = RcmsApi()
            rapi.build_from_cache()
            run_rabbitmq_server(rapi)

        # -- run web --
        case ("run", "web"):
            from backend.app import run_api_server

            run_api_server()

        # -- tools show-robot --
        case ("tools", "show-robot"):
            from util.net.showrobot import show_robot_status

            if args.interval is not None:
                show_robot_status(args.interval)
            else:
                show_robot_status()

        # -- tools rk --
        case ("tools", "rk"):
            from util.net.zeromq import removekey

            removekey()

        # -- tools clean --
        case ("tools", "clean"):
            import os
            from util.logs.clean import interactive_clean

            target = getattr(args, "clean_target", None)
            base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "util", "data")
            dirs = {
                "wcslog": os.path.join(base, "wcslog"),
                "agvlog": os.path.join(base, "agvlog"),
            }
            if target in dirs:
                interactive_clean(dirs[target], label=target)
            elif target is None:
                print("Available: wcslog, agvlog")
                choice = input("Which to clean? [wcslog/agvlog/q]: ").strip().lower()
                if choice == "q":
                    print("Cancelled.")
                elif choice in dirs:
                    interactive_clean(dirs[choice], label=choice)
                else:
                    print(f"Unknown: {choice}")
            else:
                print(f"Unknown clean target: {target}")
                print("  Available: wcslog, agvlog")

        # -- tools wcslog --
        case ("tools", "wcslog"):
            wcslog_cmd = getattr(args, "wcslog_command", None)
            if wcslog_cmd == "list":
                import asyncio
                from util.logs.parse_wcs_log import list_wcs_logs

                async def _list():
                    files = await list_wcs_logs()
                    if not files:
                        print("未找到 default.log 文件")
                        return
                    print(f"{'#':<4} {'文件名':<25} {'时间':<20} {'大小':>8}")
                    print("-" * 60)
                    for i, f in enumerate(files, 1):
                        print(f"{i:<4} {f['filename']:<25} {f['time'].strftime('%Y-%m-%d %H:%M:%S'):<20}")
                asyncio.run(_list())

            elif wcslog_cmd == "download":
                import asyncio
                from util.logs.parse_wcs_log import download_wcs_log, list_wcs_logs

                async def _download():
                    files = await list_wcs_logs()
                    if not files:
                        print("未找到 default.log 文件")
                        return

                    if args.all:
                        selected = files
                    else:
                        print(f"{'#':<4} {'文件名':<25} {'时间':<20}")
                        print("-" * 50)
                        for i, f in enumerate(files, 1):
                            print(f"{i:<4} {f['filename']:<25} {f['time'].strftime('%Y-%m-%d %H:%M:%S'):<20}")
                        print("-" * 50)
                        raw = input("输入序号下载（多个用空格/逗号分隔，回车=全部）: ").strip()
                        if not raw:
                            selected = files
                        else:
                            idxs = set()
                            for part in raw.replace(",", " ").split():
                                try:
                                    idxs.add(int(part) - 1)
                                except ValueError:
                                    print(f"无效序号: {part}，跳过")
                            selected = [files[i] for i in sorted(idxs) if 0 <= i < len(files)]

                    if not selected:
                        print("未选择任何文件")
                        return

                    def _progress(downloaded, total):
                        pct = downloaded / total * 100
                        bar_len = 30
                        filled = int(bar_len * downloaded / total)
                        bar = "█" * filled + "░" * (bar_len - filled)
                        print(f"\r  {bar} {pct:.1f}% ({_fmt(downloaded)}/{_fmt(total)})", end="", flush=True)

                    def _fmt(size):
                        for u in ["B", "KB", "MB", "GB"]:
                            if size < 1024:
                                return f"{size:.2f} {u}"
                            size /= 1024
                        return f"{size:.2f} TB"

                    for f in selected:
                        print(f"\n下载: {f['filename']}")
                        dest = await download_wcs_log(f["filename"], progress_cb=_progress)
                        print(f"\n  -> {dest}")

                asyncio.run(_download())

            else:  # parse (默认)
                from util.logs.parse_wcs_log import run
                run(args.files if hasattr(args, 'files') else None,
                    args.code if hasattr(args, 'code') else None,
                    taskid=getattr(args, 'taskid', None),
                    device_type=getattr(args, 'device_type', None))

        # -- tools agvlog --
        case ("tools", "agvlog"):
            import asyncio

            from util.logs.agvlog import (
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

        # -- env add / remove / show --
        case ("env", "add"):
            from util.core.envpath import add as env_add

            try:
                print(env_add())
            except RuntimeError as e:
                print(f"错误: {e}")

        case ("env", "remove"):
            from util.core.envpath import remove as env_remove

            try:
                print(env_remove())
            except RuntimeError as e:
                print(f"错误: {e}")

        case ("env", "show"):
            from util.core.envpath import show as env_show

            try:
                print(env_show())
            except RuntimeError as e:
                print(f"错误: {e}")

        # -- autostart add / remove / show --
        case ("autostart", "add"):
            from util.core.autostart import add as autostart_add
            from util.core.envpath import add as env_add

            try:
                print(env_add())
                print(autostart_add())
            except RuntimeError as e:
                print(f"错误: {e}")

        case ("autostart", "remove"):
            from util.core.autostart import remove as autostart_remove

            try:
                print(autostart_remove())
            except RuntimeError as e:
                print(f"错误: {e}")

        case ("autostart", "show"):
            from util.core.autostart import show as autostart_show

            try:
                print(autostart_show())
            except RuntimeError as e:
                print(f"错误: {e}")

        # -- unknown subcommand: print group help --
        case ("build", _):
            build_parser.print_help()
        case ("run", _):
            run_parser.print_help()
        case ("tools", _):
            tools_parser.print_help()
        case ("env", _):
            env_parser.print_help()
        case ("autostart", _):
            autostart_parser.print_help()

        # -- unknown command: start default server --
        case _:
            parser.print_help()
            print("3秒后启动FastAPI服务器")
            time.sleep(3)
            from backend.app import run_api_server

            run_api_server()


if __name__ == "__main__":
    main()
