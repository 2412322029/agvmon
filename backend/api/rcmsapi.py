import json
import multiprocessing
import os

import redis
import xmltodict
from fastapi import APIRouter, Request

# 配置multiprocessing使用spawn方式启动子进程，使子进程独立于父进程
try:
    multiprocessing.set_start_method("spawn")
except RuntimeError:
    pass  # 如果已经设置过则跳过

from util.config import cfg
from util.rcms_api import RcmsApi
from util.zeromq import Map_info_update

# 创建RcmsApi实例
rapi = RcmsApi()
r = redis.Redis(**cfg.get("redis"))


# 工具函数：获取Redis实例和rdstag
def get_redis_and_rdstag():
    """获取rdstag"""
    rdstag = cfg.get("rcms.host").split("://")[1].replace(":", "-")
    return rdstag


# 工具函数：检查进程是否存在
def is_process_running(pid):
    """检查进程是否正在运行"""
    try:
        os.kill(pid, 0)  # 检查进程是否存在而不发送信号
        return True
    except OSError:
        return False


# 全局变量用于跟踪ZeroMQ进程状态
zeromq_process_started = False
current_zeromq_process = None  # 保存当前的进程引用


# 全局函数，用于在子进程中启动Map_info_update
def start_map_update_process():
    from util.rcms_api import RcmsApi

    fresh_rapi = RcmsApi()
    fresh_rapi.build_from_cache()
    Map_info_update(fresh_rapi)


# 工具函数：获取程序信息
def get_program_info():
    """从Redis获取程序信息"""
    rdstag = get_redis_and_rdstag()
    program_info_key = f"{rdstag}:program_info"
    existing_info = r.get(program_info_key)

    if existing_info:
        try:
            info_data = json.loads(existing_info)
            existing_pid = info_data.get("pid")
            return r, program_info_key, info_data, existing_pid
        except json.JSONDecodeError:
            # 格式错误的信息应被删除
            r.delete(program_info_key)
            return r, program_info_key, None, None

    return r, program_info_key, None, None


# 工具函数：检查并清理僵尸进程信息
def check_and_clean_zombie_process():
    """检查并清理僵尸进程信息，返回进程是否正在运行"""
    r, program_info_key, info_data, existing_pid = get_program_info()

    if info_data and existing_pid:
        if is_process_running(existing_pid):
            return True, info_data, existing_pid, r, program_info_key
        else:
            # 进程不存在，僵尸进程信息已被清理
            r.delete(program_info_key)
            return False, None, None, r, program_info_key

    return False, None, None, r, program_info_key


# 全局函数来管理ZeroMQ进程
def ensure_zeromq_started():
    """确保ZeroMQ进程已启动"""
    global zeromq_process_started, current_zeromq_process

    # 检查当前是否有正在运行的进程引用
    if current_zeromq_process and current_zeromq_process.is_alive():
        return {
            "message": "ZeroMQ Map Update进程已存在",
            "pid": current_zeromq_process.pid,
            "info": {"pid": current_zeromq_process.pid},
        }

    # 启动新进程 - 使用spawn方式确保子进程独立
    process = multiprocessing.Process(
        target=start_map_update_process,
        args=(),
        daemon=True,  # 守护进程，主进程退出时子进程也会退出，但子进程不会影响主进程
    )

    # 启动进程
    process.start()
    current_zeromq_process = process
    zeromq_process_started = True
    # print(f"ZeroMQ Map Update进程已启动，PID: {process.pid}")
    return {"message": "ZeroMQ Map Update进程已启动", "pid": process.pid}


