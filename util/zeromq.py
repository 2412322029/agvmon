import json
import logging
import time

import redis
import xmltodict
import zmq

from .config import cfg
from .dataparse import Robot_msg_decode
from .rcms_api import RcmsApi

logger = logging.getLogger(__name__)
msg_dict = {
    "ROBOT_STATUS": 0,
    "ROBOT_PATH": 0,
    "TRP_BLOCK_CELL": 0,
    "TASK_INFO_REQ": 0,
    "CHARGE_INFO": 0,
    "BLOCK_CELL": 0,
    "VALID_ROBOT_NUM": 0,
}


class ZeroMQSubscriber:
    """ZeroMQ消息订阅者类"""

    def __init__(self, ip, port, message_port):
        """初始化订阅者"""
        try:
            self.ip = ip
            self.port = port
            self.message_port = message_port

            # 创建ZeroMQ上下文
            self.context = zmq.Context()
            # 创建SUB类型的套接字
            self.socket = self.context.socket(zmq.SUB)
            # 设置接收超时（可选）
            self.socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5秒超时
            # 连接到消息端口
            self.socket.connect(f"tcp://{self.ip}:{self.message_port}")
            logger.info(f"已尝试连接到消息服务器: tcp://{self.ip}:{self.message_port}")
        except zmq.ZMQError as e:
            logger.error(f"ZeroMQ初始化错误: {e}")
            raise
        except Exception as e:
            logger.error(f"订阅者初始化错误: {e}")
            raise

    def subscribe(self, topic=b""):
        """设置订阅主题
        topic: 订阅主题，默认订阅所有主题(b"")
        """
        try:
            # topic = b"\x02\x00\x00\x00\xb2\x02"
            self.socket.setsockopt(
                zmq.SUBSCRIBE,
                bytes(topic),
            )
            self.socket.setsockopt(zmq.CONFLATE, 1)
            self.socket.setsockopt(zmq.RCVHWM, 1)
            # self.socket.setsockopt(zmq.TCp,1)
            self.socket.setsockopt(zmq.RCVTIMEO, 200)
            logger.info(f"已订阅主题: {topic}")
        except zmq.ZMQError as e:
            logger.error(f"订阅主题错误: {e}")
            raise

    def receive_message(self):
        """接收单条消息

        Returns:
            tuple: message - 消息内容
        """
        try:
            message = self.socket.recv()
            # print(message[:72])
            # self.close()
            content = message[72:][:-3].decode("utf-8")
            return content
        except zmq.ZMQError as e:
            if e.errno == zmq.EAGAIN:  # 超时
                logger.debug("消息接收超时")
                return None
            logger.error(f"接收消息错误: {e}")
            raise
        except Exception as e:
            logger.error(f"消息处理错误: {e}")
            raise

    def run(self, callback=None, interval=0.01):
        """运行订阅者主循环

        Args:
            topic: 订阅主题
            callback: 消息处理回调函数，接收(topic, content)作为参数
        """
        self.subscribe()
        logger.info("ZeroMQ订阅者已启动，等待消息...")

        try:
            print(" | ".join(msg_dict.keys()))
            while True:
                content = self.receive_message()
                if content is not None:
                    content = xmltodict.parse(content)
                    if callback:
                        msg_type, j = Robot_msg_decode.parse(content)
                        # print(msg_type)
                        callback(msg_type, j)
                if interval:
                    time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("订阅者已停止")
        except Exception as e:
            logger.error(f"订阅者运行错误: {e}")
        finally:
            self.close()

    def close(self):
        """关闭订阅者连接"""
        try:
            self.socket.close()
            self.context.term()
            logger.info("订阅者连接已关闭")
        except zmq.ZMQError as e:
            logger.error(f"关闭连接错误: {e}")
        except Exception as e:
            logger.error(f"关闭订阅者错误: {e}")


def Map_info_update(api: RcmsApi, map_index: int = 0, interval: float = 0.01):
    """更新地图信息"""

    r = redis.Redis(**cfg.get("redis"))

    try:
        # api = RcmsApi()
        # api.build_from_cache()
        ZERO_MQ_IP = api.rcsdata[map_index].get("ip")
        ZERO_MQ_CTRL_PORT = api.rcsdata[map_index].get("zeroMqCtrlPort")
        ZERO_MQ_MESSAGE_PORT = api.rcsdata[map_index].get("zeroMqMessagePort")
        # 创建订阅者实例
        subscriber = ZeroMQSubscriber(
            ZERO_MQ_IP, ZERO_MQ_CTRL_PORT, ZERO_MQ_MESSAGE_PORT
        )
        rdstag = cfg.get("rcms.host").split("://")[1].replace(":", "-")
        message_count = 0
        def message_callback(msg_type, content):
            nonlocal message_count
            message_count += 1
            if str(message_count).endswith("00"):
                print(
                    f"{msg_dict.values()}{message_count} \r",
                    end="",
                    flush=True,
                )
            if msg_type == "ROBOT_STATUS" or msg_type == "ROBOT_PATH":
                r.hset(
                    f"{rdstag}:{msg_type}",
                    key=content.get("RobotId", "-1"),
                    value=json.dumps(content),
                )
            count = msg_dict.get(msg_type, 0)
            msg_dict.update({msg_type: count + 1})
            # elif (
            #     msg_type == "BLOCK_CELL"
            #     or msg_type == "CHARGE_INFO"
            #     or msg_type == "VALID_ROBOT_NUM"
            # ):
            #     r.set(f"{rdstag}:{msg_type}", value=json.dumps(content))
            # logger.info(f"收到{msg_type}消息: {content}")
            # elif msg_type == "BLOCK_CELL" or msg_type == "CHARGE_INFO" or msg_type == "VALID_ROBOT_NUM":
            #     r.hset(f"{rdstag}:{msg_type}", key=str(int(time.time())), value=json.dumps(content))

        subscriber.run(message_callback, interval=interval)
    except Exception as e:
        logger.error(f"主程序错误: {e}")
        exit(1)


def show_loading_bar(bar_length=30, slider_width=5, speed=0.08, stop_event=None):
    """显示无线流动加载进度条

    Args:
        bar_length: 进度条总长度
        slider_width: 流动滑块宽度
        speed: 滑块移动速度（秒）
        stop_event: 停止事件对象，用于控制加载条停止
    """
    position = 0
    direction = 1
    try:
        while not (stop_event and stop_event.is_set()):
            # 创建流动进度条字符串
            left = "░" * position
            slider = "█" * slider_width
            right = "░" * (bar_length - position - slider_width)
            bar = left + slider + right
            # 打印进度条
            print(f"|{bar}|\r", end="", flush=True)
            # 更新滑块位置
            position += direction
            # 当滑块到达边界时改变方向
            if position + slider_width >= bar_length:
                direction = -1
                position = bar_length - slider_width
            elif position <= 0:
                direction = 1
                position = 0
            time.sleep(speed)
        # 清除加载条
        if stop_event and stop_event.is_set():
            print(" " * (bar_length + 2) + "\r", end="", flush=True)
    except KeyboardInterrupt:
        print("\n已取消")


if __name__ == "__main__":
    show_loading_bar()
