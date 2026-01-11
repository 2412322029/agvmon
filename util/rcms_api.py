
import httpx


class RcmsApi:
    def __init__(self, host: str = "http://172.18.2.72:8182"):
        self.host = host
        self.base_url = f"{self.host}/rcms/services/rest/clientService"
        self.client = httpx.Client(headers={"Content-Type": "application/json"})
    
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
        url = f"{self.base_url}/findDeviceListByElcMapCode"
        data = {"elcMapCode": elc_map_code}
        response = self.client.post(url, json=data)
        response.raise_for_status()
        return response.text
    
    def find_map_list_by_rcs_code(self, rcs_code: str):
        """
        根据RCS代码查找地图列表
        :param rcs_code: RCS代码
        :return: 地图列表
        """
        url = f"{self.base_url}/findMapListByRcsCode"
        data = {"rcsCode": rcs_code}
        response = self.client.post(url, json=data)
        response.raise_for_status()
        return response.text
    
    def find_all_rcs_list(self):
        """
        查找所有RCS列表
        :return: RCS列表
        """
        url = f"{self.base_url}/findAllRcsList"
        response = self.client.get(url)
        response.raise_for_status()
        return response.text
    
    def find_display_biz_ele_typ(self):
        """
        查找显示业务元素类型
        :return: 业务元素类型列表
        """
        url = f"{self.base_url}/findDisplayBizEleTyp"
        response = self.client.get(url)
        response.raise_for_status()
        return response.text
    
    def find_alarm_typ_list(self):
        """
        查找报警类型列表
        :return: 报警类型列表
        """
        url = f"{self.base_url}/findAlarmTypList"
        response = self.client.get(url)
        response.raise_for_status()
        return response.text
    
    def get_map_data_info(self, map_code: str):
        """
        获取地图数据信息
        :param map_code: 地图代码
        :return: 地图数据信息
        """
        url = f"{self.base_url}/getMapDataInfo"
        data = {"mapCode": map_code}
        response = self.client.post(url, json=data)
        response.raise_for_status()
        return response.text
    
    def get_rabbit_mq_param(self):
        """
        获取RabbitMQ参数
        :return: RabbitMQ参数
        """
        url = f"{self.base_url}/getRabbitMqParam"
        response = self.client.get(url)
        response.raise_for_status()
        return response.text

def save(name,c):
    with open("data/fake/"+name+".xml", "w", encoding="utf-8") as f:
        f.write(c)


# 测试代码
if __name__ == "__main__":
    try:
        api = RcmsApi()
        
        # 测试find_all_rcs_list
        print("测试find_all_rcs_list...")
        result = api.find_all_rcs_list()
        save("find_all_rcs_list",result)
        print("\n" + "="*50 + "\n")
        
        # 测试find_display_biz_ele_typ
        print("测试find_display_biz_ele_typ...")
        result = api.find_display_biz_ele_typ()
        save("find_display_biz_ele_type",result)
        print("\n" + "="*50 + "\n")
        
        # 测试find_alarm_typ_list
        print("测试find_alarm_typ_list...")
        result = api.find_alarm_typ_list()
        save("find_alarm_typ_list",result)
        print("\n" + "="*50 + "\n")
        
        # 测试get_rabbit_mq_param
        print("测试get_rabbit_mq_param...")
        result = api.get_rabbit_mq_param()
        save("get_rabbit_mq_param",result)
        print("\n" + "="*50 + "\n")
        
        # 测试find_map_list_by_rcs_code
        print("测试find_map_list_by_rcs_code...")
        result = api.find_map_list_by_rcs_code("123ABCD01AB01AB")
        save("find_map_list_by_rcs_code",result)
        print("\n" + "="*50 + "\n")
        
        # 测试find_device_list_by_elc_map_code
        print("测试find_device_list_by_elc_map_code...")
        result = api.find_device_list_by_elc_map_code("AA")
        save("find_device_list_by_elc_map_code",result)
        print("\n" + "="*50 + "\n")
        
        #测试get_map_data_info
        print("测试get_map_data_info...")
        result = api.get_map_data_info("AA")
        save("get_map_data_info",result)
        print("\n" + "="*50 + "\n")
        
    except Exception as e:
        print(f"错误: {e}")
    finally:
        if 'api' in locals():
            api.close()
