import json
from helper import sharemap2json

if __name__ == "__main__":
    with open("data/2.json", "r", encoding="utf-8") as file:
        content = file.read()
    json_data = json.loads(content)
    c_xml=sharemap2json(json_data)
    
    
