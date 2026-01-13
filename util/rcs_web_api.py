from hashlib import md5

import httpx
from config import cfg


class RcsWebApi:
    """
    RCS Web API客户端类，用于与RCS系统进行交互
    """

    def __init__(
        self, base_url=cfg.get("rcms.host") + "/rcms/web", username=None, password=None
    ):
        """
        初始化RCS Web API客户端

        参数:
            base_url: RCS系统的基础URL
        """
        self.base_url = base_url
        self.client = httpx.Client(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }
        )
        self.login(username, password)

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
            temp.append(f"{k}={v}")
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
        url = self.base_url + "/login/login.action"
        data = {
            "ecsUserName": username,
            "ecsPassword": md5(password.encode("utf-8")).hexdigest(),
            "pwdSafeLevelLogin": pwd_safe_level,
        }

        response = self.client.post(
            url,
            data=self._dict_to_formdata(data),
        )
        if response.status_code != 200:
            raise Exception(
                f"登录失败，状态码：{response.status_code}，响应内容：{response.text}"
            )
        if response.json().get("success") != True:
            raise Exception(f"登录失败，响应内容：{response.json()}")
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
            data=self._dict_to_formdata(data),
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


# 示例用法（如果直接运行此文件）
if __name__ == "__main__":
    # 创建RCS Web API客户端实例
    rcs_api = RcsWebApi(
        username="lll",
        password="Hik@123++",
    )

    # 查询子任务详情示例
    subtask_response = rcs_api.find_sub_tasks_detail(
        trans_task_num="MFAGV3002026011208003876632HS"
    )
    print("子任务详情:", subtask_response)

    # 获取AGV状态示例
    agv_status_response = rcs_api.get_agv_status(map_short_name="MOD2L30")
    print("AGV状态:", agv_status_response)
