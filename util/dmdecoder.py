import asyncio
import pathlib

from PIL import Image
from pylibdmtx.pylibdmtx import ENCODING_SIZE_NAMES, decode, encode


def all_size():
    return ENCODING_SIZE_NAMES


async def encode_dmdtx(data, size=ENCODING_SIZE_NAMES[5]) -> Image.Image:
    if size not in ENCODING_SIZE_NAMES:
        raise ValueError(f"Invalid size: {size}")

    def inner():
        encoded = encode(data.encode("utf8"), size=size)
        return Image.frombytes("RGB", (encoded.width, encoded.height), encoded.pixels)

    return await asyncio.to_thread(inner)


async def encode_dmdtx_svg(data, size=ENCODING_SIZE_NAMES[5]) -> str:
    if size not in ENCODING_SIZE_NAMES:
        raise ValueError(f"Invalid size: {size}")

    def inner():
        encoded = encode(data.encode("utf8"), size=size)
        width = encoded.width
        height = encoded.height
        pixels = encoded.pixels

        svg_content = '<?xml version="1.0" encoding="utf-8"?>\n'
        svg_content += f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
        svg_content += '  <rect width="100%" height="100%" fill="white"/>\n'

        for y in range(height):
            for x in range(width):
                offset = (y * width + x) * 3
                r = pixels[offset]
                if r == 0:
                    svg_content += (
                        f'  <rect x="{x}" y="{y}" width="1" height="1" fill="black"/>\n'
                    )

        svg_content += "</svg>\n"

        return svg_content

    return await asyncio.to_thread(inner)


async def decode_dmdtx(img):
    if isinstance(img, str) or isinstance(img, pathlib.Path):
        img = Image.open(img)
    if not isinstance(img, Image.Image):
        raise ValueError(
            "Input must be a PIL Image object, pathlib.Path object, or a string"
        )
    results = await asyncio.to_thread(decode, img, timeout=1000, max_count=3)
    if results:
        return list(
            map(
                lambda x: {
                    "data": x.data.decode("utf8"),
                    "rect": {
                        "left": x.rect.left,
                        "top": x.rect.top,
                        "width": x.rect.width,
                        "height": x.rect.height,
                    },
                },
                results,
            )
        )
    else:
        return None


# results = decode(Image.open("d:\\24123\\Desktop\\hik\\MapStudioPro\\Capture\\tdcl2026_03_12_15_35_26_2080_0.png"))
# print(results)


if __name__ == "__main__":
    data = asyncio.run(
        decode_dmdtx(
            "d:\\24123\\Desktop\\1.png"
        )
    )
    print(data)
