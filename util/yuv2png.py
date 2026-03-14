import asyncio
import io
import logging
from pathlib import Path
from typing import AsyncGenerator, NoReturn

import aiofiles
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

async def y_only_to_rgb(y_data_file=None, y_data=None, width=800, height=600) -> Image|NoReturn:
    """
    将只有Y平面(灰度)的数据转换为RGB图像。
    :param y_data_file: Yuv数据文件路径
    :param y_data: Yuv数据
    :param width: 图像宽度
    :param height: 图像高度
    :return: RGB图像的PIL图像对象
    """
    if y_data_file is None and y_data is None:
        logger.warning("y_data_file和y_data都为None")
        return None
    
    if y_data_file is not None and not Path(y_data_file).exists():
        logger.warning(f"文件不存在: {y_data_file}")
        return None
    if y_data is None:
        async with aiofiles.open(y_data_file, "rb") as f:
            data = await f.read()
        yuv_data = np.frombuffer(data, dtype=np.uint8)
    else:
        yuv_data = np.frombuffer(y_data, dtype=np.uint8)
    def save_image():
        try:
            # 将Y数据reshape为二维图像
            y = yuv_data.reshape((height, width)).astype(np.float32)
            # 将Y值归一化到0-255范围
            y = y.clip(0, 255)
            # 创建RGB图像（灰度图，R=G=B=Y）
            rgb_image = np.stack([y, y, y], axis=2).astype(np.uint8)
            img = Image.fromarray(rgb_image, "RGB")
            return img
        except Exception as e:
            raise ValueError(f"转换YUV数据为RGB图像时出错: {e}")
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, save_image)


async def y_only_to_rgb_stream(y_data_file=None,y_data=None, width=800, height=600, chunk_size=8192) -> AsyncGenerator[bytes, None]:
    """
    将YUV文件转换为RGB图像并返回流生成器，用于HTTP响应。
    :param y_data_file: Y数据文件路径
    :param y_data: Yuv数据
    :param width: 图像宽度
    :param height: 图像高度
    :param chunk_size: 每次生成的块大小（字节）
    :return: 异步生成器，每次生成一个数据块
    """
    # 转换图像
    rgb_image = await y_only_to_rgb(y_data_file, y_data, width, height)
    if rgb_image is None:
        raise ValueError("转换YUV数据为RGB图像失败")

    # 在线程池中执行同步的图像保存操作
    def save_image_sync():
        buffer = io.BytesIO()
        rgb_image.save(buffer, format="PNG")
        buffer.seek(0)
        print(f"{y_data_file if y_data is None else '内存中的Yuv数据'} 转换的png已保存在内存缓冲区")
        return buffer

    loop = asyncio.get_event_loop()
    img_buffer = await loop.run_in_executor(None, save_image_sync)

    try:
        while True:
            chunk = img_buffer.read(chunk_size)
            if not chunk:
                break
            yield chunk
    except Exception as e:
        logger.error(f"生成图像流时出错: {e}")
    finally:
        img_buffer.close()


async def main():
    await y_only_to_rgb("D:\\24123\\Desktop\\hik\\MapStudioPro\\Capture\\tdcl2026_03_12_15_35_26_2080_1.yuv")


if __name__ == "__main__":
    asyncio.run(main())
