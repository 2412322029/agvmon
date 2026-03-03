from datetime import datetime, timedelta
from hashlib import md5
from urllib.parse import quote

import httpx

from util.config import cfg


class RcsWebApi:
    """
    RCS Web API客户端类，用于与RCS系统进行交互
    """

    def __init__(
        self,
        base_url=cfg.get("rcms.host") + "/rcms/web",
        username=cfg.get("rcms.username"),
        password=cfg.get("rcms.password"),
    ):
        """
        初始化RCS Web API客户端

        参数:
            base_url: RCS系统的基础URL
        """
        self.base_url = base_url
        self.username = username
        self.password = password
        self.client = httpx.Client(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }
        )
        # self.login(username, password)
        # print(self.client.cookies)

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

    def login(self, username, password, pwd_safe_level="3"):
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
        # 验证用户名和密码不为None
        self.client = httpx.Client(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }
        )
        if not username or not password:
            raise Exception("用户名和密码不能为空")

        url = self.base_url + "/login/login.action"
        data = {
            "ecsUserName": username,
            "ecsPassword": md5(password.encode("utf-8")).hexdigest(),
            "pwdSafeLevelLogin": pwd_safe_level,
        }

        response = self.client.post(
            url,
            data=data,
            cookies={
                "JSESSIONID": "86DFC75B5C1472F831C3E15FF31152B5",
                "HIK_COOKIE": "19BDC358E70VGIB",
            },
        )
        print(response.text)
        if response.status_code != 200:
            raise Exception(
                f"登录失败，状态码：{response.status_code}，响应内容：{response.text}"
            )
        if not response.json().get("success"):
            raise Exception(f"登录失败，响应内容：{response.json()}")
        return response.json()

    def find_tasks_detail(
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
        # data=
        response = self.client.post(url, data=data)

        if not response.text:
            self.login(username=self.username, password=self.password)
            response = self.client.post(url, data=data)
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

    def find_sub_tasks_detail(
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

        response = self.client.post(
            url,
            data=data,
        )
        return response.json()

    def stopResumeOffline(self, agvCodes="", flag="resume"):  # stop / resume
        url = self.base_url + "/agvControl/stopResumeOffline.action"
        data = {
            "clientCode": "",
            "robotNum": "",
            "agvCodes": agvCodes,
            "mapShortName": "",
            "stopResumeOffline": flag,
        }
        self.client.headers.update({"content-type": "application/json"})
        response = self.client.post(
            url,
            json=data,
        )
        return response.json()

    def get_agv_status(
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
        response = self.client.post(
            url,
            json=data,
        )
        return response.json()

    def check_is_rolling(self, trans_task_nums):
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
        response = self.client.post(url, data=data)

        if not response.text:
            self.login(username=self.username, password=self.password)
            response = self.client.post(url, data=data)
        if response.status_code != 200:
            raise Exception(
                f"检查任务滚动状态失败，状态码：{response.status_code}，响应内容：{response.text}"
            )
        try:
            d = response.json()
        except Exception:
            return {"success": False, "msg": response.text}
        return d

    def check_starting_trans_tasks(self, trans_task_nums):
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
        response = self.client.post(url, data=data)

        if not response.text:
            self.login(username=self.username, password=self.password)
            response = self.client.post(url, data=data)
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

    def check_soft_cancel(self, trans_task_nums):
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
        self.client.headers.update(
            {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
        )
        response = self.client.post(url, data=data)

        if not response.text:
            self.login(username=self.username, password=self.password)
            response = self.client.post(url, data=data)
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

    def cancel_trans_tasks(self, trans_task_nums, cancel_type="0", cancel_reason="2"):
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
        response = self.client.post(url, data=data)

        if not response.text:
            self.login(username=self.username, password=self.password)
            response = self.client.post(url, data=data)
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

    def forceCancelTask(self, trans_task_nums: str):
        url = self.base_url + "/taskDispatch/cancelTask.action"
        data = {"clientCode": "", "tokenCode": "", "taskCode": trans_task_nums}
        self.client.headers.update(
            {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.base_url+"/taskDispatch/cms_index.action",
            }
        )

        response = self.client.post(url, json=data)
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

    def resumeAction(self, agvcode: str):
        url = self.base_url + "/taskDispatch/resumeAction.action"
        data = {"taskCode": "", "agvCode": agvcode, "subTaskNum": ""}
        self.client.headers.update(
            {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
            }
        )
        response = self.client.post(url, json=data)

        if not response.text:
            self.login(username=self.username, password=self.password)
            response = self.client.post(url, json=data)
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

    def freeagv(self, agvcode: str):
        url = self.base_url + "/agvControl/freeRobot.action"
        data = {"clientCode": "", "agvCode": agvcode}
        self.client.headers.update(
            {
                "Content-Type": "application/json",
                # "X-Requested-With": "XMLHttpRequest",
                "origin": cfg.get("rcms.host"),
                "referer": self.base_url+"/agvControl/cms_index.action",
            }
        )
        response = self.client.post(url, json=data)

        if not response.text:
            self.login(username=self.username, password=self.password)
            response = self.client.post(url, json=data)
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


if __name__ == "__main__":
    # 创建RCS Web API客户端实例
    rcs_web_api = RcsWebApi(
        username=cfg.get("rcms.username"),
        password=cfg.get("rcms.password"),
    )
    print(rcs_web_api.find_tasks_detail(robotCode=""))
    # 查询子任务详情示例
    # subtask_response = rcs_web_api.find_sub_tasks_detail(
    #     trans_task_num="MFAGV3002026011608201393195HS"
    # )
    # print("子任务详情:", subtask_response)

    # # 获取AGV状态示例
    # agv_status_response = rcs_web_api.get_agv_status(map_short_name="MOD2L30")
    # print("AGV状态:", agv_status_response)

    # 测试新实现的方法
    # task_num = "MFAGV3002026021003075913023HS"
    # print("测试检查任务滚动状态:")
    # print(rcs_web_api.check_is_rolling(task_num))
    #
    # print("测试检查开始传输任务:")
    # print(rcs_web_api.check_starting_trans_tasks(task_num))
    #
    # print("测试检查软取消任务:")
    # print(rcs_web_api.check_soft_cancel(task_num))
    #
    # print("测试取消传输任务:")
    # print(rcs_web_api.cancel_trans_tasks(task_num))


"""
curl 'http://172.18.2.72:8182/rcms/web/taskDispatch/cancelTask.action' \
  -H 'Accept: */*' \
  -H 'Accept-Language: zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7' \
  -H 'Connection: keep-alive' \
  -H 'Content-Type: application/json' \
  -b 'ecsRemeber=1%3Blll; HIK_COOKIE=19C8886B5A6PBHO; JSESSIONID=3E81C23CF3064D3F07AEF508CCDC8D1F' \
  -H 'DNT: 1' \
  -H 'Origin: http://172.18.2.72:8182' \
  -H 'Referer: http://172.18.2.72:8182/rcms/web/taskDispatch/cms_index.action' \
  -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36' \
  -H 'X-Requested-With: XMLHttpRequest' \
  --data-raw '{"clientCode":"","tokenCode":"","taskCode":"MFAGV300换辆车，然后给他封一下这儿突然充上电电着频率电量太低了。 2026022311390041840HS"}' \
  --insecure
"""
