import json

from dataparse import generate_map_image, parse_mapxml, parse_ShareMapInfo

if __name__ == "__main__":
    # Read the JSON file
    with open("data/1.json", "r", encoding="utf-8") as file:
        content = file.read()
    json_data = json.loads(content)
    map_data = parse_ShareMapInfo(json_data["shareInfos"][0]["content"])
    print(map_data)
    with open("data/map_data.json", "w", encoding="utf-8") as f:
        f.write(map_data)
    print("\nJSON result saved to data/map_data.json")

        
    # --------------------
    # Parse the XML file
    # with open("data/172.18.2.72-20260110T032944-163.xml", "r") as file:
    #     content = file.read()
    # map_data = parse_mapxml(content)
    # map_image = generate_map_image(
    #     map_data, desired_width=800, dot_size=3, show_labels=True
    # )
    # output_file = "data/map_image.png"
    # map_image.save(output_file)
    # print(f"Map image saved as '{output_file}'")
