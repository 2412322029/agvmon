import redis
from util.config import cfg

# 初始化Redis连接
redis_client = redis.Redis(**cfg.get("redis"))

# 从配置中获取rdstag
def get_rdstag():
    """从配置中获取rdstag"""
    return cfg.get("rcms.host").split("://")[1].replace(":", "-")

# 获取所有机器人状态
def get_all_robot_status(rdstag):
    """从Redis获取所有机器人状态"""
    robot_status = redis_client.hgetall(f"{rdstag}:ROBOT_STATUS")
    robots = {}
    for robot_id, status_json in robot_status.items():
        robot_id_str = robot_id.decode("utf-8")
        try:
            import json
            status = json.loads(status_json.decode("utf-8"))
            robots[robot_id_str] = status
        except json.JSONDecodeError:
            continue
    return robots