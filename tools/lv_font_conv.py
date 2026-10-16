#!/usr/bin/env python3
"""
lv_font_conv.py — lv_font_conv 的 Python 命令行封装

调用优先级：
    1. 本地/全局安装的 lv_font_conv 可执行文件
    2. bunx（Bun.js，推荐，速度最快）
    3. npx（Node.js，兜底）

依赖（任选其一）：
    Bun：  curl -fsSL https://bun.sh/install | bash
    Node： npm install -g lv_font_conv

用法示例：
    python lv_font_conv.py --font Puhuiti.ttf --size 16 --bpp 4 \
        --symbols "登录确认取消" -o lv_font_16.c

    python lv_font_conv.py --font Puhuiti.ttf --size 16 --bpp 4 \
        --range 0x20-0x7F 0x4E00-0x9FFF -o lv_font_16.c

    python lv_font_conv.py --font Puhuiti.ttf --size 16 --bpp 1 \
        --symbols "你好世界" --format bin -o lv_font_16.bin
"""

import argparse
import os
import shutil
import subprocess
import sys

# ---------------------------------------------------------------------------
# 环境检测
# ---------------------------------------------------------------------------


def find_runner():
    """
    按优先级查找可用的调用方式。
    返回 (kind, path)：
        kind = 'exe'  → 直接用可执行文件
        kind = 'bunx' → 用 bunx 运行
        kind = 'npx'  → 用 npx 运行
    """
    # 1. 本地/全局安装的 lv_font_conv
    exe = shutil.which("lv_font_conv")
    if exe:
        return ("exe", exe)
    if sys.platform == "win32":
        exe = shutil.which("lv_font_conv.cmd")
        if exe:
            return ("exe", exe)

    # 2. bunx（Bun.js）
    bunx = shutil.which("bunx") or shutil.which("bun")
    if bunx:
        return ("bunx", bunx)

    # 3. npx（Node.js）
    npx = shutil.which("npx")
    if npx:
        return ("npx", npx)

    return (None, None)


def print_env_info(kind, path):
    """打印当前使用的运行环境"""
    labels = {
        "exe": "本地 lv_font_conv",
        "bunx": "Bun.js (bunx)",
        "npx": "Node.js (npx)",
    }
    print(f"[ENV] 使用 {labels.get(kind, '未知')}：{path}")


def check_env():
    """检查运行环境，返回 (kind, path)"""
    kind, path = find_runner()
    if kind is None:
        print("[ERROR] 未找到可用的 lv_font_conv 运行环境。", file=sys.stderr)
        print("        请安装以下任一环境：", file=sys.stderr)
        print(
            "        - Bun.js:  curl -fsSL https://bun.sh/install | bash",
            file=sys.stderr,
        )
        print("        - Node.js: npm install -g lv_font_conv", file=sys.stderr)
        sys.exit(1)
    print_env_info(kind, path)
    return (kind, path)


# ---------------------------------------------------------------------------
# 字符集读取
# ---------------------------------------------------------------------------


def read_symbols_file(path):
    """从文件读取字符集，去重并保持顺序"""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    seen = set()
    result = []
    for ch in content:
        if ch in "\r\n\t":
            continue
        if ch not in seen:
            seen.add(ch)
            result.append(ch)
    return "".join(result)


# ---------------------------------------------------------------------------
# 命令构建
# ---------------------------------------------------------------------------


