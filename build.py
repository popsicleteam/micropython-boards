#!/usr/bin/env python3
"""
编译 MicroPython 固件命令。

使用：
    ./build.py --port esp32 --board ESP32_GENERIC_S3 --modules lvgl,/home/you/extmod
    ./build.py espressif/s3 --modules lvgl,/home/you/extmod
    ./build.py espressif/esp32-s3-eye
"""

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent
BUILD_DIR = REPO / "build"
BOARDS_DIR = REPO / "boards"
MODULES_DIR = REPO / "modules"
RELEASE_DIR = REPO / "release"
MICROPY_DIR = REPO / "micropython"
PORT_DIR = MICROPY_DIR / "ports"
JOBS = str(os.cpu_count() or 4)

BASH = "bash"


def say(msg=""):
    print(msg, flush=True)


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, encoding="utf-8", **kw)


def link(dest, target):
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(os.path.relpath(target, dest.parent), dest)
    say(f"linked {dest.relative_to(REPO)} -> {target}")


def clone_at(url, ref, dest, recursive=False):
    say(f"cloning {url} at {ref} into {dest.relative_to(REPO)}")
    run(["git", "init", "-q", str(dest)])
    # Git for Windows defaults core.autocrlf=true: patches checked out CRLF don't apply.
    run(["git", "-C", str(dest), "config", "core.autocrlf", "false"])
    run(["git", "-C", str(dest), "remote", "add", "origin", url])
    # A tag is fetched as a tag, so the checkout can still say which one it is.
    spec = (
        ref
        if re.fullmatch(r"[0-9a-f]{40}", ref)
        else f"refs/tags/{ref}:refs/tags/{ref}"
    )
    run(["git", "-C", str(dest), "fetch", "-q", "--depth", "1", "origin", spec])
    run(
        [
            "git",
            "-C",
            str(dest),
            "-c",
            "advice.detachedHead=false",
            "checkout",
            "-q",
            ref if spec != ref else "FETCH_HEAD",
        ]
    )
    if recursive:
        run(
            [
                "git",
                "-C",
                str(dest),
                "submodule",
                "update",
                "--init",
                "--recursive",
                "--depth",
                "1",
                "-q",
            ]
        )


def read_mods():
    rows = []
    for line in (REPO / "modules.lock").read_text().splitlines():
        line = line.partition("#")[0].strip()
        if line:
            rows.append(line.split())
    return rows


def read_dep(check_name):
    for line in (REPO / "deps.lock").read_text().splitlines():
        line = line.partition("#")[0].strip()
        if line:
            name, url, tag = line.split()
            if name == check_name:
                return url, tag
    return []


def read_config(path):
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f)


def ensure_micropython(env_path):
    if MICROPY_DIR.exists() or MICROPY_DIR.is_symlink():
        return
    if env_path:
        link(MICROPY_DIR, env_path)
    else:
        url, tag = read_dep("micropython")
        say(f"cloning MicroPython {tag}")
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
                str(MICROPY_DIR),
            ],
        )


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


def ensure_idf_deps(board_config):
    port_path = PORT_DIR / "esp32"
    main_deps_yml = port_path / "main" / "idf_component.yml"
    main_deps = read_config(main_deps_yml)
    if board_config.get("modules") is not None:
        for mod in board_config["modules"]:
            idf_deps = read_config(MODULES_DIR / mod / "idf_component.yml")
            if idf_deps is not None and main_deps is not None:
                for dep, ver in idf_deps["dependencies"].items():
                    main_deps["dependencies"][dep] = ver
                with open(main_deps_yml, "w", encoding="utf-8") as f:
                    yaml.dump(main_deps, f, allow_unicode=True)


