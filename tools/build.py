#!python3
# -*- coding: UTF-8 -*-
import argparse
import importlib
import os
import re
import shutil
import sys

import yaml
from gen_l10n import gen_l10n

# add arguments
#
parser = argparse.ArgumentParser(description="MicroPython Board builder.")
parser.add_argument("board", help="board name")
parser.add_argument("-C", "--clean", action="store_true", help="clean built")
parser.add_argument("-p", "--port", help="device port")
parser.add_argument("-P", action="store_true", help="use default device port")
parser.add_argument("-E", "--erase", action="store_true", help="erase device flash")
args = parser.parse_args()

# show help
if not args.board:
    parser.print_help()
    exit(0)


# clean
#
def clean(board_info):
    print("\ncleaning...\n")

    board = board_info["id"]
    port = board_info["port"]

    os.chdir(f"micropython/ports/{port}")
    os.system(f"make clean BOARD={board}")
    os.chdir("../../../")


# install idf components from cmoudles.cmake
#
def is_exists(path):
    return os.path.exists(path)


def load_yaml(file):
    data = None
    try:
        if is_exists(file):
            with open(file) as yaml_file:
                data = yaml.safe_load(yaml_file)
    except:
        pass
    return data


def install_idf_comps(components):
    os.chdir("micropython/ports/esp32")
    for comp_id in components:
        os.system(f'idf.py add-dependency "{comp_id}"')
    os.chdir("../../../")


def get_idf_comps(file):
    components = []
    pattern = re.compile(r"\$\{C_MODULES_DIR\}/([^/]+)/micropython.cmake\)$")
    with open(file) as f:
        lines = f.readlines()
        for line in lines:
            match = pattern.search(line)
            if match:
                mod_name = match.group(1)
                idf_comps = load_yaml(f"cmodules/{mod_name}/idf_component.yml")
                if idf_comps:
                    for comp_name, comp_ver in idf_comps["dependencies"].items():
                        comp_id = f"{comp_name}{comp_ver}"
                        if comp_id not in components:
                            components.append(comp_id)
    return components