def build_cmd(args, symbols):
    """构建 lv_font_conv 调用命令"""
    kind, path = check_env()

    if kind == "exe":
        cmd = [path]
    elif kind == "bunx":
        # bunx 会自动下载并运行 npm 包，--bun 强制用 bun 运行时
        if os.path.basename(path).startswith("bunx"):
            cmd = [path, "lv_font_conv"]
        else:
            # 只有 bun 没有 bunx 时用 `bun x`
            cmd = [path, "x", "lv_font_conv"]
    else:  # npx
        cmd = [path, "lv_font_conv"]

    # 必选参数
    cmd += ["--font", args.font]
    cmd += ["--size", str(args.size)]
    cmd += ["--bpp", str(args.bpp)]
    cmd += ["--format", args.format]
    cmd += ["-o", args.output]

    # 字符集
    if symbols is not None:
        cmd += ["--symbols", symbols]
    if args.range:
        for r in args.range:
            cmd += ["--range", r]

    # 渲染与压缩选项
    if args.no_compress:
        cmd += ["--no-compress"]
    if args.no_prefilter:
        cmd += ["--no-prefilter"]
    if args.lcd:
        cmd += ["--lcd"]
    if args.lcd_v:
        cmd += ["--lcd-v"]
    if args.force_fast_kern_format:
        cmd += ["--force-fast-kern-format"]
    if args.no_kerning:
        cmd += ["--no-kerning"]
    if args.keep_kerning:
        cmd += ["--keep-kerning"]

    # lvgl 特有参数
    if args.format == "lvgl":
        if args.font_name:
            cmd += ["-n", args.font_name]
        if args.size_range:
            cmd += ["--size-range", args.size_range]
        if args.lv_include:
            cmd += ["--lv-include", args.lv_include]

    # 额外参数透传
    if args.extra:
        cmd += args.extra

    return cmd


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="lv_font_conv 的 Python 封装",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("--font", required=True, help="输入字体文件（.ttf/.woff/.otf）")
    parser.add_argument("--size", type=int, required=True, help="字体像素高度")
    parser.add_argument("-o", "--output", required=True, help="输出文件路径")

    parser.add_argument("--symbols", help="直接指定字符集字符串")
    parser.add_argument("--symbols-file", help="从文件读取字符集（UTF-8）")
    parser.add_argument(
        "-r", "--range", nargs="+", help="Unicode 范围，如 0x20-0x7F 0x4E00-0x9FFF"
    )

    parser.add_argument(
        "--bpp", type=int, default=4, choices=[1, 2, 3, 4], help="位深，默认 4"
    )
    parser.add_argument(
        "--format",
        default="lvgl",
        choices=["lvgl", "bin", "dump"],
        help="输出格式，默认 lvgl",
    )
    parser.add_argument(
        "-n",
        "--font-name",
        dest="font_name",
        help="生成的 C 字体变量名（仅 lvgl 格式）",
    )
    parser.add_argument(
        "--size-range", dest="size_range", help="为多个字号生成字体，如 16,20,24"
    )
    parser.add_argument(
        "--lv-include",
        dest="lv_include",
        help="指定 lvgl.h 头文件的路径（仅与 --format lvgl 一起使用）",
    )

    parser.add_argument("--lcd", action="store_true", help="启用亚像素渲染（水平）")
    parser.add_argument("--lcd-v", action="store_true", help="启用亚像素渲染（垂直）")
    parser.add_argument("--no-compress", action="store_true", help="禁用字形压缩")
    parser.add_argument("--no-prefilter", action="store_true", help="禁用预过滤")
    parser.add_argument(
        "--force-fast-kern-format", action="store_true", help="强制使用快速字距格式"
    )
    parser.add_argument("--no-kerning", action="store_true", help="不生成字距数据")
    parser.add_argument("--keep-kerning", action="store_true", help="保留原始字距数据")

    parser.add_argument(
        "--extra", nargs=argparse.REMAINDER, help="透传给 lv_font_conv 的额外参数"
    )

    args = parser.parse_args()

    # 校验字符集
    symbols = args.symbols
    if args.symbols_file:
        symbols = read_symbols_file(args.symbols_file)

    if not symbols and not args.range:
        print(
            "[ERROR] 必须指定 --symbols、--symbols-file 或 --range 之一",
            file=sys.stderr,
        )
        sys.exit(1)

    # 校验字体文件
    if not os.path.isfile(args.font):
        print(f"[ERROR] 字体文件不存在：{args.font}", file=sys.stderr)
        sys.exit(1)

    # 构建并执行
    cmd = build_cmd(args, symbols)

    print("[CMD] " + " ".join(cmd))
    print()

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(
            f"\n[ERROR] lv_font_conv 执行失败，退出码：{e.returncode}", file=sys.stderr
        )
        sys.exit(e.returncode)
    except FileNotFoundError:
        print("[ERROR] 无法执行 lv_font_conv，请检查环境", file=sys.stderr)
        sys.exit(1)

    if os.path.isfile(args.output):
        size = os.path.getsize(args.output)
        print(f"\n[OK] 已生成：{args.output}（{size} 字节）")
    else:
        print(
            f"\n[WARN] 命令执行完成，但未找到输出文件：{args.output}", file=sys.stderr
        )


if __name__ == "__main__":
    main()
