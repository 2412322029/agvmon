import io

from lxml import etree

_SAFE_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    remove_comments=True,
    dtd_validation=False,
    load_dtd=False,
)


def lxml_to_dict_simple(element):
    """将 lxml 元素转换为字典（简化版）"""
    result = {}

    # 处理属性
    if element.attrib:
        for key, value in element.attrib.items():
            result[f"@{key}"] = value

    # 处理子元素
    children = list(element)
    if children:
        for child in children:
            child_dict = lxml_to_dict_simple(child)
            tag = child.tag

            if tag in result:
                # 处理重复元素
                if not isinstance(result[tag], list):
                    result[tag] = [result[tag]]
                result[tag].append(child_dict)
            else:
                result[tag] = child_dict
    elif element.text and element.text.strip():
        # 文本内容
        result = element.text.strip()

    return result


def safe_lxml_parse(xml_string, xml_file=None):
    """安全的 lxml 解析，返回类似 xmltodict 的字典"""
    if not xml_string and not xml_file:
        raise ValueError("Either xml_string or xml_file must be provided")
    elif xml_file:
        tree = etree.parse(xml_file, _SAFE_PARSER)
    else:
        if isinstance(xml_string, str):
            xml_string = xml_string.lstrip()
        tree = etree.parse(
            io.BytesIO(
                xml_string.encode() if isinstance(xml_string, str) else xml_string
            ),
            _SAFE_PARSER,
        )

    root = tree.getroot()
    return {root.tag: lxml_to_dict_simple(root)}


if __name__ == "__main__":
    # 使用示例
    xml_data = """
    <?xml version="1.0" encoding="UTF-8" ?>
<RobotTypes>
    <Robot>1</Robot>
    <RobotType Type="0" Offline="offline.png" Online="online.png" Abnormal="alarm.png"/>
	<RobotType Type="1" Offline="offline.png" Online="online.png" Abnormal="alarm.png"/>
	<RobotType Type="2" Offline="offline.png" Online="online.png" Abnormal="alarm.png"/>
	<RobotType Type="3" Offline="offline.png" Online="online.png" Abnormal="alarm.png"/>
	<RobotType Type="4" Offline="offline.png" Online="online.png" Abnormal="alarm.png"/>
	<RobotType Type="5" Offline="offline.png" Online="online.png" Abnormal="alarm.png"/>
	<RobotType Type="30" Offline="fork_offline.png" Online="fork_online.png" Abnormal="fork_alarm.png"/>
	<RobotType Type="32" Offline="offline.png" Online="online.png" Abnormal="alarm.png"/>
	<RobotType Type="33" Offline="fork_offline.png" Online="fork_online.png" Abnormal="fork_alarm.png"/>
	<RobotType Type="34" Offline="fork_offline.png" Online="fork_online.png" Abnormal="fork_alarm.png"/>
	<RobotType Type="40" Offline="offline.png" Online="online.png" Abnormal="alarm.png"/>
	<RobotType Type="48" Offline="AMR_offline.png" Online="AMR_normal.png" Abnormal="AMR_alarm.png"/>
    <RobotType Type="60" Offline="tractor_offline.png" Online="tractor_online.png" Abnormal="tractor_alarm.png"/>
	<RobotType Type="70" Offline="ClampUnwind_offline.png" Online="ClampUnwind.png" Abnormal="ClampUnwind_alarm.png"/>
	<RobotType Type="5000" Offline="rcs5000_offline.png" Online="rcs5000_online.png" Abnormal="rcs5000_alarm.png"/>
</RobotTypes>
    """
    result = safe_lxml_parse(
            xml_string=xml_data,
        )
    print(result)
    # import time
    # import tracemalloc

    # import xmltodict

    # start_time = time.perf_counter()
    # tracemalloc.start()
    # for i in range(1000):
    #     result = safe_lxml_parse(
    #         xml_string=xml_data,
    #     )
    # current, peak = tracemalloc.get_traced_memory()
    # tracemalloc.stop()
    # print(f"safe_lxml_parse 解析时间: {time.perf_counter() - start_time} 秒")
    # print(f"safe_lxml_parse 当前内存: {current / 1024 / 1024:.2f} MB, 峰值: {peak / 1024 / 1024:.2f} MB")

    # start_time = time.perf_counter()
    # tracemalloc.start()
    # for i in range(1000):
    #     result2 = xmltodict.parse(xml_data.strip())
    # current, peak = tracemalloc.get_traced_memory()
    # tracemalloc.stop()
    # print(f"xmltodict 解析时间: {time.perf_counter() - start_time} 秒")
    # print(f"xmltodict 当前内存: {current / 1024 / 1024:.2f} MB, 峰值: {peak / 1024 / 1024:.2f} MB")
    # print(result==result2)
