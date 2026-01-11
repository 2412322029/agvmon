import json
import os
import pathlib

import httpx
from config import cfg
from dataparse import xml2json

fake_path = pathlib.Path(os.path.join(os.path.dirname(__file__), "data/fake"))
if not fake_path.exists():
    fake_path.mkdir()
cache_path = pathlib.Path(os.path.join(os.path.dirname(__file__), "data/cache"))
if not cache_path.exists():
    cache_path.mkdir()


class RcmsApi:
    def __init__(self, host: str = cfg.get("rcms.host"), fake: bool = cfg.get("fake")):
        self.host = host
        self.base_url = f"{self.host}/rcms/services/rest/clientService"
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        self.client = httpx.Client(
            headers={"Content-Type": "application/json", "User-Agent": self.user_agent}
        )
        self.fake = fake
        self.rcsdata = {}
        self.rabbitmqdata = {}
        self.mapdata = ""
        self.maplist = None
        self.alarmtype = {}
        self.devicelist = {}
        self.displaytype = {}
        self.current_cache_path = cache_path / self.host.split("://")[1].replace(
            ".", "_"
        ).replace(":", "-")
        if not self.current_cache_path.exists():
            self.current_cache_path.mkdir()

    def persist_data(self):
        """
        持久化数据到文件
        """
        import json

        p = self.current_cache_path
        if not p.exists():
            p.mkdir()
        for k in [
            "alarmtype",
            "devicelist",
            "displaytype",
            "rabbitmqdata",
            "rcsdata",
            "maplist",
        ]:
            with open(p / f"{k}.json", "w", encoding="utf-8") as f:
                json.dump(self.__dict__[k], f, indent=2, ensure_ascii=False)
        with open(p / "mapdata.xml", "w", encoding="utf-8") as f:
            f.write(self.mapdata)

    def close(self):
        """关闭httpx客户端"""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def find_device_list_by_elc_map_code(self, elc_map_code: str):
        """
        根据电子地图代码查找设备列表
        :param elc_map_code: 电子地图代码
        :return: 设备列表
        """
        method = "findDeviceListByElcMapCode"
        c = ""
        if self.fake:
            result = xml2json(self.fake_data(method))
        else:
            url = f"{self.base_url}/{method}"
            data = {"elcMapCode": elc_map_code}
            response = self.client.post(url, json=data)
            response.raise_for_status()
            c = response.text
            result = xml2json(c)

        # 将结果存储到self.data
        self.devicelist = result["rows"]["row"]
        return method, c

    def find_map_list_by_rcs_code(self, rcs_code: str):
        """
        根据RCS代码查找地图列表
        :param rcs_code: RCS代码
        :return: 地图列表
        """
        method = "findMapListByRcsCode"
        c = ""
        if self.fake:
            result = xml2json(self.fake_data(method))
        else:
            url = f"{self.base_url}/{method}"
            data = {"rcsCode": rcs_code}
            response = self.client.post(url, json=data)
            response.raise_for_status()
            c = response.text
            result = xml2json(c)

        # 将结果存储到self.data
        self.maplist = result["rows"]["row"]
        return method, c

    def find_all_rcs_list(self):
        """
        查找所有RCS列表
        :return: RCS列表
        """
        method = "findAllRcsList"
        c = ""
        if self.fake:
            result = xml2json(self.fake_data(method))
        else:
            url = f"{self.base_url}/{method}"
            response = self.client.get(url)
            response.raise_for_status()
            c = response.text
            result = xml2json(c)
        # 将结果存储到self.data
        self.rcsdata = result["rows"]["row"]
        return method, c

    def find_display_biz_ele_typ(self):
        """
        查找显示业务元素类型
        :return: 业务元素类型列表
        """
        method = "findDisplayBizEleTyp"
        c = ""
        if self.fake:
            result = xml2json(self.fake_data(method))
        else:
            url = f"{self.base_url}/{method}"
            response = self.client.get(url)
            response.raise_for_status()
            c = response.text
            result = xml2json(c)

        # 将结果存储到self.data
        self.displaytype = result["MapEleTyps"]["MapEleTyp"]
        return method, c

    def find_alarm_typ_list(self):
        """
        查找报警类型列表
        :return: 报警类型列表
        """
        method = "findAlarmTypList"
        c = ""
        if self.fake:
            result = xml2json(self.fake_data(method))
        else:
            url = f"{self.base_url}/{method}"
            response = self.client.get(url)
            response.raise_for_status()
            c = response.text
            result = xml2json(c)

        # 将结果存储到self.data
        self.alarmtype = result["rows"]["row"]
        return method, c

    def get_map_data_info(self, map_code: str):
        """
        获取地图数据信息
        :param map_code: 地图代码
        :return: 地图数据信息
        """
        method = "getMapDataInfo"
        c = ""
        if self.fake:
            c = self.fake_data(method)
        else:
            url = f"{self.base_url}/{method}"
            data = {"mapCode": map_code}
            response = self.client.post(url, json=data)
            response.raise_for_status()
            c = response.text
        self.mapdata = c
        return method, c

    def get_rabbit_mq_param(self):
        """
        获取RabbitMQ参数
        :return: RabbitMQ参数
        """
        method = "getRabbitMqParam"
        c = ""
        if self.fake:
            result = xml2json(self.fake_data(method))
        else:
            url = f"{self.base_url}/{method}"
            response = self.client.get(url)
            response.raise_for_status()
            c = response.text
            result = xml2json(c)

        # 将结果存储到self.data
        self.rabbitmqdata = result["result"]
        return method, c

    def auto_set_dynamic_cfg(self):
        """
        自动设置动态配置，按照API依赖关系调用
        """
        print("开始自动设置动态配置...")

        # 1. 先获取所有RCS列表
        print("1. 获取所有RCS列表...")
        self.find_all_rcs_list()

        # 2. 从RCS列表中获取第一个RCS的code
        if isinstance(self.rcsdata, dict):
            self.rcsdata = [self.rcsdata]

        if self.rcsdata:
            rcs_code = self.rcsdata[0].get("code", "")
            print(f"   使用RCS代码: {rcs_code}")

            # 3. 根据RCS代码获取地图列表
            print("2. 根据RCS代码获取地图列表...")
            self.find_map_list_by_rcs_code(rcs_code)

            # 4. 从地图列表中获取第一个地图的code
            if isinstance(self.maplist, dict):
                self.maplist = [self.maplist]

            if self.maplist:
                map_code = self.maplist[0].get("code", "")
                print(f"   使用地图代码: {map_code}")

                # 5. 根据地图代码获取设备列表
                print("3. 根据地图代码获取设备列表...")
                self.find_device_list_by_elc_map_code(map_code)

                # 6. 获取地图数据信息
                print("4. 获取地图数据信息...")
                self.get_map_data_info(map_code)

        # 7. 获取其他配置信息
        print("5. 获取显示业务元素类型...")
        self.find_display_biz_ele_typ()

        print("6. 获取报警类型列表...")
        self.find_alarm_typ_list()

        print("7. 获取RabbitMQ参数...")
        self.get_rabbit_mq_param()

        print("自动设置动态配置完成！")

    def build_from_remote(self):
        """
        构建API对象
        """
        self.auto_set_dynamic_cfg()
        self.persist_data()

    def build_from_cache(self):
        """
        从缓存数据构建API对象
        """
        for d in [
            "rcsdata",
            "maplist",
            "devicelist",
            "displaytype",
            "alarmtype",
            "rabbitmqdata",
        ]:
            file_path = self.current_cache_path / f"{d}.json"
            if not file_path.exists():
                print(f"缓存文件不存在: {file_path}")
                continue

            with open(file_path, "r", encoding="utf-8") as f:
                setattr(self, d, json.load(f))
        map_data_path = self.current_cache_path / "mapdata.xml"
        if map_data_path.exists():
            with open(map_data_path, "r", encoding="utf-8") as f:
                self.mapdata = f.read()
        else:
            print(f"地图数据缓存文件不存在: {map_data_path}")

    def fake_data(self, method: str):
        """
        :param method: 方法名
        :return: 模拟数据
        """
        with open(f"{fake_path}/{method}.xml", "r", encoding="utf-8") as f:
            xml_content = f.read()
        return xml_content

    def make_fake_data(self):
        """
        生成模拟数据
        """

        self.fake = False
        methods = [
            self.find_all_rcs_list,
            self.find_map_list_by_rcs_code,
            self.find_device_list_by_elc_map_code,
            self.find_display_biz_ele_typ,
            self.find_alarm_typ_list,
            self.get_map_data_info,
            self.get_rabbit_mq_param,
        ]
        for method in methods:
            n, content = method()
            with open(f"{fake_path}/{n}.xml", "w", encoding="utf-8") as f:
                f.write(content)
                print(f"已生成模拟数据: {n}")


# 测试代码
if __name__ == "__main__":
    api = RcmsApi(fake=True)
    api.build_from_cache()
    print(api.rcsdata)
