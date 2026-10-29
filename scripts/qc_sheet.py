#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
qc_sheet.py —— 给成片生成 9 宫格逐帧质检图，肉眼快速确认结构与「结尾是视频」。

用法：
    python qc_sheet.py <video.mp4> -o 输出.png [--ends 3.6] [--cols 3] [--rows 3]
"""
import argparse
import os
import subprocess
import sys
import tempfile

_FONT_CANDIDATES = ["msyhbd.ttc", "msyh.ttf", "NotoSansCJKsc-Bold.otf",
                    "NotoSansCJK-Bold.ttc", "SourceHanSansSC-Bold.otf", "wqy-zenhei.ttc"]


def find_font():
    env = os.environ.get("DPR_FONT_BOLD")
    if env and os.path.isfile(env):
        return env
    for name in _FONT_CANDIDATES:
        for d in (r"C:\Windows\Fonts", "/usr/share/fonts", "/usr/local/share/fonts",
                  os.path.expanduser("~/.fonts")):
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return p
    return None


def main():
    ap = argparse.ArgumentParser(description="9 宫格逐帧质检图")
    ap.add_argument("video", help="成片路径")
    ap.add_argument("-o", "--out", required=True, help="输出 png 路径")
    ap.add_argument("--ends", type=float, default=3.6, help="结尾商品段秒数")
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--rows", type=int, default=3)
    args = ap.parse_args()

    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                "-of", "csv=p=0", args.video], capture_output=True, text=True).stdout.strip())
    n = args.cols * args.rows
    end_start = max(0.0, dur - args.ends)
    times, notes = [], []
    for i in range(n):
        # 前若干格均匀铺在剧情段，最后两格留给结尾商品段
        if i < n - 2:
            t = (end_start - 0.4) * (i + 0.5) / max(1, n - 2) + 0.2
            notes.append("剧情")
        else:
            t = end_start + (args.ends * 0.5 if i == n - 2 else args.ends * 0.9)
            notes.append("结尾 商品镜头")
        times.append(min(t, dur - 0.1))

    from PIL import Image, ImageDraw, ImageFont
    cell_w, cell_h, pad, label_h = 384, 672, 12, 40
    sheet = Image.new("RGB", (args.cols * cell_w + (args.cols + 1) * pad,
                              args.rows * (cell_h + label_h) + (args.rows + 1) * pad), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    font = None
    fp = find_font()
    if fp:
        font = ImageFont.truetype(fp, 24)
    tmp = tempfile.mkdtemp()
    for i, t in enumerate(times):
        p = os.path.join(tmp, f"_{i}.png")
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{t:.2f}",
                        "-i", args.video, "-frames:v", "1", "-vf", f"scale={cell_w}:{cell_h}", p], check=True)
        if not os.path.exists(p):
            continue
        r, c = divmod(i, args.cols)
        x = pad + c * (cell_w + pad)
        y = pad + r * (cell_h + label_h + pad)
        label = f"{t:.1f}s {notes[i]}"
        d.text((x + 4, y + 4), label, font=font, fill=(255, 220, 60))
        sheet.paste(Image.open(p).convert("RGB"), (x, y + label_h))
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    sheet.save(args.out)
    print(f"sheet -> {args.out}")


if __name__ == "__main__":
    sys.exit(main())
