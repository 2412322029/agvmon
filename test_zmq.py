import time

import zmq

print(zmq.has('tls'))

def parse_message(message):
    """解析 ZeroMQ 消息"""
    try:
        # 转换为十六进制字符串
        hex_str = message.hex()
        print(f"消息十六进制: {hex_str}")
        
        # 尝试提取 ASCII 文本
        try:
            ascii_str = message.decode('ascii', errors='ignore')
            # 过滤掉非打印字符
            printable_str = ''.join(c for c in ascii_str if c.isprintable())
            if printable_str:
                print(f"ASCII 文本: {printable_str}")
        except:
            pass
        
        # 识别消息类型
        if b"READY" in message:
            print("消息类型: READY 消息")
            # 解析 READY 消息
            parts = message.split(b'\x00')
            if len(parts) > 1:
                print(f"状态: {parts[0].decode('ascii', errors='ignore')}")
                if len(parts) > 2:
                    socket_type = parts[2].decode('ascii', errors='ignore')
                    print(f"Socket 类型: {socket_type}")
        elif b"NULL" in message:
            print("消息类型: NULL 消息")
        elif hex_str.startswith('ff'):
            print("消息类型: 控制消息")
        
        print()
    except Exception as e:
        print(f"解析错误: {e}")


def test_zmq_address(ip, port, timeout=5000, use_curve=False, server_public_key=None):
    """测试 ZeroMQ 地址是否有数据"""
    try:
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.setsockopt(zmq.RCVTIMEO, timeout)  # 设置超时
        socket.setsockopt(zmq.SUBSCRIBE, b"")  # 订阅所有主题

        # 配置 CURVE 加密
        if use_curve:
            if not server_public_key:
                print("错误: 使用 CURVE 加密时必须提供服务器公钥")
                return False
            # 设置 CURVE 选项
            with open(server_public_key,"r") as f:
                server_public_key = f.read()
            try:
                socket.setsockopt_string(zmq.CURVE_SERVERKEY, server_public_key)
            except Exception as e:
                raise e
            address = f"tcp://{ip}:{port}"
        else:
            address = f"tcp://{ip}:{port}"
        
        print(f"连接到: {address}")
        socket.connect(address)

        print(f"等待消息... (超时: {timeout}ms)")
        message = socket.recv()

        if message:
            print(f"收到消息: {message[:500]}...")  # 打印前100字节
            print(f"完整消息长度: {len(message)} bytes")
            
            # 解析消息
            parse_message(message)
            
            return True
        else:
            print("收到空消息")
            return False

    except zmq.ZMQError as e:
        if e.errno == zmq.EAGAIN:
            print(f"超时 ({timeout}ms)，没有收到消息")
            return False
        raise e
        print(f"ZMQ错误: {e}")
        return False
    except Exception as e:
        print(f"错误: {e}")
        return False
    finally:
        try:
            socket.close()
            context.term()
        except:
            pass

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='测试 ZeroMQ 地址是否有数据')
    parser.add_argument('--ip', default='172.27.6.43', help='目标 IP 地址')
    parser.add_argument('--port', type=int, default=8790, help='目标端口')
    parser.add_argument('--timeout', type=int, default=5000, help='超时时间 (ms)')
    
    parser.add_argument('--use-curve', type=lambda x: x.lower() == 'true', default=False, help='是否使用 CURVE 加密')
    parser.add_argument('--server-public-key', help='服务器公钥')
    
    args = parser.parse_args()
    
    test_zmq_address(
        ip=args.ip,
        port=args.port,
        timeout=args.timeout,
        use_curve=args.use_curve,
        server_public_key=args.server_public_key
    )