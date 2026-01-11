#!/usr/bin/env python3

import json

from dataparse import generate_map_image, parse_ShareMapInfo
from helper import sharemap2json


def test_svg_export():
    # Read the XML file
    # xml_file_path = "data/1.xml"
    # if not os.path.exists(xml_file_path):
    #     print(f"Error: File {xml_file_path} not found")
    #     return

    # with open(xml_file_path, "r", encoding="gbk") as f:
    #     xml_content = f.read()

    with open(
        "data/172.18.2.75-20260103T234101-772.xml", "r", encoding="utf-8"
    ) as file:
        content = file.read()
    json_data = json.loads(content)
    xml_content = sharemap2json(json_data)

    try:
        # Parse the XML content
        json_result = parse_ShareMapInfo(xml_content)
        print("Parse successful!")

        # Generate and save both PNG and SVG images
        print("\nGenerating map images...")

        # Generate PNG image
        map_image = generate_map_image(
            json_result, desired_width=1600, show_labels=True
        )
        png_path = "data/map_image.png"
        map_image.save(png_path)
        print(f"PNG image saved to {png_path}")
        print(f"PNG dimensions: {map_image.size[0]} x {map_image.size[1]} pixels")

        # Generate SVG image
        svg_path = "data/map_image.svg"
        map_image = generate_map_image(
            json_result,
            desired_width=1600,
            show_labels=True,
            export_svg=True,
            svg_filename=svg_path,
        )
        print(f"SVG vector image saved to {svg_path}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_svg_export()