def ensure_sdkconfig(board_config):
    sdkconfig = []
    port_path = PORT_DIR / board_config["port"]
    board_path = port_path / "boards" / board_config["board"]

    partition_csv = board_path / "partitions.csv"
    if partition_csv.exists():
        flash = "4MB" if board_config.get("flash") is None else board_config["flash"]
        rel_partition_path = partition_csv.relative_to(port_path)
        sdkconfig += [
            f'CONFIG_ESPTOOLPY_FLASHSIZE="{flash}"',
            f"CONFIG_ESPTOOLPY_FLASHSIZE_{flash}=y",
            "CONFIG_PARTITION_TABLE_CUSTOM=y",
            f'CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="{rel_partition_path}"',
            f'CONFIG_PARTITION_TABLE_FILENAME="{rel_partition_path}"',
        ]

    if board_config.get("sdkconfig") is not None:
        for key, val in board_config["sdkconfig"].items():
            if type(val) is str and val != "y":
                val = f'"{val}"'
            elif type(val) is bool:
                val = "y" if val else ""
            sdkconfig.append(f"CONFIG_{key}={val}")

    if len(sdkconfig) > 0:
        with open(
            PORT_DIR / "esp32" / "boards" / board_config["board"] / "sdkconfig.board",
            "a",
            encoding="utf-8",
        ) as f:
            f.write("\n".join(sdkconfig) + "\n")


def writeline(f, line, search):
    if line not in search:
        f.write(f"{line}\n")


def ensure_modules(board_config):
    port = board_config["port"]
    board_path = PORT_DIR / port / "boards" / board_config["board"]

    manifest_py = board_path / "manifest.py"
    with open(manifest_py, "a", encoding="utf-8") as f:
        manifest = manifest_py.read_text().splitlines() if manifest_py.exists() else []

        writeline(f, 'include("$(PORT_DIR)/boards")', manifest)  # 默认模块

        # 模块
        if board_config.get("modules") is not None:
            ext_modules = ({item[0]: item for item in read_mods()}).items()
            for mod in board_config["modules"]:
                # 初始模块
                for ext_mod_key, ext_mod in ext_modules:
                    if mod == ext_mod_key.partition("/")[0]:
                        mod_dir, url, ref = ext_mod
                        mod_path = MODULES_DIR / Path(mod_dir)
                        if not (mod_path.exists() or mod_path.is_symlink()):
                            clone_at(url, ref, mod_path, False)

                mod_path = Path(mod)
                if (MODULES_DIR / mod_path).exists():  # ex. lvgl
                    writeline(
                        f, f'include("$(MPY_DIR)/../modules/{mod_path}")', manifest
                    )
                elif (BOARDS_DIR / mod_path).exists():  # ex. boards/extmod
                    writeline(
                        f, f'include("$(MPY_DIR)/../boards/{mod_path}")', manifest
                    )
                elif mod_path.exists():  # ex. /path/you/extmod
                    rel_mod_path = mod_path.relative_to(REPO)
                    writeline(f, f'include("$(MPY_DIR)/../{rel_mod_path}")', manifest)
                else:  # ex. aioble
                    writeline(f, f'require("{mod}")', manifest)

        # 设备驱动
        if board_config.get("devices") is not None:
            for drv in board_config["devices"]:
                drv_path = Path(drv)
                if (MODULES_DIR / "devices" / drv_path).exists():
                    writeline(
                        f,
                        f'include("$(MPY_DIR)/../modules/devices/{drv_path}")',
                        manifest,
                    )

        # 补充公共模块
        for mod in ("base64", "hmac", "logging", "threading"):
            writeline(f, f'require("{mod}")', manifest)

        # 自定义模块
        if (board_path / "modules").exists():
            writeline(f, 'freeze("modules")', manifest)
        else:
            for mod in ("board_config.py", "boot.py", "main.py", "example.py"):
                if (board_path / mod).exists():
                    writeline(f, f'module("{mod}")', manifest)


def ensure_board(board_config, arg_board):
    port_path = PORT_DIR / board_config["port"]
    base_path = port_path / "boards" / board_config["base"]
    board_path = port_path / "boards" / board_config["board"]
    if base_path.exists():
        shutil.copytree(
            str(base_path),
            str(board_path),
            dirs_exist_ok=True,
        )
    shutil.copytree(
        str(BOARDS_DIR / Path(arg_board)),
        str(board_path),
        ignore=shutil.ignore_patterns("mpconfig.yml", "romfs", "*.romfs"),
        dirs_exist_ok=True,
    )


def make_mpy_cross():
    dest = MICROPY_DIR / "mpy-cross" / "build" / "mpy-cross"
    if not dest.exists():
        run(
            ["make", "-C", str(MICROPY_DIR / "mpy-cross"), "-j", JOBS],
            stdout=subprocess.DEVNULL,
        )


