import json
import logging
import os
import time
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


class Robot_msg_decode:
    @staticmethod
    def parse(json_data) -> (str, dict):
        """
        解析JSON数据，根据消息类型调用相应的解析方法

        参数:
        json_data (str或dict): 要解析的JSON数据

        返回:
        tuple: (消息类型, 解析后的字典)
        """
        try:
            data = json.loads(json_data) if isinstance(json_data, str) else json_data
            message = data.get("Message", {})
            msg_type = message.get("Type")

            if msg_type == "ROBOT_STATUS":
                return msg_type, Robot_msg_decode.parse_robot_status(message)
            else:
                return msg_type, message

        except Exception as e:
            logger.error(f"解析JSON数据失败: {e}")
            return msg_type, {}

    # 滚轮状态映射字典
    ROLLER_STATUS_MAP = {
        40000: "正常",
    }

    @staticmethod
    def pretty_print_robot_status(rsd: dict):
        if rsd.get("abnormal"):
            print(f"""设备编号 {rsd.get("robot_id"):<7} 设备任务: {rsd.get("status"):<18}  abnormal: {rsd.get("abnormal"):<8}  电量: {rsd.get("battery")}% alarm {rsd.get("alarm").get("main_name")};{rsd.get("alarm").get("sub_name")}""")
    
    @staticmethod
    def parse_robot_status(message):
        """解析ROBOT_STATUS类型的消息"""
        robot = message.get("Robot", {})
        pod = message.get("Pod", {})

        # 解析状态码
        status_code = int(robot.get("Status", -1))
        status_text, abnormal = AmrStatusType(status_code)
        # print(status_text)
        # 解析滚轮状态
        roller_status_code = int(robot.get("RollerStatus", 0))
        roller_status_text = Robot_msg_decode.ROLLER_STATUS_MAP.get(
            roller_status_code, roller_status_code
        )

        # 解析布尔字段
        stop = Robot_msg_decode._map_boolean(int(robot.get("Stop", 0)))
        stay = Robot_msg_decode._map_boolean(int(robot.get("Stay", 0)))
        remove = Robot_msg_decode._map_boolean(int(robot.get("Remove", 0)))
        change = Robot_msg_decode._map_boolean(int(robot.get("Change", 0)))

        return {
            "type": message.get("Type"),
            "map_code": message.get("MapCode"),
            "RobotId": robot.get("Id"),
            "ip": robot.get("IP"),
            "position": {
                "x": float(robot["Pos"].get("x", 0)) if robot.get("Pos") else 0,
                "y": float(robot["Pos"].get("y", 0)) if robot.get("Pos") else 0,
                "h": float(robot["Pos"].get("h", 0)) if robot.get("Pos") else 0,
            },
            "load_status": int(robot.get("LoadStatus", 0)),
            "forklift": {
                "fork_height": int(robot["Forklift"].get("ForkHeight", 0))
                if robot.get("Forklift")
                else 0,
                "load_status": int(robot["Forklift"].get("LoadStatus", 0))
                if robot.get("Forklift")
                else 0,
            },
            "direction": int(robot.get("Direction", 0)),
            "battery": int(robot.get("Battery", 0)),
            "speed": int(robot.get("Speed", 0)),
            "status": status_text,  # 使用映射后的状态文字
            "status_code": status_code,  # 保留原始状态码
            "abnormal": abnormal,
            "alarm": AlarmType(f'{robot.get("AlarmMain", 0)}-{robot.get("AlarmSub", 0)}'),
            "stop": stop,  # 布尔值
            "stay": stay,  # 布尔值
            "tgt_distance": int(robot.get("TgtDistance", 0)),
            "remove": remove,  # 布尔值
            "change": change,  # 布尔值
            "version": robot.get("Version"),
            "roller_status": roller_status_text,  # 使用映射后的滚轮状态文字
            "roller_status_code": roller_status_code,  # 保留原始滚轮状态码
            "pod": {"id": pod.get("Id"), "bind": int(pod.get("Bind", 0))},
            "time":time.time()
        }

    def _map_boolean(value):
        """将0/1转换为false/true，其他值返回原始值"""
        if value == 0:
            return False
        elif value == 1:
            return True
        return value

