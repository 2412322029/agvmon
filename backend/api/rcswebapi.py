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
    if cfg.get("test"):
        return {
            "total": 1,
            "code": 0,
            "data": [
                {
                    "carrierId": "P8000118A2MH021672027",
                    "carrierLoc": "MFAGV3AE",
                    "chgRobDate": "2026-01-21 01:19:10",
                    "customField": "null",
                    "dateChg": "2026-01-21 01:18:03",
                    "dateCr": "2026-01-21 01:18:03",
                    "desEqName": "MFBUF303B03",
                    "desMac": "MFBUF303B",
                    "desMacType": "BUFFER",
                    "desPort": "MFBUF303B03",
                    "dstMapCode": "AA",
                    "liftCode": "",
                    "mapCode": "AA",
                    "priority": 50,
                    "repalce": 50,
                    "robotCode": "3002",
                    "srcEqName": "MFPATH00",
                    "srcMac": "MFAGV3AE",
                    "srcMacType": "EQ",
                    "srcPort": "MFAGV3AE",
                    "taskStatus": "2",
                    "taskStatusStr": "正在执行",
                    "taskTyp": "偏贴下料(G#H#K#)",
                    "tranTaskItem": "MFAGV3002026012101180413442HS",
                    "tranTaskNum": "MFAGV3002026012101180413442HS",
                    "uname": "MCS",
                    "upDown": "DOWN",
                    "userCallCode": "110137AA030537",
                    "via": '["110137AA030537","128620AA038975"]',
                },
                {
                    "carrierId": "P8000118A2MH021672027",
                    "carrierLoc": "MFAGV3AE",
                    "chgRobDate": "2026-01-21 01:19:10",
                    "customField": "null",
                    "dateChg": "2026-01-21 01:18:03",
                    "dateCr": "2026-01-21 01:18:03",
                    "desEqName": "MFBUF303B03",
                    "desMac": "MFBUF303B",
                    "desMacType": "BUFFER",
                    "desPort": "MFBUF303B03",
                    "dstMapCode": "AA",
                    "liftCode": "",
                    "mapCode": "AA",
                    "priority": 50,
                    "repalce": 50,
                    "robotCode": "3002",
                    "srcEqName": "MFPATH00",
                    "srcMac": "MFAGV3AE",
                    "srcMacType": "EQ",
                    "srcPort": "MFAGV3AE",
                    "taskStatus": "2",
                    "taskStatusStr": "正在执行",
                    "taskTyp": "偏贴下料(G#H#K#)",
                    "tranTaskItem": "MFAGV3002026112101180413442HS",
                    "tranTaskNum": "MFAGV3002026112101180413442HS",
                    "uname": "MCS",
                    "upDown": "DOWN",
                    "userCallCode": "110137AA030537",
                    "via": '["110137AA030537","128620AA038975"]',
                },
            ],
            "success": True,
            "count": 1,
        }

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
    trans_task_num: str = Body("", description="任务编号"),
    search_year: int = Body(2020, description="搜索年份"),
    show_his_data: str = Body("false", description="是否显示历史数据"),
):
    if cfg.get("test"):
        return {
            "data": [
                {
                    "dateChg": "2026-01-21 01:20:22",
                    "dateCr": "2026-01-21 01:18:03",
                    "dstMapCode": "AA",
                    "endX": 110137.0,
                    "endY": 30537.0,
                    "groupFlag": 0,
                    "loopExec": "0",
                    "mainTaskNum": "MFAGV3002026012101180413442HS",
                    "mainTaskSeq": 1,
                    "mapCode": "MOD2L30",
                    "needConfirm": "0",
                    "needTrigger": "0",
                    "podTyp": "",
                    "priority": 50,
                    "robotCode": "3002_Check",
                    "subTaskNum": "19BDC69DC32VZ44_ECS",
                    "subTaskSeq": 1,
                    "subTaskTyp": "辊筒车移动",
                    "taskMsg": '&lt;?xml version="1.0" encoding="UTF-8"?&gt;\n &lt;Message ReqCode="19BDC69DC35VZ45"&gt;\n &lt;Type &gt;EXECUTE_REQ &lt;/Type &gt;\n &lt;MapCode &gt;AA &lt;/MapCode &gt;\n &lt;Id &gt;19BDC69DC32VZ44_ECS &lt;/Id &gt;\n &lt;CanceledId/&gt;\n &lt;RobotId &gt;-1 &lt;/RobotId &gt;\n &lt;Priority &gt;50 &lt;/Priority &gt;\n &lt;RobotType &gt;$21 &lt;/RobotType &gt;\n &lt;Task &gt;\n &lt;TaskType &gt;MOVE_ROBOT_LOAD &lt;/TaskType &gt;\n &lt;SubTaskNum &gt;1 &lt;/SubTaskNum &gt;\n &lt;SubTask &gt;&lt;SubTaskType &gt;MOVE_ROBOT_LOAD &lt;/SubTaskType &gt;&lt;Seq &gt;1 &lt;/Seq &gt;&lt;Target x="110137.0" y="30537.0" name="MFPATH00"/&gt;&lt;Load Index="101"&gt;2 &lt;/Load &gt;&lt;Direction &gt;1000 &lt;/Direction &gt;&lt;Offset &gt;1 &lt;/Offset &gt;&lt;Stay &gt;1 &lt;/Stay &gt;&lt;/SubTask &gt;&lt;/Task &gt;\n &lt;/Message &gt;',
                    "taskStatus": "9",
                    "taskStatusStr": "已结束",
                    "taskTypCode": "PTA_BUF_DOWN_1",
                    "thirdMethod": "toAgv",
                    "thirdOutBinMethod": "",
                    "thirdStartMethod": "",
                    "thirdTyp": "LIFT",
                    "thirdUrl": "/agvCallback",
                    "transTaskNum": "MFAGV3002026012101180413442HS",
                    "wbCode": "110137AA030537",
                    "wbCodeName": "110137AA030537",
                },
                {
                    "dateChg": "2026-01-21 01:20:25",
                    "dateCr": "2026-01-21 01:18:03",
                    "dstMapCode": "AA",
                    "endX": 110137.0,
                    "endY": 30537.0,
                    "groupFlag": 0,
                    "loopExec": "0",
                    "mainTaskNum": "MFAGV3002026012101180413442HS",
                    "mainTaskSeq": 1,
                    "mapCode": "MOD2L30",
                    "needConfirm": "0",
                    "needTrigger": "1",
                    "podTyp": "",
                    "priority": 50,
                    "robotCode": "3002_Check",
                    "startX": 110137.0,
                    "startY": 30537.0,
                    "subTaskNum": "19BDC69DC3AVZ46_ECS",
                    "subTaskSeq": 2,
                    "subTaskTyp": "辊筒旋转",
                    "taskMsg": '&lt;?xml version="1.0" encoding="UTF-8"?&gt;\n &lt;Message ReqCode="19BDC69DC3BVZ47"&gt;\n &lt;Type &gt;EXECUTE_REQ &lt;/Type &gt;\n &lt;MapCode &gt;AA &lt;/MapCode &gt;\n &lt;Id &gt;19BDC69DC3AVZ46_ECS &lt;/Id &gt;\n &lt;CanceledId/&gt;\n &lt;RobotId &gt;3002 &lt;/RobotId &gt;\n &lt;Priority &gt;50 &lt;/Priority &gt;\n &lt;RobotType &gt;$21 &lt;/RobotType &gt;\n &lt;Task &gt;\n &lt;TaskType &gt;ROBOT_ROLL &lt;/TaskType &gt;\n &lt;SubTaskNum &gt;1 &lt;/SubTaskNum &gt;\n &lt;SubTask &gt;&lt;SubTaskType &gt;ROBOT_ROLL &lt;/SubTaskType &gt;&lt;Seq &gt;1 &lt;/Seq &gt;&lt;Target x="110137.0" y="30537.0"/&gt;&lt;Roll Index="1" Operator="2" BoxNum="1" Offset="1"/&gt;&lt;Wait time="1"&gt;1 &lt;/Wait &gt;&lt;Stay &gt;0 &lt;/Stay &gt;&lt;/SubTask &gt;&lt;/Task &gt;\n &lt;/Message &gt;',
                    "taskStatus": "2",
                    "taskStatusStr": "正在执行",
                    "taskTypCode": "PTA_BUF_DOWN_1",
                    "thirdMethod": "release",
                    "thirdOutBinMethod": "",
                    "thirdStartMethod": "",
                    "thirdTyp": "LIFT",
                    "thirdUrl": "/agvCallback",
                    "transTaskNum": "MFAGV3002026012101180413442HS",
                    "triggerSource": "MFAGV3002026012101180413442HS",
                    "triggerTyp": "任务单号",
                    "wbCode": "110137AA030537",
                    "wbCodeName": "110137AA030537",
                },
                {
                    "dateChg": "2026-01-21 01:18:03",
                    "dateCr": "2026-01-21 01:18:03",
                    "dstMapCode": "AA",
                    "endX": 128620.0,
                    "endY": 38975.0,
                    "groupFlag": 0,
                    "loopExec": "0",
                    "mainTaskNum": "MFAGV3002026012101180413442HS",
                    "mainTaskSeq": 1,
                    "mapCode": "",
                    "needConfirm": "0",
                    "needTrigger": "0",
                    "podTyp": "",
                    "priority": 50,
                    "robotCode": "-1",
                    "subTaskNum": "19BDC69DC3BVZ48_ECS",
                    "subTaskSeq": 3,
                    "subTaskTyp": "辊筒车移动",
                    "taskMsg": '&lt;?xml version="1.0" encoding="UTF-8"?&gt;\n &lt;Message ReqCode="19BDC69DC3EVZ49"&gt;\n &lt;Type &gt;EXECUTE_REQ &lt;/Type &gt;\n &lt;MapCode &gt;AA &lt;/MapCode &gt;\n &lt;Id &gt;19BDC69DC3BVZ48_ECS &lt;/Id &gt;\n &lt;CanceledId/&gt;\n &lt;RobotId &gt;-1 &lt;/RobotId &gt;\n &lt;Priority &gt;50 &lt;/Priority &gt;\n &lt;RobotType &gt;$21 &lt;/RobotType &gt;\n &lt;Task &gt;\n &lt;TaskType &gt;MOVE_ROBOT_LOAD &lt;/TaskType &gt;\n &lt;SubTaskNum &gt;1 &lt;/SubTaskNum &gt;\n &lt;SubTask &gt;&lt;SubTaskType &gt;MOVE_ROBOT_LOAD &lt;/SubTaskType &gt;&lt;Seq &gt;1 &lt;/Seq &gt;&lt;Target x="128620.0" y="38975.0"/&gt;&lt;Load Index=""&gt;1 &lt;/Load &gt;&lt;Direction &gt;1000 &lt;/Direction &gt;&lt;Offset &gt;1 &lt;/Offset &gt;&lt;Stay &gt;1 &lt;/Stay &gt;&lt;/SubTask &gt;&lt;/Task &gt;\n &lt;/Message &gt;',
                    "taskStatus": "1",
                    "taskStatusStr": "已创建",
                    "taskTypCode": "PTA_BUF_DOWN_1",
                    "thirdMethod": "fromAgv",
                    "thirdOutBinMethod": "",
                    "thirdStartMethod": "",
                    "thirdTyp": "LIFT",
                    "thirdUrl": "/agvCallback",
                    "transTaskNum": "MFAGV3002026012101180413442HS",
                    "wbCode": "110137AA030537",
                    "wbCodeName": "110137AA030537",
                },
                {
                    "dateChg": "2026-01-21 01:18:03",
                    "dateCr": "2026-01-21 01:18:03",
                    "dstMapCode": "AA",
                    "groupFlag": 0,
                    "loopExec": "0",
                    "mainTaskNum": "MFAGV3002026012101180413442HS",
                    "mainTaskSeq": 1,
                    "mapCode": "MOD2L30",
                    "needConfirm": "0",
                    "needTrigger": "1",
                    "podTyp": "",
                    "priority": 50,
                    "robotCode": "-1",
                    "subTaskNum": "19BDC69DC45VZ40_ECS",
                    "subTaskSeq": 4,
                    "subTaskTyp": "辊筒旋转",
                    "taskMsg": '&lt;?xml version="1.0" encoding="UTF-8"?&gt;\n &lt;Message ReqCode="19BDC69DC48VZ4A"&gt;\n &lt;Type &gt;EXECUTE_REQ &lt;/Type &gt;\n &lt;MapCode &gt;AA &lt;/MapCode &gt;\n &lt;Id &gt;19BDC69DC45VZ40_ECS &lt;/Id &gt;\n &lt;CanceledId/&gt;\n &lt;RobotId &gt;-1 &lt;/RobotId &gt;\n &lt;Priority &gt;50 &lt;/Priority &gt;\n &lt;RobotType &gt;$21 &lt;/RobotType &gt;\n &lt;Task &gt;\n &lt;TaskType &gt;ROBOT_ROLL &lt;/TaskType &gt;\n &lt;SubTaskNum &gt;1 &lt;/SubTaskNum &gt;\n &lt;SubTask &gt;&lt;SubTaskType &gt;ROBOT_ROLL &lt;/SubTaskType &gt;&lt;Seq &gt;1 &lt;/Seq &gt;&lt;Target x="" y=""/&gt;&lt;Roll Index="" Operator="1" BoxNum="1" Station="1" Offset="1"/&gt;&lt;Wait time="-1"&gt;1 &lt;/Wait &gt;&lt;Stay &gt;0 &lt;/Stay &gt;&lt;/SubTask &gt;&lt;/Task &gt;\n &lt;/Message &gt;',
                    "taskStatus": "1",
                    "taskStatusStr": "已创建",
                    "taskTypCode": "PTA_BUF_DOWN_1",
                    "thirdMethod": "release",
                    "thirdOutBinMethod": "",
                    "thirdStartMethod": "",
                    "thirdTyp": "LIFT",
                    "thirdUrl": "/agvCallback",
                    "transTaskNum": "MFAGV3002026012101180413442HS",
                    "triggerTyp": "任务单号",
                    "wbCode": "110137AA030537",
                    "wbCodeName": "110137AA030537",
                },
            ],
            "success": True,
        }

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
def login_api(
    username: str = Body(..., embed=False),
    password: str = Body(..., embed=False),
    pwd_safe_level: str = Body("3", embed=False),
):
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


