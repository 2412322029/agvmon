import json
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw


def parse_mapxml(content):
    root = ET.fromstring(content)
    # Extract all map data points (coordinates and macName)
    map_data = []
    for row in root.findall(".//row"):
        cooX = float(row.find("cooX").text)
        cooY = float(row.find("cooY").text)
        # Extract macName if available, otherwise use empty string
        macName_elem = row.find("macName")
        macName = macName_elem.text if macName_elem is not None else ""
        if macName:
            map_data.append(
                {
                    "x": cooX,
                    "y": cooY,
                    "macName": macName,
                }
            )
        else:
            map_data.append(
                {
                    "x": cooX,
                    "y": cooY,
                }
            )
    return map_data


def parse_ShareMapInfo(j):
    root = ET.fromstring(j)
    map_data = {
        'map_ret_list': [],
        'ret_name_list': []
    }
    
    # Iterate through all MapRet elements
    for map_ret in root.findall('.//MapRet'):
        # Extract all Point coordinates
        points = []
        for point in map_ret.findall('.//Point'):
            xpos = int(point.get('xpos'))
            ypos = int(point.get('ypos'))
            points.append({
                'xpos': xpos,
                'ypos': ypos
            })
        
        # Extract Area color attributes
        area = map_ret.find('.//Area')
        area_data = {
            'color_a': int(area.get('color_a')),
            'color_r': int(area.get('color_r')),
            'color_g': int(area.get('color_g')),
            'color_b': int(area.get('color_b'))
        }
        
        # Add MapRet data to list
        map_data['map_ret_list'].append({
            'points': points,
            'area': area_data
        })
    
    # Iterate through all RetName elements
    for ret_name in root.findall('.//RetName'):
        # Extract RetName attributes
        ret_name_data = {
            'start_x': int(ret_name.get('start_x')),
            'start_y': int(ret_name.get('start_y')),
            'end_x': int(ret_name.get('end_x')),
            'end_y': int(ret_name.get('end_y')),
            'size': float(ret_name.get('size')),
            'font': ret_name.get('font'),
            'font_color_a': int(ret_name.get('font_color_a')),
            'font_color_r': int(ret_name.get('font_color_r')),
            'font_color_g': int(ret_name.get('font_color_g')),
            'font_color_b': int(ret_name.get('font_color_b')),
            'text': ret_name.text.strip() if ret_name.text else ''
        }
        
        # Add RetName data to list
        map_data['ret_name_list'].append(ret_name_data)
    
    # Convert to JSON and return, ensure non-ASCII characters are preserved
    return json.dumps(map_data, indent=2, ensure_ascii=False)
    


# Create a function to generate map image from map data
def generate_map_image(map_data, desired_width=800, dot_size=3, show_labels=True):
    """
    Generate a map image from the provided map data.

    Args:
        map_data: List of dictionaries with 'x', 'y', and 'macName' keys
        desired_width: Desired width of the output image in pixels
        dot_size: Size of each dot representing a coordinate point
        show_labels: Whether to show macName labels for each point

    Returns:
        PIL.Image: The generated map image
    """
    # Extract coordinates for analysis
    xs = [point["x"] for point in map_data]
    ys = [point["y"] for point in map_data]
    minX = min(xs)
    maxX = max(xs)
    minY = min(ys)
    maxY = max(ys)

    # Calculate coordinate space dimensions
    coord_width = maxX - minX
    coord_height = maxY - minY

    print(f"Found {len(map_data)} map points")
    print(f"Coordinate range: X({minX}, {maxX}), Y({minY}, {maxY})")
    print(f"Coordinate space dimensions: {coord_width} x {coord_height}")

    # Determine image dimensions and scaling factor
    scale = desired_width / coord_width
    image_width = int(coord_width * scale)
    image_height = int(coord_height * scale)

    print(f"Image dimensions: {image_width} x {image_height} pixels")
    print(f"Scaling factor: {scale:.4f}")

    # Helper function to convert coordinates to image pixels
    def coord_to_pixel(coord, min_val, max_val, image_size):
        # Normalize coordinate to [0, 1] range
        normalized = (coord - min_val) / (max_val - min_val)
        # Scale to image size
        return int(normalized * image_size)

    # Create a white background image
    image = Image.new("RGB", (image_width, image_height), color="white")
    draw = ImageDraw.Draw(image)

    # Draw all map points
    for point in map_data:
        x, y = point["x"], point["y"]
        macName = point.get("macName", "")

        # Convert to pixel coordinates
        pixel_x = coord_to_pixel(x, minX, maxX, image_width - dot_size)
        pixel_y = image_height - coord_to_pixel(y, minY, maxY, image_height - dot_size)

        # Draw a small black dot
        draw.ellipse(
            [(pixel_x, pixel_y), (pixel_x + dot_size, pixel_y + dot_size)], fill="black"
        )

        # Draw macName label if available and show_labels is True
        if show_labels and macName:
            # Position label to the right of the dot
            label_x = pixel_x + dot_size + 2
            label_y = pixel_y - 5
            # Draw label with black text, small font
            draw.text((label_x, label_y), macName, fill="black")

    return image