def AlarmType(t: str):
    """
    根据告警代码映射告警信息

    参数:
        t: 告警类型代码（如"1-1"表示主控告警-相机未获取到导航数据）
    返回:
        dict: 包含告警名称、解决方案等信息的字典
    """
    try:
        # 解析告警类型代码，格式为"主类型-子类型"或单独的主类型
        if "-" in t:
            main_code, sub_code = t.split("-", 1)
        else:
            main_code, sub_code = t, None
        # 构建AmrStatusInfo.json文件路径
        file_path = os.path.join(os.path.dirname(__file__), "data", "AlarmInfo.json")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 查找主告警类型
        for main_alarm in data:
            if main_alarm.get("code") == main_code:
                main_name = main_alarm.get("name", "")

                # 如果没有子类型，返回主告警信息
                if not sub_code:
                    return {
                        "main_code": main_code,
                        "main_name": main_name,
                        "sub_code": "",
                        "sub_name": "",
                        "solution": "",
                    }

                # 查找子告警类型
                for sub_alarm in main_alarm.get("alarmTpeVO", []):
                    if sub_alarm.get("code") == sub_code:
                        return {
                            "main_code": main_code,
                            "main_name": main_name,
                            "sub_code": sub_code,
                            "sub_name": sub_alarm.get("name", ""),
                            "solution": sub_alarm.get("solution", ""),
                        }

        # 如果未找到匹配的告警类型
        return {
            "main_code": main_code,
            "main_name": "",
            "sub_code": sub_code or "",
            "sub_name": "",
            "solution": "",
        }
    except Exception as e:
        return {
            "main_code": "",
            "main_name": "",
            "sub_code": "",
            "sub_name": "",
            "solution": "",
        }
def AmrStatusType(t: str):
    """
    根据机器人状态代码查询状态名称和异常标识

    参数:
        t: 机器人状态代码（如"1"表示任务完成）

    返回:
        dict: 包含状态名称和异常标识的字典
    """

    # 构建AmrStatusInfo.json文件路径
    file_path = os.path.join(os.path.dirname(__file__), "data", "AmrStatusInfo.json")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 获取状态列表
        status_list = data.get("data", [])

        # 查找匹配的状态
        for status in status_list:
            if status.get("code") == str(t) and status.get("type") == "1":
                return status.get("name", "-"),bool(int(status.get("abnormal", False)))
                

        # 如果未找到匹配的状态
        return f"未知状态({t})", False
    except Exception:
        return f"未知状态({t})", False


def parse_mapxml(content):
    root = ET.fromstring(content)
    map_data = []
    for row in root.findall(".//row"):
        cooX = float(row.find("cooX").text)
        cooY = float(row.find("cooY").text)
        # 获取macName属性（如果存在）
        macName_elem = row.find("macName")
        macName = macName_elem.text if macName_elem is not None else ""
        if macName:
            map_data.append({"x": cooX, "y": cooY, "macName": macName})
        else:
            map_data.append({"x": cooX, "y": cooY})
    return map_data


