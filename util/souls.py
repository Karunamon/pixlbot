import os
from typing import Optional
from xml.etree import ElementTree

import yaml

cores = {}


def format_from_soul(txt: str) -> (Optional[str], list):
    root = ElementTree.fromstring(txt)
    element = root.find("MESSAGE")
    if element is not None:
        return element.text, [
            root.find("FEELING").text,
            root.find("THOUGHT").text,
            root.find("ANALYSIS").text,
        ]
    else:
        return None


def scan_cores():
    for f in os.listdir("cores"):
        sc = yaml.safe_load(open(f"cores/{f}"))
        cores[f] = sc["name"]