def make_board(prefix, board_config):
    port = board_config["port"]
    board = board_config["board"]
    variant = board_config.get("variant")
    build_path = BUILD_DIR / port / board

    make = [
        "make",
        "-C",
        str(PORT_DIR / port),
        f"BUILD={build_path}",
    ]
    if board:
        make.append(f"BOARD={board}")
        if variant:
            make.append(f"BOARD_VARIANT={variant}")

    subprocess.run(
        [BASH, "-c", prefix + shlex.join(make + ["clean"])],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        cmds = [shlex.join(c) for c in [make + ["submodules"], make]]
        run([BASH, "-c", prefix + " && ".join(cmds)])
    except subprocess.CalledProcessError:
        return

    for name in ("firmware.bin", "firmware.uf2", "micropython"):
        firmware_path = build_path / name
        if firmware_path.exists():
            return firmware_path


def esptool_merge_romfs(flasher_args, romfs_img, board_path, output_path):
    partition_csv = board_path / "partitions.csv"
    if not partition_csv.exists():
        return

    cmd = ["esptool.py"]
    cmd.extend(["--chip", flasher_args.get("extra_esptool_args", {}).get("chip", "")])
    cmd.extend(["merge_bin", "-o", str(output_path)])
    cmd.extend(flasher_args.get("write_flash_args", []))

    entries = {}
    base_path = output_path.parent
    for addr_str, file_path in flasher_args.get("flash_files", {}).items():
        entries[int(addr_str, 16)] = (addr_str, str(base_path / Path(file_path)))
    for addr_int in sorted(entries):
        addr_str, file_path = entries[addr_int]
        cmd.extend([addr_str, file_path])

    for line in partition_csv.read_text(encoding="utf-8").splitlines():
        line = line.partition("#")[0].strip()
        if line:
            parts = [p.strip() for p in line.split(",")]
            if parts[0] == "romfs":
                cmd.extend([parts[3], str(romfs_img)])
                break
    return cmd


def make_romfs(prefix, romfs_path, firmware_path):
    build_path = firmware_path.parent

    flasher_args_json = build_path / "flasher_args.json"
    if not flasher_args_json.exists():
        return

    romfs_img = build_path / "romfs.img"
    output_path = build_path / f"merged_{os.path.basename(firmware_path)}"

    cmds = [["mpremote", "romfs", "-o", str(romfs_img), "build", str(romfs_path)]]
    with flasher_args_json.open(encoding="utf-8") as f:
        data = json.load(f)
        cmd = esptool_merge_romfs(data, romfs_img, romfs_path.parent, output_path)
        if not cmd:
            return
        cmds.append(cmd)

    try:
        cmds = [shlex.join(c) for c in cmds]
        run([BASH, "-c", prefix + " && ".join(cmds)])
    except subprocess.CalledProcessError:
        return
    return output_path


def build(args):
    # 检查编译环境
    ensure_micropython(os.environ.get("MICROPY_DIR"))
    make_mpy_cross()

    # 读取开发板配置
    mpconfig_path = BOARDS_DIR / Path(args.board) / "mpconfig.yml"
    if not mpconfig_path.exists():
        # micorpython 原有开发板
        port, board = args.board.split("/")
        port_path = PORT_DIR / port
        board_path = port_path / "boards" / board
        if not board_path.exists():
            say(f"not found {port}/{board}")
            return
        board_config = {}
        board_config["port"] = port
        board_config["board"] = board
        board_config["variant"] = args.variant
        board_config["modules"] = args.modules
    else:
        # 自定义开发板
        board_config = read_config(mpconfig_path)
        if board_config is None:
            say(f"read {args.board}/mpconfig.yml failed.")
            return
        port = board_config["port"]
        board = re.sub(r"[^A-Za-z0-9]+", "_", args.board)
        board_config["board"] = board
        port_path = PORT_DIR / port
        board_path = port_path / "boards" / board
        if args.modules is not None:
            modules = []
            if board_config.get("modules") is not None:
                modules += board_config["modules"]
            modules += args.modules.split(",")
            board_config["modules"] = modules
        ensure_board(board_config, args.board)

    # 检查模块
    ensure_modules(board_config)

    # 编译配置
    prefix = ""
    mpconfigboard_cmake = board_path / "mpconfigboard.cmake"
    with open(mpconfigboard_cmake, "a", encoding="utf-8") as f:
        mpconfigboard = mpconfigboard_cmake.read_text()

        # 将模块加入编译配置
        writeline(
            f,
            "set(MICROPY_FROZEN_MANIFEST ${MICROPY_BOARD_DIR}/manifest.py)",
            mpconfigboard,
        )

        # 特定配置
        if port == "esp32":
            idf_path = ensure_espidf(os.environ.get("ESPIDF_DIR"))
            prefix = f'. "{(idf_path / "export.sh")}" >/dev/null && '
            ensure_idf_deps(board_config)
            ensure_sdkconfig(board_config)
            if (board_path / "sdkconfig.board").exists():
                writeline(
                    f,
                    "list(APPEND SDKCONFIG_DEFAULTS ${MICROPY_BOARD_DIR}/sdkconfig.board)",
                    mpconfigboard,
                )

    # 修复 MICROPY_HW_BOARD_NAME 重复定义，修改默认 MICROPY_BANNER 显示文本
    mpconfigboard_h = board_path / "mpconfigboard.h"
    mpconfigboard = mpconfigboard_h.read_text()
    mpconfigboard_h.write_text(
        "#ifdef MICROPY_HW_BOARD_NAME\n#undef MICROPY_HW_BOARD_NAME\n#endif\n"
        + mpconfigboard,
        encoding="utf-8",
    )
    with open(mpconfigboard_h, "a", encoding="utf-8") as f:
        writeline(
            f,
            '#define MICROPY_BANNER_NAME_AND_VERSION "MicroPython v" MICROPY_VERSION_STRING_BASE " on " MICROPY_BUILD_DATE',
            mpconfigboard,
        )
        if board_config.get("banner") is not None:
            writeline(
                f,
                f'#define MICROPY_BANNER_MACHINE "{board_config["banner"]}"',
                mpconfigboard,
            )

    # 开始编译
    firmware_path = make_board(prefix, board_config)

    # 清理
    restore_micropy(mpconfig_path)

    # 合并 romfs 资源
    if firmware_path and firmware_path.exists():
        romfs_path = BOARDS_DIR / Path(args.board) / "romfs"
        if romfs_path.exists():
            firmware_path = make_romfs(prefix, romfs_path, firmware_path)

    if not firmware_path or not firmware_path.exists():
        return

    say(f"\nBuilt into {firmware_path.parent.relative_to(REPO)}")
    say(f" {firmware_path}")

    # 部署
    if args.deploy:
        run([str(REPO / "deploy.py"), args.board])

    # 发布
    if args.release:
        release_path = RELEASE_DIR / port
        release_path.mkdir(parents=True, exist_ok=True)
        firmware_zip = (
            release_path / f"{board}_{datetime.now().strftime('%Y-%m-%d')}.zip"
        )
        with zipfile.ZipFile(firmware_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(firmware_path, arcname=os.path.basename(firmware_path))
        say(f"\nReleased into {release_path.relative_to(REPO)}")
        say(f" {firmware_zip}")


def restore_micropy(mpconfig_path):
    if mpconfig_path.exists():
        board_config = read_config(mpconfig_path)
        if board_config is not None:
            port = board_config["port"]
            board = re.sub(r"[^A-Za-z0-9]+", "_", args.board)
            board_path = PORT_DIR / port / "boards" / board
            shutil.rmtree(board_path, ignore_errors=True)
    run(["git", "-C", str(MICROPY_DIR), "restore", "."])
    run(["git", "-C", str(MICROPY_DIR), "clean", "-df"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MicroPython firmware builder.")
    parser.add_argument("board", help="board")
    parser.add_argument("--variant")
    parser.add_argument("--modules", help="comma list: short names, full paths")
    parser.add_argument("--deploy", action="store_true")
    parser.add_argument("--release", action="store_true")
    args = parser.parse_args()

    try:
        build(args)
    except KeyboardInterrupt:
        restore_micropy(BOARDS_DIR / Path(args.board) / "mpconfig.yml")