def parse_ShareMapInfo(j):
    root = ET.fromstring(j)
    map_data = {"map_ret_list": [], "ret_name_list": []}

    # 遍历所有MapRet元素
    for map_ret in root.findall(".//MapRet"):
        # 提取所有Point坐标
        points = []
        for point in map_ret.findall(".//Point"):
            xpos = int(point.get("xpos"))
            ypos = int(point.get("ypos"))
            points.append({"xpos": xpos, "ypos": ypos})

        # 提取Area颜色属性
        area = map_ret.find(".//Area")
        area_data = {
            "color_a": int(area.get("color_a")),
            "color_r": int(area.get("color_r")),
            "color_g": int(area.get("color_g")),
            "color_b": int(area.get("color_b")),
        }

        # 添加MapRet数据到列表
        map_data["map_ret_list"].append({"points": points, "area": area_data})

    # 遍历所有RetName元素
    for ret_name in root.findall(".//RetName"):
        # 提取RetName属性
        ret_name_data = {
            "start_x": int(ret_name.get("start_x")),
            "start_y": int(ret_name.get("start_y")),
            "end_x": int(ret_name.get("end_x")),
            "end_y": int(ret_name.get("end_y")),
            "size": float(ret_name.get("size")),
            "font": ret_name.get("font"),
            "font_color_a": int(ret_name.get("font_color_a")),
            "font_color_r": int(ret_name.get("font_color_r")),
            "font_color_g": int(ret_name.get("font_color_g")),
            "font_color_b": int(ret_name.get("font_color_b")),
            "text": ret_name.text.strip() if ret_name.text else "",
        }

        # 添加RetName数据到列表
        map_data["ret_name_list"].append(ret_name_data)

    # 转换为JSON并返回，保持非ASCII字符不转义
    return json.dumps(map_data, indent=2, ensure_ascii=False)


