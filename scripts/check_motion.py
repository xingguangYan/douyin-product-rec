#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
check_motion.py —— 逐帧运动量检测：验证「全片都是视频，没有静态照片段」。

用法：
    python check_motion.py <video.mp4> [video2.mp4 ...] [--ends 3.6] [--ratio 0.4] [--floor 2.0]

对每段计算相邻帧灰度平均绝对差（MAD，分辨率缩到 160x280 估算）：
    - 前段（剧情镜头）均值
    - 结尾 ends 秒（商品镜头）均值
结尾段 MAD 同时低于 floor 且低于 前段均值*ratio 时，判定为「结尾像静态照片」，
以非零返回码报警（配色：H3 真视频一般 MAD>=2.5，纯静态卡推镜只有 ~1.4）。
传入单个短镜头文件（时长不到 ends 两倍）时，整段按一个区间统计，不做判定。
"""
import argparse
import os
import subprocess
import sys
import tempfile

W, H, FPS = 160, 280, 25


def sh(args):
    p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise SystemExit("命令失败: " + " ".join(args)[:200] + "\n" + p.stderr[-500:])
    return p.stdout


def duration(path):
    return float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "csv=p=0", path]).strip() or 0)


def frame_mad(path):
    """返回相邻帧 MAD 数组（numpy 可选，不可用时退回纯 python）。"""
    raw = tempfile.NamedTemporaryFile(suffix=".bin", delete=False)
    raw.close()
    try:
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", path,
                        "-vf", f"scale={W}:{H},format=gray", "-f", "rawvideo", raw.name],
                       check=True)
        n_bytes = os.path.getsize(raw.name)
        n = n_bytes // (W * H)
        try:
            import numpy as np
            a = np.fromfile(raw.name, dtype="uint8", count=n * W * H).reshape(n, H, W).astype("float32")
            return np.abs(np.diff(a, axis=0)).mean(axis=(1, 2)).tolist()
        except ImportError:
            with open(raw.name, "rb") as fh:
                prev = None
                mads = []
                for i in range(n):
                    cur = fh.read(W * H)
                    if prev is not None:
                        mads.append(sum(abs(a - b) for a, b in zip(cur, prev)) / (W * H))
                    prev = cur
            return mads
    finally:
        try:
            os.unlink(raw.name)
        except OSError:
            pass


def seg_stats(mads, t0, t1):
    i0, i1 = int(t0 * FPS), max(int(t0 * FPS) + 2, int(t1 * FPS) - 1)
    s = mads[i0:i1]
    if not s:
        return 0.0, 0.0
    return sum(s) / len(s), max(s)


def check(path, ends, ratio, floor):
    dur = duration(path)
    if dur <= 0:
        print(f"[{os.path.basename(path)}] 无法读取时长")
        return 1
    mads = frame_mad(path)
    if len(mads) < 5:
        print(f"[{os.path.basename(path)}] 帧数太少，无法分析")
        return 1
    t_end_start = max(0.0, dur - ends)
    story_mean, story_max = seg_stats(mads, 0.0, t_end_start)
    end_mean, end_max = seg_stats(mads, t_end_start, dur)
    whole_mean, whole_max = seg_stats(mads, 0.0, dur)
    print(f"[{os.path.basename(path)}] {dur:.2f}s {len(mads)+1}帧")
    if dur < ends * 2:
        print(f"    整段 meanMAD={whole_mean:6.3f} max={whole_max:7.3f}（短镜头，不做结尾判定）")
        return 0
    print(f"    剧情段  t=0.00-{t_end_start:5.2f}  meanMAD={story_mean:6.3f} max={story_max:7.3f}")
    print(f"    结尾段  t={t_end_start:5.2f}-{dur:5.2f}  meanMAD={end_mean:6.3f} max={end_max:7.3f}")
    ok = end_mean >= floor and end_mean >= ratio * story_mean
    print(f"    判定: {'PASS 结尾是动态视频' if ok else 'WARN 结尾段太静，像是静态照片，建议重生成商品镜头'}")
    return 0 if ok else 2


def main():
    ap = argparse.ArgumentParser(description="逐帧运动量检测（防静态照片结尾）")
    ap.add_argument("videos", nargs="+", help="要检测的视频，可多个")
    ap.add_argument("--ends", type=float, default=3.6, help="结尾商品段秒数（默认 3.6）")
    ap.add_argument("--ratio", type=float, default=0.4, help="结尾 MAD 需 >= 剧情段均值*ratio")
    ap.add_argument("--floor", type=float, default=2.0, help="结尾 MAD 绝对下限")
    args = ap.parse_args()
    rc = 0
    for v in args.videos:
        rc = max(rc, check(v, args.ends, args.ratio, args.floor))
    return rc


if __name__ == "__main__":
    sys.exit(main())
