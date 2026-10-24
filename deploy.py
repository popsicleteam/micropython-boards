#!/usr/bin/env python3
import argparse
import os
import re
import shlex
import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent
BUILD_DIR = REPO / "build"
BOARDS_DIR = REPO / "boards"
PORT_DIR = REPO / "micropython" / "ports"

BASH = "bash"


def say(msg=""):
    print(msg, flush=True)


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, encoding="utf-8", **kw)


def link(dest, target):
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(os.path.relpath(target, dest.parent), dest)
    say(f"linked {dest.relative_to(REPO)} -> {target}")


def read_dep(check_name):
    for line in (REPO / "deps.lock").read_text().splitlines():
        line = line.partition("#")[0].strip()
        if line:
            name, url, tag = line.split()
            if name == check_name:
                return url, tag
    return []


def read_config(path):
    try:
        if path.exists():
            with open(path) as f:
                return yaml.safe_load(f)
    except Exception:
        pass
    return None


def ensure_espidf(env_path):
    idf_path = REPO / "tools" / "esp-idf"
    if idf_path.exists() or idf_path.is_symlink():
        return idf_path
    if env_path:
        link(idf_path, env_path)
    else:
        url, tag = read_dep("esp-idf")
        say(f"cloning ESP-IDF {tag}")
        run(
            [
                "git",
                "-c",
                "advice.detachedHead=false",
                "clone",
                "-q",
                "--depth",
                "1",
                "--branch",
                tag,
                url,
                str(idf_path),
            ],
        )
    return idf_path


def get_firmware(port, board):
    for name in ("firmware.bin", "firmware.uf2", "micropython"):
        firmware_path = BUILD_DIR / port / board / f"merged_{name}"
        if firmware_path.exists():
            return firmware_path
        firmware_path = BUILD_DIR / port / board / name
        if firmware_path.exists():
            return firmware_path


def esp_flash(idf_path, firmware, compress=0, erase=False, serial_port=False):
    prefix = f'. "{str(idf_path / "export.sh")}" >/dev/null && '
    esptool = ["esptool.py", "--chip", "auto"]
    if serial_port:
        esptool += ["--port", serial_port]
    cmds = []
    if erase:
        cmds.append(esptool + ["erase_flash"])
    cmds.append(esptool + ["write_flash", "-z", hex(compress), str(firmware)])
    run([BASH, "-c", prefix + " && ".join([shlex.join(c) for c in cmds])])


def main():
    parser = argparse.ArgumentParser(description="MicroPython firmware flasher.")
    parser.add_argument("board", help="board")
    parser.add_argument("-p", "--port")
    parser.add_argument("-z", "--compress", default=0)
    parser.add_argument("--erase", action="store_true")
    parser.add_argument("-f", "--firmware")
    args = parser.parse_args()

    # 读取开发板配置
    mpconfig_path = BOARDS_DIR / Path(args.board) / "mpconfig.yml"
    if not mpconfig_path.exists():
        # micorpython 原有开发板
        port, board = args.board.split("/")
        if not (PORT_DIR / port / "boards" / board).exists():
            say(f"not found {port}/{board}")
            return
    else:
        # 自定义开发板
        board_config = read_config(mpconfig_path)
        if board_config is None:
            say(f"read {args.board}/mpconfig.yml failed.")
            return
        port = board_config["port"]
        board = re.sub(r"[^A-Za-z0-9]+", "_", args.board)

    firmware = get_firmware(port, board)
    if firmware is None:
        say(f"Not found {args.board} firmware.")
        return

    if port == "esp32":
        idf_path = ensure_espidf(os.environ.get("ESPIDF_DIR"))
        esp_flash(idf_path, firmware, int(args.compress), args.erase, args.port)


if __name__ == "__main__":
    main()