@rcs_web_router.post("/check_is_rolling")
def check_is_rolling_api(
    trans_task_nums: str = Body("", embed=True, description="传输任务编号，多个任务号用逗号分隔"),
):
    try:
        result = rcs_api.check_is_rolling(trans_task_nums=trans_task_nums)
        return result
    except Exception as e:
        return {"message": "error", "errors": [str(e)]}


@rcs_web_router.post("/check_starting_trans_tasks")
def check_starting_trans_tasks_api(
    trans_task_nums: str = Body("", embed=True, description="传输任务编号，多个任务号用逗号分隔"),
):
    try:
        result = rcs_api.check_starting_trans_tasks(trans_task_nums=trans_task_nums)
        return result
    except Exception as e:
        return {"message": "error", "errors": [str(e)]}


@rcs_web_router.post("/check_soft_cancel")
def check_soft_cancel_api(
    trans_task_nums: str = Body("", embed=True, description="传输任务编号，多个任务号用逗号分隔"),
):
    try:
        result = rcs_api.check_soft_cancel(trans_task_nums=trans_task_nums)
        return result
    except Exception as e:
        return {"message": "error", "errors": [str(e)]}


@rcs_web_router.post("/cancel_trans_tasks")
def cancel_trans_tasks_api(
    trans_task_nums: str = Body("", embed=True, description="传输任务编号，多个任务号用逗号分隔"),
    cancel_type: str = Body("0", embed=True, description="取消类型"),
    cancel_reason: str = Body("2", embed=True, description="取消原因"),
):
    try:
        result = rcs_api.cancel_trans_tasks(
            trans_task_nums=trans_task_nums,
            cancel_type=cancel_type,
            cancel_reason=cancel_reason
        )
        return result
    except Exception as e:
        return {"message": "error", "errors": [str(e)]}