# 从ShareMapInfo数据生成地图图像的函数
def generate_map_image(
    share_map_json,
    desired_width=1200,
    show_labels=True,
    border_padding=50,
    export_svg=False,
    svg_filename=None,
    font_scale=0.3,
    compile_scale=1.0,
):
    """
    从提供的ShareMapInfo JSON数据生成地图图像。

    参数:
        share_map_json: parse_ShareMapInfo返回的包含地图数据的JSON字符串
        desired_width: 输出图像的宽度（像素），默认1200以获得更高分辨率
        show_labels: 是否显示每个区域的文本标签
        border_padding: 地图周围的内边距，确保所有内容可见
        export_svg: 是否将地图导出为SVG矢量图像
        svg_filename: SVG导出的文件名（export_svg为True时必填）
        font_scale: 字体大小缩放因子，用于调整文本显示大小，默认0.5
        compile_scale: 编译缩放参数，用于整体缩放地图元素，默认1.0

    返回:
        PIL.Image: 生成的地图图像
    """
    # 解析JSON数据
    share_map_data = json.loads(share_map_json)

    # 提取所有坐标点（来自map_ret_list和ret_name_list）以确定坐标范围
    all_points = []
    for map_ret in share_map_data["map_ret_list"]:
        all_points.extend(map_ret["points"])

    # 添加ret_name_list中的坐标点，确保它们也在可见区域内
    if "ret_name_list" in share_map_data:
        for ret_name in share_map_data["ret_name_list"]:
            all_points.append(
                {"xpos": ret_name["start_x"], "ypos": ret_name["start_y"]}
            )
            all_points.append({"xpos": ret_name["end_x"], "ypos": ret_name["end_y"]})

    # 计算带内边距的坐标范围
    xs = [point["xpos"] for point in all_points]
    ys = [point["ypos"] for point in all_points]
    original_minX = min(xs)
    original_maxX = max(xs)
    original_minY = min(ys)
    original_maxY = max(ys)

    # 添加内边距以确保所有内容可见
    padding_x = (original_maxX - original_minX) * 0.05  # 每边5%的内边距
    padding_y = (original_maxY - original_minY) * 0.05
    minX = original_minX - padding_x
    maxX = original_maxX + padding_x
    minY = original_minY - padding_y
    maxY = original_maxY + padding_y

    # 计算坐标空间尺寸
    coord_width = maxX - minX
    coord_height = maxY - minY

    logger.info(f"找到 {len(share_map_data['map_ret_list'])} 个地图区域")
    logger.info(f"坐标范围: X({minX}, {maxX}), Y({minY}, {maxY})")
    logger.info(f"坐标空间尺寸: {coord_width} x {coord_height}")

    # 确定图像尺寸和缩放因子
    scale = desired_width / coord_width * compile_scale
    image_width = int(coord_width * scale)
    image_height = int(coord_height * scale)

    logger.info(f"图像尺寸: {image_width} x {image_height} 像素")
    logger.info(f"缩放因子: {scale:.4f}")

    # 将坐标转换为图像像素的辅助函数
    def coord_to_pixel(coord, min_val, max_val, image_size):
        # 将坐标归一化到[0, 1]范围
        normalized = (coord - min_val) / (max_val - min_val)
        # 缩放到图像尺寸
        return int(normalized * image_size)

    # 创建白色背景图像
    image = Image.new("RGB", (image_width, image_height), color="white")
    draw = ImageDraw.Draw(image)

    # 绘制所有地图区域（多边形）
    for map_ret in share_map_data["map_ret_list"]:
        points = map_ret["points"]
        area = map_ret["area"]

        # 将多边形坐标转换为像素坐标
        pixel_points = []
        for point in points:
            x = point["xpos"]
            y = point["ypos"]
            pixel_x = coord_to_pixel(x, minX, maxX, image_width - 1)
            pixel_y = image_height - coord_to_pixel(y, minY, maxY, image_height - 1)
            pixel_points.append((pixel_x, pixel_y))

        # 从区域数据创建颜色元组
        color = (area["color_r"], area["color_g"], area["color_b"], area["color_a"])

        # 绘制指定颜色的多边形（无边框）
        draw.polygon(pixel_points, fill=color[:3])  # 仅使用RGB值填充

    # 如果show_labels为True，绘制文本标签
    if show_labels and "ret_name_list" in share_map_data:
        # 初始化默认字体参数
        default_font_family = "simsun.ttc"
        default_font_size = 16

        # 尝试使用TrueType字体以获得更好的文本渲染效果
        try:
            # 尝试Windows系统字体
            font = ImageFont.truetype(default_font_family, default_font_size)
        except Exception:
            try:
                # 尝试另一种常用字体
                default_font_family = "arial.ttf"
                font = ImageFont.truetype(default_font_family, default_font_size)
            except Exception:
                # 回退到默认字体
                font = ImageFont.load_default()
                default_font_family = "default"

        for ret_name in share_map_data["ret_name_list"]:
            # 使用实际坐标点计算文本位置
            center_x = (ret_name["start_x"] + ret_name["end_x"]) / 2
            center_y = (ret_name["start_y"] + ret_name["end_y"]) / 2

            # 转换为像素坐标
            pixel_x = coord_to_pixel(center_x, minX, maxX, image_width)
            pixel_y = image_height - coord_to_pixel(center_y, minY, maxY, image_height)

            # 获取文本内容
            text = ret_name["text"]

            # 从ret_name数据获取字体属性
            font_family = ret_name.get("font", default_font_family)

            # 适当缩放字体大小，考虑地图尺寸和缩放因子
            base_font_size = ret_name["size"]

            # 基于地图整体尺寸的自适应缩放
            size_factor = (
                min(image_width, image_height) / 1000.0
            )  # 相对于1000像素尺寸的因子
            scaled_font_size = base_font_size * font_scale * compile_scale * size_factor

            # 根据文本长度调整字体大小，长文本使用稍小字体
            text_length_factor = max(
                0.7, min(1.0, 20.0 / max(len(text), 10))
            )  # 文本越长，因子越小
            scaled_font_size *= text_length_factor

            # 确保字体大小合理（不过小或过大）
            final_font_size = max(
                1, min(scaled_font_size, 100)
            )  # 限制在8到32像素之间，提供更灵活的范围

            # 使用正确的字体系列和大小创建字体
            current_font = font  # 默认使用回退字体
            try:
                # 尝试使用数据中指定的准确字体系列
                if font_family.lower() in ["microsoft yahei", "microsoft yahei ui"]:
                    # 特殊处理Microsoft YaHei，它可能有不同的字体文件名
                    possible_font_files = [
                        "msyh.ttc",
                        "msyhbd.ttc",
                        "msyhl.ttc",
                        "microsoft yahei.ttf",
                    ]
                    for font_file in possible_font_files:
                        try:
                            current_font = ImageFont.truetype(
                                font_file, int(final_font_size)
                            )
                            break
                        except Exception:
                            continue
                else:
                    # 直接尝试指定的字体系列
                    current_font = ImageFont.truetype(font_family, int(final_font_size))
            except Exception as e:
                # 如果指定的字体失败，尝试默认字体系列
                try:
                    current_font = ImageFont.truetype(
                        default_font_family, int(final_font_size)
                    )
                except Exception:
                    # 如果所有尝试都失败，回退到系统默认字体
                    current_font = ImageFont.load_default()

            # 将空格替换为换行符
            text_lines = text.split(" ")

            # 计算各行列的大小和文本总大小
            line_metrics = []  # 存储每行的宽度、高度和边界框

            for line in text_lines:
                try:
                    # 使用textbbox获取精确的文本边界框
                    bbox = draw.textbbox((0, 0), line, font=current_font)
                    width = bbox[2] - bbox[0]
                    height = bbox[3] - bbox[1]
                    ascent = abs(bbox[1])  # 从基线到顶部的距离
                    descent = bbox[3]  # 从基线到底部的距离
                    line_metrics.append((width, height, ascent, descent, bbox))
                except Exception:
                    # 回退计算
                    try:
                        width, height = draw.textsize(line, font=current_font)
                        ascent = height * 0.7  # 近似ascent
                        descent = height * 0.3  # 近似descent
                        line_metrics.append((width, height, ascent, descent, None))
                    except Exception:
                        # 完全回退
                        line_metrics.append(
                            (0, current_font.getsize("A")[1], 0, 0, None)
                        )

            # 计算文本总尺寸
            line_widths = [m[0] for m in line_metrics]
            line_ascent = [m[2] for m in line_metrics]
            line_descent = [m[3] for m in line_metrics]

            max_line_width = max(line_widths) if line_widths else 0
            total_ascent = max(line_ascent) if line_ascent else 0
            total_descent = max(line_descent) if line_descent else 0

            # 计算行高和行间距
            line_height = total_ascent + total_descent
            line_spacing = line_height * 0.2  # 行间距为行高的20%
            total_text_height = line_height + (len(text_lines) - 1) * (
                line_height + line_spacing
            )

            # 计算起始位置以居中整个文本块
            # 水平居中
            start_x = pixel_x - max_line_width // 2

            # 垂直居中，考虑文本的基线位置
            start_y = pixel_y - total_text_height // 2 + total_ascent

            # 分别绘制每行，控制行间距
            current_y = start_y
            font_color = (
                ret_name["font_color_r"],
                ret_name["font_color_g"],
                ret_name["font_color_b"],
            )

            for i, (line, metrics) in enumerate(zip(text_lines, line_metrics)):
                line_width, _, _, _, _ = metrics

                # 计算此行的水平居中位置，使用每行实际宽度
                line_x = pixel_x - line_width // 2

                # 绘制文本行
                draw.text((line_x, current_y), line, fill=font_color, font=current_font)

                # 为下一行移动位置，使用行高加行间距
                if i < len(text_lines) - 1:
                    current_y += line_height + line_spacing

            # 可选：绘制背景以提高文本可见性
            # text_bbox = draw.textbbox((0, 0), text, font=font)[2:]
            # draw.rectangle((pixel_x, pixel_y, pixel_x + text_bbox[0], pixel_y + text_bbox[1]),
            #                fill="white", outline="white")
            # draw.text((pixel_x, pixel_y), text, fill=font_color, font=font)

    # 如果需要，导出为SVG格式
    if export_svg:
        if not svg_filename:
            raise ValueError("当export_svg为True时，必须提供svg_filename")

        # 计算SVG尺寸（与图像尺寸相同）
        svg_width = image_width
        svg_height = image_height

        # 创建SVG内容
        svg_content = [
            f'<svg width="{svg_width}" height="{svg_height}" viewBox="0 0 {svg_width} {svg_height}" xmlns="http://www.w3.org/2000/svg">'
        ]
        svg_content.append('  <rect width="100%" height="100%" fill="white"/>')

        # 向SVG添加多边形
        for map_ret in share_map_data["map_ret_list"]:
            points = map_ret["points"]
            area = map_ret["area"]

            # 将多边形坐标转换为SVG坐标
            svg_points = []
            for point in points:
                x = point["xpos"]
                y = point["ypos"]
                pixel_x = coord_to_pixel(x, minX, maxX, image_width - 1)
                pixel_y = image_height - coord_to_pixel(y, minY, maxY, image_height - 1)
                svg_points.append(f"{pixel_x},{pixel_y}")

            # 从区域数据创建颜色
            color = (area["color_r"], area["color_g"], area["color_b"])
            color_hex = "#{:02x}{:02x}{:02x}".format(*color)

            # 向SVG添加多边形
            svg_content.append(
                f'  <polygon points="{" ".join(svg_points)}" fill="{color_hex}"/>'
            )

        # 向SVG添加文本标签
        if show_labels and "ret_name_list" in share_map_data:
            for ret_name in share_map_data["ret_name_list"]:
                # 计算文本位置
                center_x = (ret_name["start_x"] + ret_name["end_x"]) / 2
                center_y = (ret_name["start_y"] + ret_name["end_y"]) / 2

                # 转换为SVG坐标
                pixel_x = coord_to_pixel(center_x, minX, maxX, image_width)
                pixel_y = image_height - coord_to_pixel(
                    center_y, minY, maxY, image_height
                )

                # 获取文本内容
                text = ret_name["text"]

                # 获取字体颜色
                font_color = (
                    ret_name["font_color_r"],
                    ret_name["font_color_g"],
                    ret_name["font_color_b"],
                )
                font_color_hex = "#{:02x}{:02x}{:02x}".format(*font_color)

                # 将空格替换为换行符
                text_to_draw = text.replace(" ", "\n")

                # 向SVG添加文本，使用正确的字体系列和缩放大小
                font_family = ret_name.get("font", "Microsoft YaHei, Arial")
                base_font_size = ret_name["size"]

                # 使用与PNG相同的缩放逻辑
                size_factor = min(image_width, image_height) / 1000.0
                scaled_font_size = (
                    base_font_size * font_scale * compile_scale * size_factor
                )

                # 根据文本长度调整字体大小
                text_length_factor = max(0.7, min(1.0, 20.0 / max(len(text), 10)))
                scaled_font_size *= text_length_factor

                # 确保字体大小合理
                font_size = max(8, min(scaled_font_size, 32))

                # 创建SVG文本元素，设置适当的位置和换行
                svg_text = f'  <text x="{pixel_x}" y="{pixel_y}" text-anchor="middle" font-family="{font_family}, Arial" font-size="{font_size}" fill="{font_color_hex}" line-height="1.0">'

                # 为每行添加tspan元素，使用合适的行间距
                for i, line in enumerate(text_to_draw.split("\n")):
                    dy = (
                        f"{i * font_size * 0.7}" if i > 0 else "0"
                    )  # 行间距为字体大小的70%
                    svg_text += f'<tspan x="{pixel_x}" dy="{dy}">{line}</tspan>'

                svg_text += "</text>"
                svg_content.append(svg_text)

        # 关闭SVG标签
        svg_content.append("</svg>")

        # 将SVG写入文件
        with open(svg_filename, "w", encoding="utf-8") as f:
            f.write("\n".join(svg_content))

        logger.info(f"SVG矢量图像已保存到 {svg_filename}")

    return image

# print(AmrStatusType(246))