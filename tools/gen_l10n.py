import os
from string import Template

import yaml

l10n_template = Template("""
_language = "en"

_locales = $locales

def set_language(lang):
    global _language
    _language = lang

def __getattr__(attr):
    if attr == "get_language":
        return _language
    if attr == "set_language":
        return set_language
    if _language != "en" and attr in _locales[_language]:
        return _locales[_language][attr]
    elif attr in _locales["en"]:
        return _locales["en"][attr]
    raise AttributeError(f"module '{__name__}' has no attribute '{attr}'")
""")


def load_yaml(file):
    data = None
    try:
        with open(file) as yaml_file:
            data = yaml.safe_load(yaml_file)
    except:
        pass
    return data


def gen_l10n(board_info):
    board = board_info["id"]
    port = board_info["port"]

    l10n_file = ""
    locales = {}

    l10n_path = f"boards/{board}/l10n"
    if not os.path.exists(l10n_path):
        return

    for root, dirs, files in os.walk(l10n_path):
        for file in files:
            if file.endswith(".yml") or file.endswith(".yaml"):
                file_path = os.path.join(root, file)
                name = os.path.splitext(os.path.basename(file_path))[0]
                data = load_yaml(file_path)
                if data:
                    locales[name] = data

    l10n_file = l10n_template.substitute(locales=str(locales))
    dest_file = f"micropython/ports/{port}/boards/{board}/modules/l10n.py"

    with open(dest_file, "w") as f:
        f.write(l10n_file)
