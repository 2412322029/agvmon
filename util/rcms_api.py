import json
import os
import pathlib

import httpx
import xmltodict
from .config import cfg
from .dataparse import generate_map_image, parse_ShareMapInfo
from .helper import sharemap2json
import logging



logger = logging.getLogger(__name__)   


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
        self.mapdata = {}
        self.sharemapdata = ""
        self.maplinedata ={}
        self.maplist = None
        self.alarmtype = {}
        self.devicelist = {}
        self.displaytype = {}
        self.current_cache_path = cache_path / self.host.split("://")[1].replace(
            ".", "_"
        ).replace(":", "-")
        if not self.current_cache_path.exists():
            logger.info(f"创建缓存目录 {self.current_cache_path}")
            self.current_cache_path.mkdir()

    def cache_data(self):
        """
        持久化数据到文件
        """

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
            "mapdata",
        ]:
            with open(p / f"{k}.json", "w", encoding="utf-8") as f:
                json.dump(self.__dict__[k], f, indent=2, ensure_ascii=False)
        with open(p / "sharemapdata.xml", "w", encoding="utf-8") as f:
            f.write(self.sharemapdata)
        logger.info(f"数据已持久化到 {p}")

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
            result = xmltodict.parse(self.fake_data(method))
        else:
            url = f"{self.base_url}/{method}"
            data = {"elcMapCode": elc_map_code}
            response = self.client.post(url, json=data)
            response.raise_for_status()
            c = response.text
            result = xmltodict.parse(c)

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
            result = xmltodict.parse(self.fake_data(method))
        else:
            url = f"{self.base_url}/{method}"
            data = {"rcsCode": rcs_code}
            response = self.client.post(url, json=data)
            response.raise_for_status()
            c = response.text
            result = xmltodict.parse(c)

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
            result = xmltodict.parse(self.fake_data(method))
        else:
            url = f"{self.base_url}/{method}"
            response = self.client.get(url)
            response.raise_for_status()
            c = response.text
            result = xmltodict.parse(c)
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
            result = xmltodict.parse(self.fake_data(method))
        else:
            url = f"{self.base_url}/{method}"
            response = self.client.get(url)
            response.raise_for_status()
            c = response.text
            result = xmltodict.parse(c)

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
            result = xmltodict.parse(self.fake_data(method))
        else:
            url = f"{self.base_url}/{method}"
            response = self.client.get(url)
            response.raise_for_status()
            c = response.text
            result = xmltodict.parse(c)

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
            c = xmltodict.parse(self.fake_data(method))
        else:
            url = f"{self.base_url}/{method}"
            data = {"mapCode": map_code}
            response = self.client.post(url, json=data)
            response.raise_for_status()
            c = xmltodict.parse(response.text)

        self.mapdata = c["rows"]["row"]
        return method, c

    def get_line_info(self,map_code: str):
        method = "findByElcMapCode"
        c = ""
        if self.fake:
            with open(f"{fake_path}/{method}.json", "r", encoding="utf-8") as f:
                c = sharemap2json(json.load(f))
        else:
            url = f"{self.base_url}/{method}"
            payload = {"mapCode": map_code}
            response = self.client.post(url,data=payload)
            response.raise_for_status()
            c = sharemap2json(response.json())
        self.maplinedata = c
        return method, c

    def get_share_map_data_info(self, map_code: str, typen: int = 1):
        """
        获取共享地图数据信息
        :param map_code: 地图代码
        :param type: 共享类型，1为共享，2为非共享
        :return: 地图数据信息
        """
        method = "getShareMapInfoByMapCode"
        c = ""
        if self.fake:
            with open(f"{fake_path}/{method}.json", "r", encoding="utf-8") as f:
                c = sharemap2json(json.load(f))
        else:
            url = f"{self.base_url}/{method}"
            data = {"mapCode": map_code, "shareInfos": {"content": "", "type": typen}}
            response = self.client.post(url, json=data)
            response.raise_for_status()
            # print(response.json())
            c = sharemap2json(response.json())
        self.sharemapdata = c
        return method, c

    def get_rabbit_mq_param(self):
        """
        获取RabbitMQ参数
        :return: RabbitMQ参数
        """
        method = "getRabbitMqParam"
        c = ""
        if self.fake:
            result = xmltodict.parse(self.fake_data(method))
        else:
            url = f"{self.base_url}/{method}"
            response = self.client.get(url)
            response.raise_for_status()
            c = response.text
            result = xmltodict.parse(c)

        # 将结果存储到self.data
        self.rabbitmqdata = result["result"]
        return method, c

    def auto_set_dynamic_cfg(self):
        """
        自动设置动态配置，按照API依赖关系调用
        """
        logger.info("开始自动设置动态配置...")

        # 1. 先获取所有RCS列表
        logger.info("1. 获取所有RCS列表...")
        self.find_all_rcs_list()

        # 2. 从RCS列表中获取第一个RCS的code
        if isinstance(self.rcsdata, dict):
            self.rcsdata = [self.rcsdata]

        if self.rcsdata:
            rcs_code = self.rcsdata[0].get("code", "")
            logger.info(f"   使用RCS代码: {rcs_code}")

            # 3. 根据RCS代码获取地图列表
            logger.info("2. 根据RCS代码获取地图列表...")
            self.find_map_list_by_rcs_code(rcs_code)

            # 4. 从地图列表中获取第一个地图的code
            if isinstance(self.maplist, dict):
                self.maplist = [self.maplist]

            if self.maplist:
                map_code = self.maplist[0].get("code", "")
                logger.info(f"   使用地图代码: {map_code}")

                # 5. 根据地图代码获取设备列表
                logger.info("3. 根据地图代码获取设备列表...")
                self.find_device_list_by_elc_map_code(map_code)

                # 6. 获取地图数据信息
                logger.info("4. 获取地图数据信息...")
                self.get_map_data_info(map_code)

        # 7. 获取其他配置信息
        logger.info("5. 获取显示业务元素类型...")
        self.find_display_biz_ele_typ()

        logger.info("6. 获取报警类型列表...")
        self.find_alarm_typ_list()

        logger.info("7. 获取RabbitMQ参数...")
        self.get_rabbit_mq_param()

        # 8. 获取共享地图数据信息
        logger.info("8. 获取共享地图数据信息...")
        self.get_share_map_data_info(map_code)

        logger.info("自动设置动态配置完成！")

    def build_from_raw(self):
        """
        从原始数据构建API对象 并且缓存
        cache_data()
        """
        self.auto_set_dynamic_cfg()
        self.cache_data()

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
            "mapdata",
        ]:
            file_path = self.current_cache_path / f"{d}.json"
            if not file_path.exists():
                logger.warning(f"缓存文件不存在: {file_path}")
                continue

            with open(file_path, "r", encoding="utf-8") as f:
                setattr(self, d, json.load(f))
        map_data_path = self.current_cache_path / "sharemapdata.xml"
        if map_data_path.exists():
            with open(map_data_path, "r", encoding="utf-8") as f:
                self.sharemapdata = f.read()
        else:
            logger.warning(f"地图数据缓存文件不存在: {map_data_path}")

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
            self.get_share_map_data_info,
        ]
        for method in methods:
            n, content = method()
            with open(f"{fake_path}/{n}.xml", "w", encoding="utf-8") as f:
                f.write(content)
                logger.info(f"已生成模拟数据: {n}")

    def genmapimage(self):
        """
        生成地图图片
        """
        try:
            # Parse the XML content
            json_result = parse_ShareMapInfo(self.sharemapdata)
            logger.info("Parse successful!")

            # Generate and save both PNG and SVG images
            logger.info("Generating map images...")

            # Generate PNG image
            map_image = generate_map_image(
                json_result, desired_width=1600, show_labels=True
            )
            png_path = self.current_cache_path / "map_image.png"
            map_image.save(png_path)
            logger.info(f"PNG image saved to {png_path}")
            logger.info(
                f"PNG dimensions: {map_image.size[0]} x {map_image.size[1]} pixels"
            )

            # Generate SVG image
            svg_path = self.current_cache_path / "map_image.svg"
            map_image = generate_map_image(
                json_result,
                desired_width=1600,
                show_labels=True,
                export_svg=True,
                svg_filename=svg_path,
            )

        except Exception as e:
            logger.error(f"Error: {e}")
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    api = RcmsApi()
    api.build_from_raw()

    # api.build_from_cache()
    api.genmapimage()
