import functools
import json
import logging
import os
import pathlib
from datetime import datetime, timedelta
from hashlib import md5
from urllib.parse import quote

import httpx

from util.config import cfg

logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger()
cache_path = pathlib.Path(os.path.join(os.path.dirname(__file__), "data/cache"))
if not cache_path.exists():
    cache_path.mkdir()


class RcsWebApi:
    """
    RCS Web API客户端类，用于与RCS系统进行交互
    """

    def __init__(
        self,
        base_url=cfg.get_with_reload("rcms.rcs_web_api") + "/rcms/web",
        username=cfg.get_with_reload("rcms.username"),
        password=cfg.get_with_reload("rcms.password"),
    ):
        """
        初始化RCS Web API客户端

        参数:
            base_url: RCS系统的基础URL
        """
        self.base_url = base_url
        self.username = username
        self.password = password
        self.client = None
        self.cookies = None
        self.current_cache_path = cache_path / cfg.get("rcms.host").split("://")[
            1
        ].replace(".", "_").replace(":", "-")
        # self.login(username, password)
        # print(self.client.cookies)

    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            cookies={
                "same": "agvmon",
            },
            verify=False,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    def _dict_to_formdata(self, data_dict: dict) -> str:
        """
        将字典转换为表单数据格式

        参数:
            data_dict: 要转换的字典

        返回:
            str: 转换后的表单数据字符串
        """
        temp = []
        for k, v in data_dict.items():
            temp.append(f"{quote(str(k))}={quote(str(v))}".replace("%2B", "+"))
            # temp.append(f"{k}={v}")
        return "&".join(temp)

    async def login(self, username, password, pwd_safe_level="3"):
        """
        登录RCS系统

        参数:
            username: 用户名
            password: 密码
            pwd_safe_level: 密码安全级别
            cookies: 可选的Cookie字典

        返回:
            dict: 登录响应的JSON数据
        """
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            verify=False,
        )
        if not username or not password:
            raise Exception("用户名和密码不能为空")

        url = self.base_url + "/login/login.action"
        data = {
            "ecsUserName": username,
            "ecsPassword": md5(password.encode("utf-8")).hexdigest(),
            "pwdSafeLevelLogin": pwd_safe_level,
        }

        response = await self.client.post(
            url,
            data=data,
            cookies={
                "JSESSIONID": "86DFC75B5C1472F831C3E15FF31152B5",
                "HIK_COOKIE": "19BDC358E70VGIB",
            },
            timeout=10
        )
        print(response.text)
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
        """
        查询任务详情
        返回:
            dict: 查询响应的JSON数据
        """
        url = self.base_url + "/transTask/findListWithPages.action"

        # 如果没有提供日期范围，使用近2天：昨天00:00:00到今天23:59:59
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
            # "bigDataFlag": True,
            "showHisData": False,
        }
        self.client.headers.update(
            {"accept": "application/json, text/javascript, */*; q=0.01"}
        )
        self.client.cookies = self.cookies
        response = await self.client.post(url, data=data)

        if not response.text:
            await self.login(username=self.username, password=self.password)
            response = await self.client.post(url, data=data)
        if response.status_code != 200:
            raise Exception(
                f"查询任务详情失败，状态码：{response.status_code}，响应内容：{response.text}"
            )
        # print(response.text)
        try:
            d = response.json()
        except Exception:
            # print(response.text)
            return {"success": False, "msg": response.text}
        if not d.get("success"):
            raise Exception(f"查询任务详情失败，响应内容：{response.json()}")
        return response.json()

    async def find_sub_tasks_detail(
        self, trans_task_num, search_year=2020, show_his_data="false"
    ):
        """
        查询子任务详情

        参数:
            trans_task_num: 任务号
            search_year: 搜索年份
            show_his_data: 是否显示历史数据

        返回:
            dict: 查询响应的JSON数据
        """
        url = self.base_url + "/transTask/findSubTasksDetail.action"
        data = {
            "transTaskNum": trans_task_num,
            "searchYear": search_year,
            "showHisData": show_his_data,
        }
        self.client.cookies = self.cookies
        response = await self.client.post(
            url,
            data=data,
        )
        if not response.text:
            await self.login(username=self.username, password=self.password)
            response = await self.client.post(url, data=data)
        return response.json()

    async def stopResumeOffline(self, agvCodes="", flag="resume"):  # stop / resume
        url = self.base_url + "/agvControl/stopResumeOffline.action"
        data = {
            "clientCode": "",
            "robotNum": "",
            "agvCodes": agvCodes,
            "mapShortName": "",
            "stopResumeOffline": flag,
        }
        self.client.headers.update({"content-type": "application/json"})
        self.client.cookies = self.cookies
        response = await self.client.post(
            url,
            json=data,
        )
        return response.json()

    async def get_agv_status(
        self, client_code="", robot_count="-1", robots="", map_short_name=""
    ):
        """
        获取AGV状态

        参数:
            client_code: 客户端代码
            robot_count: 机器人数量，-1表示查询所有
            robots: 机器人列表，逗号分隔
            map_short_name: 地图名称

        返回:
            dict: 查询响应的JSON数据
        """
        url = self.base_url + "/agvQuery/getAgvStatus.action"
        data = {
            "clientCode": client_code,
            "robotCount": robot_count,
            "robots": robots,
            "mapShortName": map_short_name,
        }
        self.client.headers.update(
            {
                "Content-Type": "application/json; charset=UTF-8",
            }
        )
        self.client.cookies = self.cookies
        response = await self.client.post(
            url,
            json=data,
        )
        return response.json()

    async def check_is_rolling(self, trans_task_nums):
        """
        检查任务是否正在滚动执行

        参数:
            trans_task_nums: 传输任务编号，多个任务号可以用逗号分隔

        返回:
            dict: 查询响应的JSON数据
        """
        url = self.base_url + "/transTask/checkIsRolling.action"
        data = {
            "transTaskNums": trans_task_nums,
        }
        self.client.headers.update(
            {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
        )
        self.client.cookies = self.cookies
        response = await self.client.post(url, data=data)

        if not response.text:
            await self.login(username=self.username, password=self.password)
            response = await self.client.post(url, data=data)
        if response.status_code != 200:
            raise Exception(
                f"检查任务滚动状态失败，状态码：{response.status_code}，响应内容：{response.text}"
            )
        try:
            d = response.json()
        except Exception:
            return {"success": False, "msg": response.text}
        return d

    async def check_starting_trans_tasks(self, trans_task_nums):
        """
        检查开始传输任务

        参数:
            trans_task_nums: 传输任务编号，多个任务号可以用逗号分隔

        返回:
            dict: 查询响应的JSON数据
        """
        url = self.base_url + "/transTask/checkStartingTransTasks.action"
        data = {
            "transTaskNums": trans_task_nums,
        }
        self.client.headers.update(
            {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
        )
        self.client.cookies = self.cookies
        response = await self.client.post(url, data=data)

        if not response.text:
            await self.login(username=self.username, password=self.password)
            response = await self.client.post(url, data=data)
        if response.status_code != 200:
            return {
                "success": False,
                "msg": f"检查开始传输任务失败，状态码：{response.status_code}，响应内容：{response.text}",
            }
        try:
            d = response.json()
        except Exception:
            return {"success": False, "msg": response.text}
        return d

    async def check_soft_cancel(self, trans_task_nums):
        """
        检查软取消任务

        参数:
            trans_task_nums: 传输任务编号，多个任务号可以用逗号分隔

        返回:
            dict: 查询响应的JSON数据
        """
        url = self.base_url + "/transTask/checkSoftCancel.action"
        data = {
            "transTaskNums": trans_task_nums,
        }
        self.client.cookies = self.cookies
        self.client.headers.update(
            {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
        )
        response = await self.client.post(url, data=data,timeout=10)

        if not response.text:
            await self.login(username=self.username, password=self.password)
            response = await self.client.post(url, data=data)
        if response.status_code != 200:
            return {
                "success": False,
                "msg": f"检查软取消任务失败，状态码：{response.status_code}，响应内容：{response.text}",
            }
        try:
            d = response.json()
        except Exception:
            return {"success": False, "msg": response.text}
        return d

    async def cancel_trans_tasks(
        self, trans_task_nums, cancel_type="0", cancel_reason="2"
    ):
        """
        取消传输任务

        参数:
            trans_task_nums: 传输任务编号，多个任务号可以用逗号分隔
            cancel_type: 取消类型，默认为"0"
            cancel_reason: 取消原因，默认为"2"

        返回:
            dict: 查询响应的JSON数据
        """
        url = self.base_url + "/transTask/cancelTransTasks.action"
        data = {
            "transTaskNums": trans_task_nums,
            "cancelType": cancel_type,
            "forceCancel": 2,
            "cancelReason": cancel_reason,
        }
        self.client.headers.update(
            {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
        )
        self.client.cookies = self.cookies
        response = await self.client.post(url, data=data)

        if not response.text:
            await self.login(username=self.username, password=self.password)
            response = await self.client.post(url, data=data)
        if response.status_code != 200:
            return {
                "success": False,
                "msg": f"取消任务失败，状态码：{response.status_code}，响应内容：{response.text}",
            }

        try:
            d = response.json()
            print(d)
        except Exception:
            return {"success": False, "msg": response.text}
        return d

    async def forceCancelTask(self, trans_task_nums: str):
        url = self.base_url + "/taskDispatch/cancelTask.action"
        data = {"clientCode": "", "tokenCode": "", "taskCode": trans_task_nums}
        self.client.headers.update(
            {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.base_url + "/taskDispatch/cms_index.action",
            }
        )
        self.client.cookies = self.cookies
        response = await self.client.post(url, json=data)
        if response.status_code != 200:
            return {
                "success": False,
                "msg": f"取消任务失败，状态码：{response.status_code}，响应内容：{response.text}",
            }
        d = response.json()
        # if d["resultCode"] == "redirect":
        #     response = self.client.post(d["message"], data=data)
        #     d = response.text
        self.client.headers.update({"X-Requested-With": ""})
        print(self.client.cookies)
        return d

    async def resumeAction(self, agvcode: str):
        url = self.base_url + "/taskDispatch/resumeAction.action"
        data = {"taskCode": "", "agvCode": agvcode, "subTaskNum": ""}
        self.client.headers.update(
            {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
            }
        )
        self.client.cookies = self.cookies
        response = await self.client.post(url, json=data)
        if not response.text:
            await self.login(username=self.username, password=self.password)
            response = await self.client.post(url, json=data)
        if response.status_code != 200:
            return {
                "success": False,
                "msg": f"取消任务失败，状态码：{response.status_code}，响应内容：{response.text}",
            }

        try:
            d = response.json()
            print(d)
        except Exception:
            return {"success": False, "msg": response.text}
        return d

    async def freeagv(self, agvcode: str):
        url = self.base_url + "/agvControl/freeRobot.action"
        data = {"clientCode": "", "agvCode": agvcode}
        self.client.headers.update(
            {
                "Content-Type": "application/json",
                # "X-Requested-With": "XMLHttpRequest",
                "origin": cfg.get("rcms.host"),
                "referer": self.base_url + "/agvControl/cms_index.action",
            }
        )
        self.client.cookies = self.cookies
        response = await self.client.post(url, json=data)

        if not response.text:
            await self.login(username=self.username, password=self.password)
            response = await self.client.post(url, json=data)
        if response.status_code != 200:
            return {
                "success": False,
                "msg": f"freeagv失败，状态码：{response.status_code}，响应内容：{response.text}",
            }

        try:
            d = response.json()
        except Exception:
            return {"success": False, "msg": response.text}
        return d

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
        buforeq="bufferPort",  # bufferPort / machinePort
        cache=False,
    ):
        if buforeq != "bufferPort" and buforeq != "machinePort":
            return {
                "success": False,
                "msg": "未知类型bufferPort / machinePort",
            }
        if cache:
            start = 1
            limit = 1000
            port = ""
            mapDataCode = ""
            cmsIndex = ""
            carrierId = ""
            carrierLoc = ""
            type = -1
            upDown = -1
            logger.info(f"limit={limit}, other args ignored")
        url = self.base_url + f"/{buforeq}/findListWithPages.action"
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
            data.update({"upDown": upDown})
        self.client.headers.update(
            {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }
        )
        self.client.cookies = self.cookies
        response = await self.client.post(url, data=data)

        if not response.text:
            await self.login(username=self.username, password=self.password)
            response = await self.client.post(url, data=data)
        if response.status_code != 200:
            return {
                "success": False,
                "msg": f"getPort失败，状态码：{response.status_code}，响应内容：{response.text}",
            }

        try:
            d = response.json()
            if cache:
                file_path = self.current_cache_path / f"{buforeq}.json"
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, "w") as f:
                    json.dump(d, f, ensure_ascii=False, indent=2)
                    logger.info(f"{buforeq}缓存成功，路径：{file_path}")
            return d
        except Exception:
            return {"success": False, "msg": response.text}
        return d

    async def saveallport(self):
        import traceback

        try:
            logger.info("开始缓存bufferPort")
            data = await self.getPort(limit=1000, buforeq="bufferPort", cache=True)
            if data.get("success"):
                logger.info(f"{data.get('success')}|{data.get('total')}")
            else:
                print(data)
        except Exception as e:
            traceback.print_exc()
            logger.error(f"缓存bufferPort失败: {e}")
        try:
            logger.info("开始缓存machinePort")
            data2 = await self.getPort(limit=1000, buforeq="machinePort", cache=True)
            if data2.get("success"):
                logger.info(f"{data2.get('success')}|{data2.get('total')}")
            else:
                print(data2)
        except Exception as e:
            traceback.print_exc()
            logger.error(f"缓存machinePort失败: {e}")

    def transport(self):
        file_path = self.current_cache_path / "bufferPort.json"
        with open(file_path, "r") as f:
            data = json.load(f)
        buffer_dict = {}
        for one in data.get("data", []):
            if one.get("type") == "1":
                name = one.get("port")[:8]
                if name in buffer_dict:
                    continue
                cmsIndex = one.get("cmsIndex")[:4] + "00"
                buffer_dict[name] = cmsIndex
        # print(f"buffer_dict: {json.dumps(buffer_dict, ensure_ascii=False, indent=2)}")
        cv_dict = {}
        for one in data.get("data", []):
            if one.get("type") == "2":
                name = one.get("port")[:8]
                if name in cv_dict:
                    continue
                cmsIndex = one.get("cmsIndex")[:4] + "00"
                cv_dict[name] = cmsIndex
        # print(f"cv_dict: {json.dumps(cv_dict, ensure_ascii=False, indent=2)}")
        file_path = self.current_cache_path / "machinePort.json"
        with open(file_path, "r") as f:
            data = json.load(f)
        eq_dict = {}
        for one in data.get("data", []):
            if one.get("type") == "1":
                name = one.get("eqName")[:8] + one.get("carrierLoc")[-1:]
                if name in eq_dict:
                    continue
                cmsIndex = one.get("cmsIndex")[:4] + "00"
                eq_dict[name] = cmsIndex
        # print(f"eq_dict: {json.dumps(eq_dict, ensure_ascii=False, indent=2)}")
        LET_dict = {}
        for one in data.get("data", []):
            if one.get("type") == "2":
                name = one.get("port")
                if name in LET_dict:
                    continue
                cmsIndex = one.get("cmsIndex")[:4] + "00"
                LET_dict[name] = cmsIndex
        PACKING_dict = {}
        for one in data.get("data", []):
            if one.get("type") == "3":
                name = one.get("eqName")
                if name in PACKING_dict:
                    continue
                cmsIndex = one.get("cmsIndex")[:4] + "00"
                PACKING_dict[name] = cmsIndex
        # print(f"PACKING_dict: {json.dumps(PACKING_dict, ensure_ascii=False, indent=2)}")
        stk_dict = {}
        for one in data.get("data", []):
            if one.get("type") == "4":
                name = one.get("port")
                if name in stk_dict:
                    continue
                cmsIndex = one.get("cmsIndex")[:4] + "00"
                stk_dict[name] = cmsIndex
        # print(f"stk_dict: {json.dumps(stk_dict, ensure_ascii=False, indent=2)}")
        all_dict = {
            "BUFFER": buffer_dict,
            "CV": cv_dict,
            "EQ": eq_dict,
            "PACKING": PACKING_dict,
            "STK": stk_dict,
        }
        with open(self.current_cache_path / "cmsindexmap.json", "w") as f:
            json.dump(all_dict, f, ensure_ascii=False, indent=2)
        logger.info(
            f"cmsindexmap.json缓存成功，路径：{self.current_cache_path / 'cmsindexmap.json'}"
        )

    def get_cmsindexmap(self):
        """
        获取CMS索引映射表
        从缓存文件 cmsindexmap.json 中读取CMS索引映射数据。
        返回:
            dict: CMS索引映射字典，包含设备类型和对应的CMS索引列表
        """
        file_path = self.current_cache_path / "cmsindexmap.json"
        with open(file_path, "r") as f:
            data = json.load(f)
        return data

    @functools.lru_cache(maxsize=1)
    def get_device_type_options(self):
        """
        获取设备类型选项 使用 lru_cache 装饰器缓存结果
        """
        cmsindexmap = self.get_cmsindexmap()
        options = {}
        for device_type, devices in cmsindexmap.items():
            options[device_type] = [
                {"value": cms_index, "label": device_name}
                for device_name, cms_index in devices.items()
            ]
        return {"options": options}


if __name__ == "__main__":
    import asyncio

    async def main():
        rcs_web_api = RcsWebApi(
            username=cfg.get("rcms.username"),
            password=cfg.get("rcms.password"),
        )
        async with rcs_web_api:
            print(await rcs_web_api.find_tasks_detail(robotCode=""))

    asyncio.run(main())
