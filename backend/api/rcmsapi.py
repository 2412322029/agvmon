import json
import multiprocessing
import os

import xmltodict
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from util.config import r

# 导入异常日志数据库
from .exception_log import ExceptionLogDB

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
    Map_info_update(fresh_rapi, show_count=False)


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
            if cfg.get("zmq_auto"):
                print("检测到活跃的WebSocket连接，启动ZeroMQ进程")
                return ensure_zeromq_started()
            else:
                return {"message": "ZeroMQ自动启停管理已禁用"}
    else:
        # 如果没有WebSocket连接，停止进程
        if phas and timeout:
            return ensure_zeromq_stopped()

    return {"message": "ZeroMQ进程状态正常"}


rcms_router = APIRouter(
    prefix="/rcms",
    tags=["rcms"],
)


@rcms_router.get("/remove_agv_status")
def remove_agv_status(robot_id: str):
    num_deleted = r.hdel(get_redis_and_rdstag() + ":ROBOT_STATUS", robot_id)
    return {"message": f"AGV状态已删除，共删除 {num_deleted} 条记录"}   


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


# 创建异常日志数据库实例
exception_db = ExceptionLogDB()


# Pydantic模型定义
class ExceptionLogCreate(BaseModel):
    agv_id: str = Field(..., description="小车ID")
    problem_description: str = Field(..., description="问题描述")
    agv_status: str = Field(None, description="小车状态")
    remarks: str = Field(None, description="备注")


class ExceptionLogUpdate(BaseModel):
    agv_id: str = Field(None, description="小车ID")
    problem_description: str = Field(None, description="问题描述")
    agv_status: str = Field(None, description="小车状态")
    remarks: str = Field(None, description="备注")


class ExceptionLogQuery(BaseModel):
    id: int = Field(None, description="日志ID")
    agv_id: str = Field(None, description="小车ID")
    keyword: str = Field(None, description="关键词搜索")
    start_date: str = Field(None, description="开始日期")
    end_date: str = Field(None, description="结束日期")
    agv_status: str = Field(None, description="小车状态")
    page: int = Field(None, description="页码")
    page_size: int = Field(None, description="每页大小")


# 异常日志相关API接口
@rcms_router.get("/exception_logs/{log_id}")
def get_exception_log(log_id: int):
    """根据ID获取单条异常日志"""
    try:
        log = exception_db.get_exception_log(log_id)
        if log:
            return {"message": "success", "data": log}
        else:
            return {"message": "error", "errors": ["Log not found"]}
    except Exception as e:
        return {"message": "error", "errors": [str(e)]}


@rcms_router.post("/add_exception_logs")
def add_exception_log(log_data: ExceptionLogCreate):
    """添加异常日志"""
    try:
        # 确保必需字段非空
        agv_id = log_data.agv_id if log_data.agv_id else ""
        problem_description = (
            log_data.problem_description
            if log_data.problem_description
            else "无问题描述"
        )

        log_id = exception_db.add_exception_log(
            agv_id, problem_description, log_data.agv_status, log_data.remarks
        )
        return {"message": "success", "data": {"id": log_id}}
    except Exception as e:
        return {"message": "error", "errors": [str(e)]}


@rcms_router.put("/exception_logs/{log_id}")
def update_exception_log(log_id: int, log_data: ExceptionLogUpdate):
    """更新异常日志"""
    try:
        success = exception_db.update_exception_log(
            log_id,
            log_data.agv_id,
            log_data.problem_description,
            log_data.agv_status,
            log_data.remarks,
        )
        if success:
            return {"message": "success", "data": {"updated": True}}
        else:
            return {"message": "error", "errors": ["Log not found or update failed"]}
    except Exception as e:
        return {"message": "error", "errors": [str(e)]}


@rcms_router.delete("/exception_logs/{log_id}")
def delete_exception_log(log_id: int):
    """删除异常日志"""
    try:
        success = exception_db.delete_exception_log(log_id)
        if success:
            return {"message": "success", "data": {"deleted": True}}
        else:
            return {"message": "error", "errors": ["Log not found or deletion failed"]}
    except Exception as e:
        return {"message": "error", "errors": [str(e)]}


@rcms_router.delete("/exception_logs/agv/{agv_id}")
def delete_exception_logs_by_agv(agv_id: str):
    """删除指定小车的所有异常日志"""
    try:
        deleted_count = exception_db.delete_exception_logs_by_agv(agv_id)
        return {"message": "success", "data": {"deleted_count": deleted_count}}
    except Exception as e:
        return {"message": "error", "errors": [str(e)]}


@rcms_router.get("/exception_logs")
def query_exception_logs_get(
    id: int = None,
    agv_id: str = None,
    keyword: str = None,
    start_date: str = None,
    end_date: str = None,
    agv_status: str = None,
    page: int = None,
    page_size: int = None,
):
    """统一查询异常日志（传统查询方式，兼容原有接口）"""
    try:
        # 如果指定了具体的ID，则获取单条记录
        if id is not None:
            log = exception_db.get_exception_log(id)
            if log:
                return {
                    "message": "success",
                    "data": {
                        "data": [log],
                        "total_count": 1,
                        "page": 1,
                        "page_size": 1,
                        "total_pages": 1,
                    },
                }
            else:
                return {"message": "error", "errors": ["Log not found"]}
        else:
            # 使用统一查询接口
            logs = exception_db.query_exception_logs(
                agv_id=agv_id,
                keyword=keyword,
                start_date=start_date,
                end_date=end_date,
                agv_status=agv_status,
                page=page,
                page_size=page_size,
            )
            return {"message": "success", "data": logs}
    except Exception as e:
        return {"message": "error", "errors": [str(e)]}


@rcms_router.post("/exception_logs/query")
def query_exception_logs_post(log_data: ExceptionLogQuery):
    """统一查询异常日志（使用请求体传递参数）"""
    try:
        # 如果指定了具体的ID，则获取单条记录
        if log_data.id is not None:
            log = exception_db.get_exception_log(log_data.id)
            if log:
                return {
                    "message": "success",
                    "data": {
                        "data": [log],
                        "total_count": 1,
                        "page": 1,
                        "page_size": 1,
                        "total_pages": 1,
                    },
                }
            else:
                return {"message": "error", "errors": ["Log not found"]}
        else:
            # 使用统一查询接口，处理可能的空值情况
            logs = exception_db.query_exception_logs(
                agv_id=log_data.agv_id if log_data.agv_id else None,
                keyword=log_data.keyword if log_data.keyword else None,
                start_date=log_data.start_date if log_data.start_date else None,
                end_date=log_data.end_date if log_data.end_date else None,
                agv_status=log_data.agv_status if log_data.agv_status else None,
                page=log_data.page if log_data.page else 1,
                page_size=log_data.page_size if log_data.page_size else 10,
            )
            return {"message": "success", "data": logs}
    except Exception as e:
        return {"message": "error", "errors": [str(e)]}
