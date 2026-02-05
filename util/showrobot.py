import io
import json
import time

from colorama import Fore, Style, init

from .config import cfg, r

# 初始化colorama
init(autoreset=True)

rdstag = cfg.get("rcms.host").split("://")[1].replace(":", "-")


def get_display_width(text):
    """计算文本的显示宽度，中文占2个字符，英文和特殊符号（如⚡）占1个字符"""
    width = 0
    for char in text:
        # 闪电符号⚡和其他ASCII字符占1个字符宽度
        if ord(char) <= 127:
            width += 1  # ASCII字符和特殊符号
        elif char == "⚡":
            width += 2  # 充电中图标
        else:
            width += 2  # 中文等非ASCII字符
    return width


def align_text(text, width):
    """根据显示宽度对齐文本"""
    text_width = get_display_width(text)
    if text_width < width:
        padding = width - text_width
        return text + " " * padding
    return text


def show_robot_status(interval=0.1):
    # 初始化进度条变量
    position = 0
    direction = 1
    bar_length = 27
    slider_width = 5

    try:
        # 禁用终端滚动
        print("\033[?7l", end="", flush=True)

        while True:
            # 创建缓冲区
            buffer = io.StringIO()

            # 清空整个屏幕和滚动区域
            buffer.write("\033[2J\033[3J\033[H")
            # 创建进度条
            left = "░" * position
            slider = "█" * slider_width
            right = "░" * (bar_length - position - slider_width)
            bar = left + slider + right
            buffer.write(
                f"time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}   "
                f"{Fore.GREEN}|{bar}|{Style.RESET_ALL}"
                f"{1 / interval:.2f} Hz\n"
            )
            # 获取机器人状态输出
            robot_output = print_robot_status()
            buffer.write(robot_output)
            # 一次性显示所有内容
            print(buffer.getvalue(), end="", flush=True)
            buffer.close()

            # 更新滑块位置
            position += direction
            # 当滑块到达边界时改变方向
            if position + slider_width >= bar_length:
                direction = -1
                position = bar_length - slider_width
            elif position <= 0:
                direction = 1
                position = 0

            time.sleep(interval)
    except KeyboardInterrupt:
        # 清除进度条
        print("\n已取消")


def print_robot_status():
    """显示机器人的状态"""
    robot_status = r.hgetall(f"{rdstag}:ROBOT_STATUS")

    # 创建输出缓冲区
    output = io.StringIO()

    # 按robot_id排序
    sorted_robots = sorted(
        robot_status.items(), key=lambda x: int(x[0].decode("utf-8"))
    )

    # 打印表头（使用更清晰的列对齐）
    header = f"{Fore.CYAN}{align_text('设备编号', 10)} {align_text('状态', 6)} {align_text('设备任务', 22)} {align_text('电量', 8)} {align_text('时间差', 8)} {align_text('速度mm/s', 8)} {align_text('报警', 20)}{Style.RESET_ALL}\n"
    output.write(header)

    for robot_id, status_json in sorted_robots:
        status = json.loads(status_json.decode("utf-8"))
        robot_id_str = robot_id.decode("utf-8")

        # 确定显示状态
        display_status = "正常"
        if (
            status.get("abnormal")
            or int(status.get("status_code")) in [67, 61]
            or "异常" in status.get("status")
        ):
            display_status = "异常"
        elif status.get("stop"):
            display_status = "暂停"
        elif status.get("remove"):
            display_status = "排除"

        # 获取其他信息
        device_task = f"{status.get('status', '未知')}({status.get('status_code', '')})"
        alarm_text = f"{status.get('alarm', {}).get('main_name', '')};{status.get('alarm', {}).get('sub_name', '')}"
        battery = status.get("battery", "未知")
        speed = str("" if status.get("speed") == 0 else f"{status.get('speed', '')}")
        # 设置电量颜色和格式
        battery_str = f"{battery}%"
        if isinstance(battery, int):
            # 使用固定宽度的字符串格式化，考虑颜色代码的影响
            if battery > 80:
                battery_str = f"{Fore.GREEN}{battery:>3}%{Style.RESET_ALL}"
            elif 30 <= battery <= 80:
                battery_str = f"{Fore.YELLOW}{battery:>3}%{Style.RESET_ALL}"
            else:
                battery_str = f"{Fore.RED}{battery:>3}%{Style.RESET_ALL}"

        # 如果是充电中，电量后面加一个绿色闪电
        if "充电中" in status.get("status", ""):
            battery_str += f" {Fore.GREEN}⚡{Style.RESET_ALL}"

        # 计算时间差
        time_diff = ""  # 初始化时间差字符串
        current_time = time.time()

        # 确保time字段存在且为数值类型
        if "time" in status:
            try:
                status_time = float(status["time"])
                diff_seconds = int(current_time - status_time)

                # 确保时间差不为负
                diff_seconds = max(diff_seconds, 0)

                # 格式化时间差
                if diff_seconds < 60:
                    time_diff_str = f"{diff_seconds}秒前"
                elif diff_seconds < 3600:
                    minutes = diff_seconds // 60
                    time_diff_str = f"{minutes}分钟前"
                elif diff_seconds < 86400:
                    hours = diff_seconds // 3600
                    time_diff_str = f"{hours}小时前"
                else:
                    days = diff_seconds // 86400
                    time_diff_str = f"{days}天前"

                # 时间差超过10秒标红
                if diff_seconds > 10:
                    time_diff = f"{Fore.RED}{time_diff_str}{Style.RESET_ALL}"
                else:
                    time_diff = time_diff_str
            except (ValueError, TypeError):
                # 如果time字段格式不正确，使用当前时间作为默认值
                time_diff = "刚刚"
        else:
            # 如果没有time字段，使用当前时间作为默认值
            time_diff = "刚刚"

        # 构建输出行（使用更清晰的列对齐）
        line = f"{align_text(robot_id_str, 10)} {align_text(display_status, 6)} {align_text(device_task, 22)} {align_text(battery_str, 16)} {align_text(time_diff, 7)} {align_text(speed, 8)}  {alarm_text}\n"

        # 如果是异常状态，整行显示红色
        if display_status == "异常":
            output.write(f"{Fore.RED}{line}{Style.RESET_ALL}")
        elif status.get("remove") or display_status == "暂停":
            output.write(f"{Fore.YELLOW}{line}{Style.RESET_ALL}")
        else:
            output.write(line)

    # 获取输出内容
    content = output.getvalue()
    output.close()
    return content
