#!/usr/bin/env python3
"""音乐格式转换工具 - 支持 MP3, WAV, FLAC, OGG, M4A, WMA, AAC 等格式互转"""

import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from pydub import AudioSegment
except ImportError:
    print("正在安装依赖 pydub...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pydub"])
    from pydub import AudioSegment

SUPPORTED_FORMATS = {
    "mp3":  "mp3",
    "wav":  "wav",
    "flac": "flac",
    "ogg":  "ogg",
    "m4a":  "mp4",
    "wma":  "wma",
    "aac":  "aac",
    "opus": "opus",
    "ac3":  "ac3",
}


def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("错误: 未找到 ffmpeg。请安装 ffmpeg 并添加到 PATH。")
        print("  Windows: 下载 https://ffmpeg.org/download.html 并添加到环境变量")
        print("  macOS:   brew install ffmpeg")
        print("  Linux:   apt install ffmpeg")
        sys.exit(1)


def convert_file(src: Path, dst: Path, format: str, bitrate: str | None, quiet: bool):
    try:
        audio = AudioSegment.from_file(str(src))
        params = {}
        if format == "mp3" and bitrate:
            params["bitrate"] = bitrate
        audio.export(str(dst), format=format, **params)
        if not quiet:
            print(f"  ✓ {src.name} -> {dst.name}")
        return True, None
    except Exception as e:
        return False, f"{src.name}: {e}"


def batch_convert(
    src_dir: Path, dst_dir: Path, src_fmt: str, dst_fmt: str,
    bitrate: str | None, max_workers: int, recursive: bool, quiet: bool,
    delete_src: bool, overwrite: bool,
):
    pattern = f"**/*.{src_fmt}" if recursive else f"*.{src_fmt}"
    files = list(src_dir.glob(pattern))
    if not files:
        print(f"未找到 .{src_fmt} 文件")
        return

    dst_dir.mkdir(parents=True, exist_ok=True)
    pydub_fmt = SUPPORTED_FORMATS.get(dst_fmt, dst_fmt)
    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for src in files:
            rel = src.relative_to(src_dir)
            dst = dst_dir / rel.with_suffix(f".{dst_fmt}")
            if not overwrite and dst.exists():
                if not quiet:
                    print(f"  - 跳过 {dst.name} (已存在)")
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            futures[executor.submit(convert_file, src, dst, pydub_fmt, bitrate, quiet)] = src

        for f in as_completed(futures):
            ok, err = f.result()
            src = futures[f]
            if ok:
                results.append(("ok", src))
                if delete_src:
                    src.unlink()
            else:
                results.append(("err", src, err))

    ok_count = sum(1 for r in results if r[0] == "ok")
    err_count = sum(1 for r in results if r[0] == "err")
    print(f"\n完成: {ok_count} 成功, {err_count} 失败")


def main():
    parser = argparse.ArgumentParser(
        description="音乐格式转换工具 - 支持 MP3/WAV/FLAC/OGG/M4A 等格式互转",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  %(prog)s input.wav output.mp3\n"
            "  %(prog)s input.flac -o output.m4a\n"
            "  %(prog)s -d ./music -f flac -t mp3 --bitrate 320k\n"
            "  %(prog)s -d ./music -f wav -t flac --recursive --delete\n"
        ),
    )

    parser.add_argument("input", nargs="?", help="输入文件")
    parser.add_argument("output", nargs="?", help="输出文件")
    parser.add_argument("-d", "--dir", help="批量转换的目录")
    parser.add_argument("-f", "--from-format", help="源格式 (批量)")
    parser.add_argument("-t", "--to-format", help="目标格式", default="mp3")
    parser.add_argument("-o", "--output", help="输出文件或目录")
    parser.add_argument("-b", "--bitrate", help="比特率 (如 320k, 192k, 128k)")
    parser.add_argument("--recursive", action="store_true", help="递归子目录")
    parser.add_argument("--delete", action="store_true", dest="delete_src", help="转换后删除源文件")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的文件")
    parser.add_argument("-j", "--workers", type=int, default=4, help="并行线程数 (默认 4)")
    parser.add_argument("-q", "--quiet", action="store_true", help="静默模式")
    parser.add_argument("--list-formats", action="store_true", help="列出支持的格式")

    args = parser.parse_args()

    if args.list_formats:
        print("支持的格式:", ", ".join(sorted(SUPPORTED_FORMATS)))
        return

    check_ffmpeg()

    # 批量模式
    if args.dir:
        src_dir = Path(args.dir).resolve()
        if not src_dir.is_dir():
            print(f"错误: 目录不存在 {src_dir}")
            sys.exit(1)
        src_fmt = args.from_format
        if not src_fmt:
            print("错误: 批量模式需要指定 -f/--from-format")
            sys.exit(1)
        src_fmt = src_fmt.lstrip(".")
        dst_fmt = args.to_format.lstrip(".")
        dst_dir = Path(args.output).resolve() if args.output else src_dir / f"converted_{dst_fmt}"
        batch_convert(
            src_dir, dst_dir, src_fmt, dst_fmt,
            args.bitrate, args.workers, args.recursive,
            args.quiet, args.delete_src, args.overwrite,
        )
        return

    # 单文件模式
    if not args.input:
        parser.print_help()
        sys.exit(1)

    src = Path(args.input).resolve()
    if not src.is_file():
        print(f"错误: 文件不存在 {src}")
        sys.exit(1)

    dst = Path(args.output).resolve() if args.output else src.with_suffix(f".{args.to_format}")
    dst_fmt = dst.suffix.lstrip(".").lower()
    pydub_fmt = SUPPORTED_FORMATS.get(dst_fmt, dst_fmt)

    print(f"转换: {src.name} -> {dst.name}")
    ok, err = convert_file(src, dst, pydub_fmt, args.bitrate, args.quiet)
    if ok:
        print("完成!")
        if args.delete_src:
            src.unlink()
    else:
        print(f"失败: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
