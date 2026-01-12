import time
import traceback

import xmltodict
import zmq
from logger import logger
from rcms_api import RcmsApi

logger = logger.getChild("zeromq")


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
            self.socket.connect(f"tcp://{ZERO_MQ_IP}:{ZERO_MQ_MESSAGE_PORT}")
            logger.info(
                f"已连接到消息服务器: tcp://{ZERO_MQ_IP}:{ZERO_MQ_MESSAGE_PORT}"
            )
        except zmq.ZMQError as e:
            logger.error(f"ZeroMQ初始化错误: {e}")
            raise
        except Exception as e:
            logger.error(f"订阅者初始化错误: {e}")
            raise

    def subscribe(self, topic=b""):
        """设置订阅主题

        Args:
            topic: 订阅主题，默认订阅所有主题(b"")
        """
        try:
            self.socket.setsockopt_string(
                zmq.SUBSCRIBE,
                topic.decode("utf-8") if isinstance(topic, bytes) else topic,
            )
            topic_str = topic if isinstance(topic, str) else topic.decode("utf-8")
            logger.info(f"已订阅主题: {topic_str}")
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

    def run(self, callback=None):
        """运行订阅者主循环

        Args:
            topic: 订阅主题
            callback: 消息处理回调函数，接收(topic, content)作为参数
        """
        self.subscribe()
        logger.info("ZeroMQ订阅者已启动，等待消息...")

        try:
            while True:
                content = self.receive_message()
                if content is not None:
                    self.xmlmsgdecode(content=content)
                    if callback:
                        try:
                            callback(content)
                        except Exception as e:
                            traceback.print_exc()
                            logger.error(f"回调函数执行错误: {e}")
                time.sleep(1)  # 防止CPU占用过高
        except KeyboardInterrupt:
            logger.info("订阅者已停止")
        except Exception as e:
            logger.error(f"订阅者运行错误: {e}")
        finally:
            self.close()

    def xmlmsgdecode(self, content):
        content = xmltodict.parse(content)
        Type = content["Message"]["Type"]
        if Type == "ROBOT_STATUS":
            Robot = content["Message"]["Robot"]
            self.robot_msg_docode(Robot)
        else:
            logger.debug(f"收到消息内容: {content}")

    def robot_msg_docode(self, Robot: dict):
        logger.info(
            f"小车状态: Id {Robot['Id']} - 电池 {Robot['Battery']}% - 状态 {Robot['Status']} - 位置 ({Robot['Pos']['x']},{Robot['Pos']['y']})"
            f"- 速度 {Robot['Speed']} - 警告{Robot['AlarmMain']}- 子警告{Robot['AlarmSub']}-滚动状态 {Robot['RollerStatus']}"
        )

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


if __name__ == "__main__":
    """主程序入口"""
    try:
        api = RcmsApi()
        api.build_from_cache()
        ZERO_MQ_IP = api.rcsdata[0].get("ip")
        ZERO_MQ_CTRL_PORT = api.rcsdata[0].get("zeroMqCtrlPort")
        ZERO_MQ_MESSAGE_PORT = api.rcsdata[0].get("zeroMqMessagePort")
        # 创建订阅者实例
        subscriber = ZeroMQSubscriber(
            ZERO_MQ_IP, ZERO_MQ_CTRL_PORT, ZERO_MQ_MESSAGE_PORT
        )
        # 运行订阅者，订阅所有主题

        subscriber.run()
    except Exception as e:
        logger.error(f"主程序错误: {e}")
        exit(1)
