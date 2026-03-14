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


async def decode_dmdtx(img):
    if isinstance(img, str) or isinstance(img, pathlib.Path):
        img = Image.open(img)
    if not isinstance(img, Image.Image):
        raise ValueError(
            "Input must be a PIL Image object, pathlib.Path object, or a string"
        )
    results = await asyncio.to_thread(decode, img)
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
            "d:\\24123\\Desktop\\hik\\MapStudioPro\\Capture\\tdcl2026_03_12_15_35_26_2080_0.png"
        )
    )
    print(data)
