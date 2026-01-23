from fastapi import APIRouter, Body

from util.config import cfg
from util.rcs_web_api import RcsWebApi

rcs_web_router = APIRouter(
    prefix="/rcs_web",
    tags=["rcs_web"],
)

# 创建RcsWebApi实例
rcs_api = RcsWebApi()


@rcs_web_router.post("/find_tasks_detail")
def find_tasks_detail_api(
    robotCode: str = Body("", description="机器人代码"),
    taskTyp: str = Body("", description="任务类型"),
    taskStatus: int = Body(2, description="任务状态"),
    carrierId: str = Body("", description="载体ID"),
    podCode: str = Body("", description="Pod代码"),
    ctnrCode: str = Body("", description="容器代码"),
    tranTaskNum: str = Body("", description="任务号"),
    wbCode: str = Body("", description="工作站代码"),
    uname: str = Body("", description="用户名"),
    dstMapCode: str = Body("", description="目标地图代码"),
    groupNum: str = Body("", description="组号"),
    liftCode: str = Body("", description="电梯代码"),
    srcEqName: str = Body("", description="源设备名称"),
    desEqName: str = Body("", description="目标设备名称"),
    sdateTo: str = Body(None, description="开始时间"),
    edateTo: str = Body(None, description="结束时间"),
    limit: int = Body(20, description="每页数量"),
):
    try:
        result = rcs_api.find_tasks_detail(
            robotCode=robotCode,
            taskTyp=taskTyp,
            taskStatus=taskStatus,
            carrierId=carrierId,
            podCode=podCode,
            ctnrCode=ctnrCode,
            tranTaskNum=tranTaskNum,
            wbCode=wbCode,
            uname=uname,
            dstMapCode=dstMapCode,
            groupNum=groupNum,
            liftCode=liftCode,
            srcEqName=srcEqName,
            desEqName=desEqName,
            sdateTo=sdateTo,
            edateTo=edateTo,
            limit=limit,
        )
        return result
    except Exception as e:
        return {"message": "error", "errors": [str(e)]}


@rcs_web_router.post("/find_sub_tasks_detail")
def find_sub_tasks_detail_api(
    trans_task_num: str, search_year: int = 2020, show_his_data: str = "false"
):
    try:
        result = rcs_api.find_sub_tasks_detail(
            trans_task_num=trans_task_num,
            search_year=search_year,
            show_his_data=show_his_data,
        )
        return result
    except Exception as e:
        return {"message": "error", "errors": [str(e)]}


@rcs_web_router.post("/stopagv")
def stopagv(
    agvcode=Body("", description="agv编号"), stop=Body(False, description="是否stop")
):
    try:
        result = rcs_api.stopResumeOffline(
            agvCodes=agvcode, flag="stop" if stop else "resume"
        )
        return result
    except Exception as e:
        return {"message": "error", "errors": [str(e)]}


@rcs_web_router.post("/get_agv_status")
def get_agv_status_api(
    client_code: str = "",
    robot_count: str = "-1",
    robots: str = "",
    map_short_name: str = "",
):
    try:
        result = rcs_api.get_agv_status(
            client_code=client_code,
            robot_count=robot_count,
            robots=robots,
            map_short_name=map_short_name,
        )
        return result
    except Exception as e:
        return {"message": "error", "errors": [str(e)]}


@rcs_web_router.post("/login")
def login_api(username: str, password: str, pwd_safe_level: str = "3"):
    try:
        result = rcs_api.login(
            username=username, password=password, pwd_safe_level=pwd_safe_level
        )
        return result
    except Exception as e:
        return {"message": f"error {str(e)}", "success": False}


@rcs_web_router.get("/login2")
def login_api2():
    try:
        result = rcs_api.login(
            username=cfg.get("rcms.username"),
            password=cfg.get("rcms.password"),
            pwd_safe_level="3",
        )
        return result
    except Exception as e:
        return {"message": f"error {str(e)}", "success": False}


