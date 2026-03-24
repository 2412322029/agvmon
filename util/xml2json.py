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
        result["#text"] = element.text.strip()

    return result


def safe_lxml_parse(xml_string, xml_file=None):
    """安全的 lxml 解析，返回类似 xmltodict 的字典"""
    if not xml_string and not xml_file:
        raise ValueError("Either xml_string or xml_file must be provided")
    elif xml_file:
        tree = etree.parse(xml_file, _SAFE_PARSER)
    else:
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
    <root>
        <item id="1">First</item>
        <item id="2">Second</item>
        <info>
            <name>Test</name>
            <value>123</value>
        </info>
    </root>
    """

    result = safe_lxml_parse(
        xml_string=xml_data,
    )
    print(result)
