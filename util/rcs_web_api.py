import functools
import json
import logging
import os
import pathlib
from datetime import datetime, timedelta
from hashlib import md5, sha256

import httpx

from util.config import cfg

logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger()
cache_path = pathlib.Path(os.path.join(os.path.dirname(__file__), "data/cache"))
if not cache_path.exists():
    cache_path.mkdir()


class RcsWebApi:
    """RCS Web API客户端类，用于与RCS系统进行交互"""

    def __init__(self, base_url=None, username=None, password=None):
        self.base_url = base_url or cfg.get_with_reload("rcms.host") + "/rcms/web"
        self.username = username or cfg.get_with_reload("rcms.username")
        self.password = password or cfg.get_with_reload("rcms.password")
        self.client = None
        self.cookies = None
        self.current_cache_path = cache_path / (
            cfg.get("rcms.host").split("://")[1].replace(".", "_").replace(":", "-")
        )

    async def __aenter__(self):
        self._init_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
            self.client = None

    def _init_client(self):
        """创建httpx客户端（含默认headers）"""
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            cookies={"same": "agvmon"},
            verify=False,
        )

    async def _request(
        self,
        endpoint: str,
        data: dict = None,
        json_data: dict = None,
        content_type: str = "application/x-www-form-urlencoded; charset=UTF-8",
        timeout: int = 10,
        retry_on_empty: bool = True,
        extra_headers: dict = None,
    ) -> dict:
        """
        统一POST请求，自动处理headers、cookies、登录过期重试、JSON解析。

        返回dict，HTTP/解析错误时包含 _error=True 标记，调用方可据此判断。
        """
        url = self.base_url + endpoint
        headers = {"Content-Type": content_type}
        if extra_headers:
            headers.update(extra_headers)
        self.client.headers.update(headers)
        self.client.cookies = self.cookies
        resp = await self.client.post(url, data=data, json=json_data, timeout=timeout)

        if not resp.text and retry_on_empty:
            await self.login(self.username, self.password)
            self.client.cookies = self.cookies
            resp = await self.client.post(
                url, data=data, json=json_data, timeout=timeout
            )

        if resp.status_code != 200:
            return {
                "success": False,
                "_error": True,
                "msg": f"请求失败，状态码：{resp.status_code}，响应内容：{resp.text}",
            }

        try:
            return resp.json()
        except Exception:
            return {
                "success": False,
                "_error": True,
                "msg": f"解析响应失败，状态码：{resp.status_code}，响应内容：{resp.text}",
            }

    async def login(self, username, password, pwd_safe_level="3"):
        """登录RCS系统"""
        self._init_client()
        if not username or not password:
            raise Exception("用户名和密码不能为空")

        if cfg.get("rcms.hash") == "md5":
            pwd = md5(password.encode("utf-8")).hexdigest()
        elif cfg.get("rcms.hash") == "sha256":
            pwd = sha256(password.encode("utf-8")).hexdigest()
        else:
            raise Exception("unknown hash, md5 or sha256")

        data = {
            "ecsUserName": username,
            "ecsPassword": pwd,
            "pwdSafeLevelLogin": pwd_safe_level,
        }
        response = await self.client.post(
            self.base_url + "/login/login.action",
            data=data,
            cookies={
                "JSESSIONID": "86DFC75B5C1472F831C3E15FF31152B5",
                "HIK_COOKIE": "19BDC358E70VGIB",
            },
            timeout=10,
        )
        logger.info(f"登录rcs2000 web:{response.text}")
        self.cookies = self.client.cookies
        if response.status_code != 200:
            raise Exception(
                f"登录失败，状态码：{response.status_code}，响应内容：{response.text}"
            )
        if not response.json().get("success"):
            raise Exception(f"登录失败，响应内容：{response.json()}")
        return response.json()

    async def find_tasks_detail(
        self,
        robotCode="",
        taskTyp="",
        taskStatus="",
        carrierId="",
        podCode="",
        ctnrCode="",
        tranTaskNum="",
        wbCode="",
        uname="",
        dstMapCode="",
        groupNum="",
        liftCode="",
        srcEqName="",
        desEqName="",
        sdateTo=None,
        edateTo=None,
        limit=20,
    ):
        """查询任务详情"""
        if sdateTo is None or edateTo is None:
            today = datetime.today()
            yesterday = today - timedelta(days=1)
            sdateTo = yesterday.strftime("%Y-%m-%d 00:00:00")
            edateTo = today.strftime("%Y-%m-%d 23:59:59")

        data = {
            "start": 1,
            "taskTyp": taskTyp,
            "taskStatus": taskStatus,
            "carrierId": carrierId,
            "podCode": podCode,
            "ctnrCode": ctnrCode,
            "tranTaskNum": tranTaskNum,
            "wbCode": wbCode,
            "uname": uname,
            "dstMapCode": dstMapCode,
            "groupNum": groupNum,
            "liftCode": liftCode,
            "srcEqName": srcEqName,
            "desEqName": desEqName,
            "robotCode": robotCode,
            "sdateTo": sdateTo,
            "edateTo": edateTo,
            "limit": limit,
            "showHisData": False,
        }
        self.client.headers.update(
            {"accept": "application/json, text/javascript, */*; q=0.01"}
        )
        d = await self._request("/transTask/findListWithPages.action", data=data)
        if not d.get("success"):
            raise Exception(f"查询任务详情失败，响应内容：{d}")
        return d

    async def find_sub_tasks_detail(
        self, trans_task_num, search_year=2020, show_his_data="false"
    ):
        """查询子任务详情"""
        return await self._request(
            "/transTask/findSubTasksDetail.action",
            data={
                "transTaskNum": trans_task_num,
                "searchYear": search_year,
                "showHisData": show_his_data,
            },
        )

    async def stopResumeOffline(self, agvCodes="", flag="resume"):
        """停止/恢复AGV离线"""
        return await self._request(
            "/agvControl/stopResumeOffline.action",
            json_data={
                "clientCode": "",
                "robotNum": "",
                "agvCodes": agvCodes,
                "mapShortName": "",
                "stopResumeOffline": flag,
            },
            content_type="application/json",
        )

    async def get_agv_status(
        self, client_code="", robot_count="-1", robots="", map_short_name=""
    ):
        """获取AGV状态"""
        return await self._request(
            "/agvQuery/getAgvStatus.action",
            json_data={
                "clientCode": client_code,
                "robotCount": robot_count,
                "robots": robots,
                "mapShortName": map_short_name,
            },
            content_type="application/json; charset=UTF-8",
        )

    async def check_is_rolling(self, trans_task_nums):
        """检查任务是否正在滚动执行"""
        return await self._request(
            "/transTask/checkRollTransTasks.action",
            data={"transTaskNums": trans_task_nums},
        )

    async def check_starting_trans_tasks(self, trans_task_nums):
        """检查开始传输任务"""
        return await self._request(
            "/transTask/checkStartingTransTasks.action",
            data={"transTaskNums": trans_task_nums},
        )

    async def check_soft_cancel(self, trans_task_nums):
        """检查软取消任务"""
        return await self._request(
            "/transTask/checkSoftCancel.action",
            data={"transTaskNums": trans_task_nums},
            timeout=10,
        )

    async def cancel_trans_tasks(
        self, trans_task_nums, cancel_type="0", toStationTaskCodes=""
    ):
        """取消传输任务"""
        d = await self._request(
            "/transTask/cancelTransTasks.action",
            data={
                "transTaskNums": trans_task_nums,
                "cancelType": cancel_type,
                "toStationTaskCodes": toStationTaskCodes,
            },
        )
        if not d.get("_error"):
            print(d)
        return d

    async def forceCancelTask(self, trans_task_nums: str):
        """强制取消任务"""
        d = await self._request(
            "/taskDispatch/cancelTask.action",
            json_data={"clientCode": "", "tokenCode": "", "taskCode": trans_task_nums},
            content_type="application/json",
            extra_headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.base_url + "/taskDispatch/cms_index.action",
            },
        )
        self.client.headers.update({"X-Requested-With": ""})
        print(self.client.cookies)
        return d

    async def resumeAction(self, agvcode: str):
        """恢复AGV动作"""
        d = await self._request(
            "/taskDispatch/resumeAction.action",
            json_data={"taskCode": "", "agvCode": agvcode, "subTaskNum": ""},
            content_type="application/json",
            extra_headers={"X-Requested-With": "XMLHttpRequest"},
        )
        if not d.get("_error"):
            print(d)
        return d

    async def freeagv(self, agvcode: str):
        """释放AGV"""
        return await self._request(
            "/agvControl/freeRobot.action",
            json_data={"clientCode": "", "agvCode": agvcode},
            content_type="application/json",
            extra_headers={
                "origin": cfg.get("rcms.host"),
                "referer": self.base_url + "/agvControl/cms_index.action",
            },
        )

    async def findAllAgv(self):
        """查询所有AGV"""
        return await self._request(
            "/agvQuery/findAllAgv.action",
            json_data={"clientCode": ""},
            content_type="application/json",
        )

    async def get_agv(self, agvid=""):
        """查询单个AGV状态"""
        d = await self._request(
            "/agvQuery/getAgvStatus.action",
            json_data={
                "clientCode": "",
                "robotCount": "",
                "robots": agvid,
                "mapShortName": "",
            },
            content_type="application/json",
        )
        if not d.get("_error") and d.get("message") == "成功":
            return d
        return {"success": False, "msg": d.get("message", d.get("msg", ""))}

    async def wcsTaskState(
        self, start=1, limit=100, deviceType="rotate", deviceIndex=""
    ):
        """查询WCS任务状态"""
        return await self._request(
            "/wcsTaskState/findTaskState.action",
            data={
                "start": start,
                "limit": limit,
                "deviceType": deviceType,
                "deviceIndex": deviceIndex,
            },
        )

    async def saveagvinfo(self):
        """缓存AGV信息到本地文件"""
        file_path = self.current_cache_path / "agvinfo.json"
        await self.login(username=self.username, password=self.password)
        logger.info("开始缓存AGV信息")
        d = await self.findAllAgv()
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=4)
        logger.info(f"缓存AGV信息到{file_path}")

    async def getPort(
        self,
        start=1,
        limit=20,
        port="",
        mapDataCode="",
        cmsIndex="",
        carrierId="",
        carrierLoc="",
        type=-1,
        upDown=-1,
        buforeq="bufferPort",
        cache=False,
    ):
        """查询端口（bufferPort/machinePort），支持缓存到本地"""
        if buforeq not in ("bufferPort", "machinePort"):
            return {"success": False, "msg": "未知类型bufferPort / machinePort"}

        if cache:
            start, limit = 1, 1000
            port = mapDataCode = cmsIndex = carrierId = carrierLoc = ""
            type = upDown = -1

        data = {
            "start": start,
            "limit": limit,
            "port": port,
            "mapDataCode": mapDataCode,
            "cmsIndex": cmsIndex,
            "carrierId": carrierId,
            "carrierLoc": carrierLoc,
            "type": type,
        }
        if buforeq == "bufferPort":
            data["upDown"] = upDown

        d = await self._request(f"/{buforeq}/findListWithPages.action", data=data)

        if not d.get("_error") and cache:
            file_path = self.current_cache_path / f"{buforeq}.json"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            logger.info(f"{buforeq}缓存成功，路径：{file_path}")

        return d

    async def saveallport(self):
        """缓存所有端口（bufferPort + machinePort）"""
        import traceback

        for buforeq in ("bufferPort", "machinePort"):
            try:
                logger.info(f"开始缓存{buforeq}")
                data = await self.getPort(limit=1000, buforeq=buforeq, cache=True)
                if data.get("success"):
                    logger.info(f"{data.get('success')}|{data.get('total')}")
                else:
                    print(data)
            except Exception as e:
                traceback.print_exc()
                logger.error(f"缓存{buforeq}失败: {e}")

    def transport(self):
        """从缓存的bufferPort/machinePort生成cmsindexmap.json"""
        with open(self.current_cache_path / "bufferPort.json") as f:
            buffer_data = json.load(f)

        result = {}
        # bufferPort: type → 分组
        for key, type_val in {
            "BUFFER": "1",
            "CV": "2",
            "NO_POWER_BUFFER": "3",
            "S_CV": "8",
            "VS": "9",
        }.items():
            d = {}
            for one in buffer_data.get("data", []):
                if one.get("type") != type_val:
                    continue
                name = one.get("port")[:4] if type_val == "1" else one.get("port")
                if name not in d:
                    d[name] = one.get("cmsIndex", "")[:4] + "00"
            result[key] = d

        with open(self.current_cache_path / "machinePort.json") as f:
            machine_data = json.load(f)

        # machinePort: (type, name提取函数) → 分组
        for key, (type_val, name_fn) in {
            "EQ": (
                "1",
                lambda o: (
                    o.get("eqName", "")[:8] + (o.get("carrierLoc", "")[-1:] or "")
                ),
            ),
            "PODEQ": ("4", lambda o: o.get("port", "")),
            "STK": ("3", lambda o: o.get("eqName", "")),
        }.items():
            d = {}
            for one in machine_data.get("data", []):
                if one.get("type") != type_val:
                    continue
                name = name_fn(one)
                if name not in d:
                    d[name] = one.get("cmsIndex", "")[:4] + "00"
            result[key] = d

        file_path = self.current_cache_path / "cmsindexmap.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info(f"cmsindexmap.json缓存成功，路径：{file_path}")

    def get_cmsindexmap(self):
        """从缓存文件读取CMS索引映射表"""
        file_path = self.current_cache_path / "cmsindexmap.json"
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @functools.lru_cache(maxsize=1)
    def get_device_type_options(self):
        """获取设备类型选项（缓存结果）"""
        cmsindexmap = self.get_cmsindexmap()
        return {
            "options": {
                device_type: [
                    {"value": cms_index, "label": device_name}
                    for device_name, cms_index in devices.items()
                ]
                for device_type, devices in cmsindexmap.items()
            }
        }


if __name__ == "__main__":
    import asyncio

    async def main():
        rcs_web_api = RcsWebApi(
            username=cfg.get("rcms.username"),
            password=cfg.get("rcms.password"),
        )
        async with rcs_web_api:
            await rcs_web_api.login(rcs_web_api.username, rcs_web_api.password)
            data = await rcs_web_api.get_agv(agvid="1069")
            print(data)

    asyncio.run(main())