def ensure_zeromq_stopped():
    """确保ZeroMQ进程已停止"""
    global zeromq_process_started, current_zeromq_process

    # 检查当前进程引用
    if current_zeromq_process:
        if current_zeromq_process.is_alive():
            # 直接终止进程
            try:
                current_zeromq_process.terminate()  # 使用terminate方法而不是os.kill
                current_zeromq_process.join(timeout=5)  # 等待进程结束，最多等待5秒

                # 如果进程仍然存活，则强制终止
                if current_zeromq_process.is_alive():
                    current_zeromq_process.kill()  # 强制终止
                    current_zeromq_process.join()

                # 清理Redis中的程序信息
                rdstag = get_redis_and_rdstag()
                program_info_key = f"{rdstag}:program_info"
                _, _, _, pid = get_program_info()
                if pid:
                    os.kill(pid, 9)
                r.delete(program_info_key)

                zeromq_process_started = False
                current_zeromq_process = None

                return {
                    "message": "ZeroMQ Map Update进程已停止",
                    "pid": current_zeromq_process.pid
                    if current_zeromq_process
                    else None,
                }
            except Exception as e:
                # 进程可能已经不存在
                rdstag = get_redis_and_rdstag()
                program_info_key = f"{rdstag}:program_info"
                r.delete(program_info_key)
                current_zeromq_process = None
                zeromq_process_started = False
                return {
                    "message": f"进程停止时出现异常: {str(e)}",
                    "pid": current_zeromq_process.pid
                    if current_zeromq_process
                    else None,
                }
        else:
            # 进程已死亡，清理引用
            current_zeromq_process = None

    # 清理Redis中的程序信息
    rdstag = get_redis_and_rdstag()
    program_info_key = f"{rdstag}:program_info"
    _, _, _, pid = get_program_info()
    if pid:
        os.kill(pid, 9)
    r.delete(program_info_key)
    print("ZeroMQ Map Update进程已停止")
    zeromq_process_started = False
    return {"message": "未找到正在运行的ZeroMQ Map Update进程", "pid": None}


def check_and_manage_zeromq_process(has_active_websocket=False, timeout=False):
    """检查并管理ZeroMQ进程状态"""
    phas = False
    if r.exists(get_redis_and_rdstag() + ":program_info"):
        phas = True
    # 如果有WebSocket连接，确保ZeroMQ进程已启动
    if has_active_websocket:
        if phas:
            return {"message": "ZeroMQ进程已在运行"}
        else:
            print("检测到活跃的WebSocket连接，启动ZeroMQ进程")
            return ensure_zeromq_started()
    else:
        # 如果没有WebSocket连接，停止进程
        if phas and timeout:
            return ensure_zeromq_stopped()

    return {"message": "ZeroMQ进程状态正常"}


rcms_router = APIRouter(
    prefix="/rcms",
    tags=["rcms"],
)


@rcms_router.get("/build_from_cache")
def build_rcms_from_cache_api():
    try:
        retmsg = rapi.build_from_cache()
    except Exception as e:
        return {"message": "error", "errors": [str(e)]}
    if retmsg:
        return {"message": "error", "errors": retmsg}
    else:
        return {"message": "RCMS cache built successfully"}


@rcms_router.get("/build_from_raw")
def build_rcms_from_raw_api(request: Request):
    try:
        rapi.fake = request.query_params.get("fake", default=False) == "true"
        rapi.build_from_raw()
    except Exception as e:
        return {"message": "error", "errors": [str(e)]}
    retmsg = []
    for i in [
        rapi.rcsdata,
        rapi.maplist,
        rapi.devicelist,
        rapi.displaytype,
        rapi.alarmtype,
    ]:
        if not i:
            retmsg.append(f"数据为空: {i}")
    if retmsg:
        return {"message": "error", "errors": retmsg}
    else:
        return {"message": "RCMS raw data built successfully"}


# 获取共享地图数据
@rcms_router.get("/sharemapdata")
def get_sharemapdata_api():
    if isinstance(rapi.sharemapdata, str):
        return xmltodict.parse(rapi.sharemapdata)
    return rapi.sharemapdata


@rcms_router.get("/maplist")
def get_maplist_api():
    return rapi.maplist


@rcms_router.post("/start_zeromq_map_update")
def start_zeromq_map_update(map_index: int = 0, interval: float = 0.01):
    """启动ZeroMQ Map Info Update进程"""
    return ensure_zeromq_started()


@rcms_router.post("/stop_zeromq_map_update")
def stop_zeromq_map_update(map_index: int = 0):
    """停止ZeroMQ Map Info Update进程"""
    return ensure_zeromq_stopped()


@rcms_router.get("/zeromq_program_info")
def get_zeromq_program_info():
    """获取ZeroMQ程序信息"""
    _, _, info_data, _ = get_program_info()

    if info_data:
        return {"message": "程序信息获取成功", "info": info_data}
    else:
        return {"message": "未找到程序信息", "info": None}
