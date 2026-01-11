import xml.etree.ElementTree as ET


def sharemap2json(sharemap_info):
    content = sharemap_info["shareInfos"][0]["content"]
    root = ET.fromstring(content)
    return ET.tostring(root, encoding="utf-8").decode("utf-8")
