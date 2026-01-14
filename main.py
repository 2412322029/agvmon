import argparse

from util.logger import logger
from util.rabbitmq import run_rabbitmq_server
from util.rcms_api import RcmsApi
from util.showrobot import show_robot_status
from util.zeromq import Map_info_update

logger.setLevel('INFO')
def main():
    parser = argparse.ArgumentParser(description='AGV监控系统命令行界面')
    
    # 添加互斥组用于主要操作
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--zeromq', action='store_true', help='运行ZeroMQ更新以刷新Redis地图信息')
    group.add_argument('--rabbitmq', action='store_true', help='运行RabbitMQ更新服务器')
    
    # 添加单个操作选项
    parser.add_argument('--build-raw', action='store_true', help='从原始数据构建模型并创建缓存')
    parser.add_argument('--build-cache', action='store_true', help='从缓存构建模型')
    parser.add_argument('--genmap', action='store_true', help='从模型生成地图图片')
    parser.add_argument('--show-robot', action='store_true', help='显示机器人状态')
    
    # 添加interval选项
    parser.add_argument("-i",'--interval', type=float, default=None, help='更新间隔时间（秒），适用于--zeromq和--show-robot选项')
    
    args = parser.parse_args()
    
    # 创建RcmsApi实例
    rapi = RcmsApi()
    
    # 执行请求的操作
    if args.build_raw:
        rapi.build_from_raw()
    elif args.build_cache:
        rapi.build_from_cache()
    elif args.genmap:
        rapi.build_from_cache()  # 生成地图前需要构建模型
        rapi.genmapimage()
    elif args.zeromq:
        rapi.build_from_cache()
        if args.interval is not None:
            Map_info_update(rapi, interval=args.interval)
        else:
            Map_info_update(rapi)
    elif args.rabbitmq:
        rapi.build_from_cache()
        run_rabbitmq_server(rapi)
    elif args.show_robot:
        if args.interval is not None:
            show_robot_status(args.interval)
        else:
            show_robot_status()
    else:
        parser.print_help()

if __name__ == '__main__':
    main()