# build
#
def walk_dir(dir_path, excludes_subdir=False):
    file_list = []
    for root, dirs, files in os.walk(dir_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        files[:] = [f for f in files if not f.startswith(".")]
        if excludes_subdir and dir_path != root:
            break
        for file in files:
            file_list.append(os.path.join(root, file))
    return file_list


def read_partitions_from(files):
    pattern = r"^partitions-[a-zA-Z0-9_-]+\.csv$"
    for filename in files:
        if re.match(pattern, filename.split("/")[-1]) is not None:
            with open(filename, "r") as f:
                rows = []
                for line in f:
                    rows.append(line.strip().split(","))
                return rows


def build(board_info):
    # git restore
    os.chdir("micropython")
    os.system("git restore .")
    os.system("git clean -df")
    os.chdir("..")

    print("\nbuilding...\n")

    board = board_info["id"]
    port = board_info["port"]
    chip = board_info["chip"]
    version = board_info["version"]

    board_dir = f"boards/{board}"

    # import board build script
    if is_exists(f"boards/{board}/build.py"):
        sys.path.insert(0, os.getcwd())
        importlib.import_module(f"boards.{board}.build")

    # coping board files
    board_files = []
    board_files.extend(walk_dir(board_dir))

    for file in board_files:
        destfile = f"micropython/{file.replace(f'boards/{board}/', f'ports/{port}/boards/{board}/')}"
        dir = os.path.dirname(destfile)
        if not is_exists(dir):
            os.makedirs(dir)
        shutil.copy(file, destfile)

    # generate l10n file
    gen_l10n(board_info)

    # esp32 install idf components
    cmodules_file = f"{board_dir}/cmodules.cmake"
    if port == "esp32" and is_exists(cmodules_file):
        idf_components = get_idf_comps(cmodules_file)
        install_idf_comps(idf_components)

    os.chdir(f"micropython/ports/{port}")

    # write version
    board_module_path = f"boards/{board}/modules/{board.lower()}"
    if is_exists(board_module_path):
        major, minor, revision = version.split(".")
        with open(f"{board_module_path}/version.py", "w") as f:
            f.write(f"major = {major}\n")
            f.write(f"minor = {minor}\n")
            f.write(f"revision = {revision}\n")

    # write MICROPY_BANNER_NAME_AND_VERSION and MICROPY_BANNER_MACHINE
    with open(f"boards/{board}/mpconfigboard.h", "a") as f:
        f.write(f"""
#define MICROPY_BANNER_NAME_AND_VERSION                                                                                \\
    MICROPY_HW_BOARD_NAME " with " MICROPY_HW_MCU_NAME " v{version} base on MicroPython v" MICROPY_VERSION_STRING_BASE

#ifndef MICROPY_BANNER_MACHINE
#define MICROPY_BANNER_MACHINE                                                                                         \\
    "Provided by\\r\\n"                                                                                                  \\
    "░█▀▄░█░░░█▀█░█▀▀░█░█░█▀▀░█▀█░█▀▄░█▀▀░░░█░░░█▀█░█▀▄\\r\\n"                                                           \\
    "░█▀▄░█░░░█░█░█░░░█▀▄░█░░░█░█░█░█░█▀▀░░░█░░░█▀█░█▀▄\\r\\n"                                                           \\
    "░▀▀░░▀▀▀░▀▀▀░▀▀▀░▀░▀░▀▀▀░▀▀▀░▀▀░░▀▀▀░░░▀▀▀░▀░▀░▀▀░"
#endif
""")

    # build micropython
    os.system(f"make submodules BOARD={board}")
    os.system(f"make BOARD={board}")
    os.chdir("../../../")

    # combine resources to firmware
    resources_dir = f"{board_dir}/resources"
    firmware_path = f"micropython/ports/{port}/build-{board}/firmware.bin"

    # out firmware path
    out_firmware = f"dist/{board}.{board_info['version']}.bin".lower()

    if not is_exists("dist"):
        os.makedirs("dist")

    partitions = read_partitions_from(board_files)
    if partitions and is_exists(resources_dir) and port == "esp32":
        print("\ncombining resources...\n")

        for partition in partitions:
            if partition[0] == "resource":
                cmd_str = f"python3 tools/combine/combine.py --dir {resources_dir} "
                cmd_str += (
                    f"--offset {partition[3].strip()} --size {partition[4].strip()} "
                )
                if chip == "esp32":
                    cmd_str += "--esp32 "
                cmd_str += f"{firmware_path} {out_firmware}"
                os.system(cmd_str)
                break
    else:
        os.system(f"cp {firmware_path} {out_firmware}")

    print("\nSuccessfully!")
    print(f"Generated {out_firmware}")
    return out_firmware


# esp32 flash firmware
#
def esp32_flash(board_info, firmware_path):
    if args.erase:
        print("\ncleaning flash...\n")
        if args.P:
            os.system("esptool.py --chip auto erase_flash")
        else:
            os.system(f"esptool.py --chip auto --port {args.port} erase_flash")

    if not firmware_path:
        firmware_dir = "dist"
        firmware_list = os.listdir(firmware_dir)
        firmware_list.sort(
            key=lambda f: (
                os.path.getmtime(f"{firmware_dir}/{f}")
                if not os.path.isdir(f"{firmware_dir}/{f}")
                else 0
            )
        )
        firmware_path = f"{firmware_dir}/{firmware_list[-1]}"
        print(f"{firmware_list[-1]} is ready.")

    print("\nuploading firmware...\n")

    flash_address = 0x1000 if board_info["chip"] == "esp32" else 0
    if args.P:
        os.system(f"esptool.py --chip auto write_flash {flash_address} {firmware_path}")
    else:
        os.system(
            f"esptool.py --chip auto --port {args.port} write_flash {flash_address} {firmware_path}"
        )


if __name__ == "__main__":
    board = args.board.upper()
    board_info = load_yaml(f"boards/{board}/boardinfo.yml")

    if board_info:
        board_info["id"] = board

    if board_info and args.clean:
        clean(board_info)

    firmware_path = None
    if board_info:
        firmware_path = build(board_info)

    if board_info["port"] == "esp32" and (args.port or args.P):
        esp32_flash(board_info, firmware_path)
