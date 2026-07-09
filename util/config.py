import pathlib
import shutil
import sys

import redis
import toml

# 配置文件放在 main.dist 外部，防止更新时被覆盖
_BUNDLED_CFG = __file__.replace("config.py", "config.toml")

if getattr(sys, "frozen", False):
    _APP_ROOT = pathlib.Path(sys.executable).parent
else:
    _APP_ROOT = pathlib.Path.cwd()

CFG_PATH = str(_APP_ROOT / "config.toml")


def _ensure_config():
    """首次运行时，将默认配置复制到外部目录。"""
    if not pathlib.Path(CFG_PATH).exists():
        bundled = pathlib.Path(_BUNDLED_CFG)
        if bundled.exists():
            shutil.copy2(bundled, CFG_PATH)
        else:
            pathlib.Path(CFG_PATH).touch()


_ensure_config()


class Config:
    def __init__(self):
        self._load_config()

    def _load_config(self):
        """加载配置文件"""
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            self.data = toml.load(f)

    def reload(self):
        """重新加载配置文件"""
        self._load_config()

    def get(self, key: str):
        """
        获取配置项
        :param key: 配置项键 .访问嵌套项
        :return: 配置项值
        """

        def _get_recursive(data, keys):
            if not keys:
                return data
            k, *rest = keys
            if isinstance(data, dict) and k in data:
                return _get_recursive(data[k], rest)
            return None

        return _get_recursive(self.data, key.split("."))

    def set(self, key: str, value):
        """
        设置配置项
        :param key: 配置项键 .访问嵌套项
        :param value: 配置项值
        """

        def _set_recursive(data, keys, value):
            if not keys:
                return value
            k, *rest = keys

            # 检查键是否为数字索引
            is_index = k.isdigit()

            # 如果当前数据不是字典且不是列表（当键是索引时），转换为适当类型
            if not isinstance(data, dict) and not (is_index and isinstance(data, list)):
                data = [] if is_index else {}

            if is_index:
                # 处理列表索引
                index = int(k)
                # 确保列表足够长
                while len(data) <= index:
                    data.append({})
                data[index] = _set_recursive(data[index], rest, value)
            else:
                # 处理字典键
                if k not in data:
                    data[k] = (
                        []
                        if (rest and rest[0].isdigit())
                        or isinstance(value, list)
                        and not rest
                        else {}
                    )
                data[k] = _set_recursive(data[k], rest, value)

            return data

        self.data = _set_recursive(self.data, key.split("."), value)

    def save(self):
        """
        保存配置项
        """
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            toml.dump(self.data, f)

    def get_with_reload(self, key: str):
        """
        获取配置项（每次从文件重新加载）
        :param key: 配置项键 .访问嵌套项
        :return: 配置项值
        """
        self.reload()
        return self.get(key)


cfg = Config()
r = redis.Redis(**cfg.get("redis"))
