import logging
import sys
import xml.etree.ElementTree as ET

import pika

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("rabbitmq.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


class RabbitMQClient:
    def __init__(self, xml_config=None):
        self.config = self._parse_xml_config(xml_config) if xml_config else None
        self.connection = None
        self.channel = None

    def _parse_xml_config(self, xml_content):
        """解析XML配置信息"""
        try:
            root = ET.fromstring(xml_content)
            config = {
                "user": root.find("rabbitmpUser").text
                if root.find("rabbitmpUser") is not None
                else "root",
                "exchange": root.find("rabbitmqExchange").text
                if root.find("rabbitmqExchange") is not None
                else "exchangeMsg",
                "host": root.find("rabbitmqIp").text
                if root.find("rabbitmqIp") is not None
                else "127.0.0.1",
                "password": root.find("rabbitmqPassword").text
                if root.find("rabbitmqPassword") is not None
                else "",
                "port": int(root.find("rabbitmqPort").text)
                if root.find("rabbitmqPort") is not None
                else 5672,
            }
            logger.info(f"解析XML配置成功: {config}")
            return config
        except Exception as e:
            logger.error(f"解析XML配置失败: {e}")
            raise

    def connect(self, host=None, port=None, user=None, password=None, virtual_host="/"):
        """建立RabbitMQ连接"""
        try:
            # 使用传入的参数或配置文件中的参数
            host = host or (self.config["host"] if self.config else "127.0.0.1")
            port = port or (self.config["port"] if self.config else 5672)
            user = user or (self.config["user"] if self.config else "guest")
            password = password or (self.config["password"] if self.config else "guest")

            credentials = pika.PlainCredentials(user, password)
            parameters = pika.ConnectionParameters(
                host=host,
                port=port,
                virtual_host=virtual_host,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300,
            )

            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            logger.info(f"成功连接到RabbitMQ服务器: {host}:{port}")
            return True
        except Exception as e:
            logger.error(f"连接RabbitMQ服务器失败: {e}")
            raise

    def declare_exchange(
        self, exchange_name=None, exchange_type="fanout", durable=True
    ):
        """声明交换机"""
        try:
            if not self.channel:
                raise Exception("RabbitMQ连接未建立")

            exchange_name = exchange_name or (
                self.config["exchange"] if self.config else "default_exchange"
            )
            self.channel.exchange_declare(
                exchange=exchange_name, exchange_type=exchange_type, durable=durable
            )
            logger.info(f"成功声明交换机: {exchange_name}")
            return exchange_name
        except Exception as e:
            logger.error(f"声明交换机失败: {e}")
            raise

    def declare_queue(
        self, queue_name, durable=True, exclusive=False, auto_delete=False
    ):
        """声明队列"""
        try:
            if not self.channel:
                raise Exception("RabbitMQ连接未建立")
            if not queue_name:
                queue_name = self.config["exchange"]
            result = self.channel.queue_declare(
                queue=queue_name,
                durable=durable,
                exclusive=exclusive,
                auto_delete=auto_delete,
            )
            logger.info(f"成功声明队列: {queue_name}")
            return result.method.queue
        except Exception as e:
            logger.error(f"声明队列失败: {e}")
            raise

    def bind_queue(self, queue_name, exchange_name=None, routing_key=""):
        """绑定队列到交换机"""
        try:
            if not self.channel:
                raise Exception("RabbitMQ连接未建立")

            exchange_name = exchange_name or (
                self.config["exchange"] if self.config else "default_exchange"
            )
            self.channel.queue_bind(
                queue=queue_name, exchange=exchange_name, routing_key=routing_key
            )
            logger.info(f"成功绑定队列 {queue_name} 到交换机 {exchange_name}")
            return True
        except Exception as e:
            logger.error(f"绑定队列失败: {e}")
            raise

    def publish_message(
        self, message, exchange_name=None, routing_key="", properties=None
    ):
        """发布消息"""
        try:
            if not self.channel:
                raise Exception("RabbitMQ连接未建立")

            exchange_name = exchange_name or (
                self.config["exchange"] if self.config else "default_exchange"
            )
            self.channel.basic_publish(
                exchange=exchange_name,
                routing_key=routing_key,
                body=message,
                properties=properties,
            )
            logger.info(f"成功发布消息到交换机 {exchange_name}")
            return True
        except Exception as e:
            logger.error(f"发布消息失败: {e}")
            raise

    def consume_message(self, queue_name, callback, auto_ack=False):
        """消费消息"""
        try:
            if not self.channel:
                raise Exception("RabbitMQ连接未建立")

            logger.info(f"开始消费队列 {queue_name} 的消息")
            self.channel.basic_consume(
                queue=queue_name, on_message_callback=callback, auto_ack=auto_ack
            )
            self.channel.start_consuming()
        except Exception as e:
            logger.error(f"消费消息失败: {e}")
            raise

    def close(self):
        """关闭连接"""
        try:
            if self.channel:
                self.channel.close()
            if self.connection and self.connection.is_open:
                self.connection.close()
            logger.info("成功关闭RabbitMQ连接")
            return True
        except Exception as e:
            logger.error(f"关闭RabbitMQ连接失败: {e}")
            raise


# 示例用法
if __name__ == "__main__":
    # XML配置示例
    xml_config = """<?xml version="1.0" encoding="utf-8" standalone="yes"?> 
 <result> 
     <rabbitmpUser>root</rabbitmpUser> 
     <rabbitmqExchange>exchangeMsg</rabbitmqExchange> 
     <rabbitmqIp>172.18.2.90</rabbitmqIp> 
     <rabbitmqPassword>Hik12345+</rabbitmqPassword> 
     <rabbitmqPort>5672</rabbitmqPort> 
 </result>"""

    try:
        # 创建客户端实例
        client = RabbitMQClient(xml_config)

        # 连接到RabbitMQ
        client.connect()

        # 声明交换机
        client.declare_exchange()

        # 声明队列
        queue_name = client.declare_queue(queue_name="test_queue")

        # 绑定队列到交换机
        client.bind_queue(queue_name)

        # 定义消息处理回调
        def callback(ch, method, properties, body):
            logger.info(f"收到消息: {body.decode('utf-8')}")
            ch.basic_ack(delivery_tag=method.delivery_tag)

        # 开始消费消息（注释掉，避免阻塞）
        client.consume_message('test_queue', callback)

        logger.info("RabbitMQ客户端示例运行成功")

    except Exception as e:
        logger.error(f"RabbitMQ客户端示例运行失败: {e}")
    finally:
        client.close() if "client" in locals() else None
