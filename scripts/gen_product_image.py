#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
gen_product_image.py —— 抖音商品主图抓不到时，用 Qwen-Image 2.1 文生图生成商品主图。

用法：
    python gen_product_image.py <输出png> "<提示词>" [--seed 2026111101] [--w 1024] [--h 1024]

提示词要求：干净的电商主图调性（纯色背景 + 主体居中 + 自然光），不要文字/水印/卡通。
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request

COMFY = os.environ.get("COMFY_BASE", "http://127.0.0.1:8188")
T2I_UNET = os.environ.get("DPR_T2I_UNET", "qwen-image-2.1-Q5_K_M.gguf")
T2I_CLIP = os.environ.get("DPR_T2I_CLIP", "qwen3vl_8b_bf16.safetensors")
T2I_VAE = os.environ.get("DPR_T2I_VAE", "qwen_image_2.1_vae_bf16.safetensors")


def _post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def _get(url):
    return json.loads(urllib.request.urlopen(url, timeout=60).read())


def _get_raw(url):
    return urllib.request.urlopen(url, timeout=300).read()


def run_workflow(prompt, negative, width, height, seed):
    return {
        "105": {"inputs": {"unet_name": T2I_UNET}, "class_type": "UnetLoaderGGUF"},
        "106": {"inputs": {"clip_name": T2I_CLIP, "type": "qwen_image",
                           "device": "default"}, "class_type": "CLIPLoader"},
        "103": {"inputs": {"vae_name": T2I_VAE}, "class_type": "VAELoader"},
        "100": {"inputs": {"width": width, "height": height, "batch_size": 1}, "class_type": "EmptyLatentImage"},
        "102": {"inputs": {"clip": ["106", 0], "prompt": prompt, "negative_prompt": negative,
                           "resolution": max(width, height)}, "class_type": "TextEncodeQwenImage21"},
        "96": {"inputs": {"model": ["105", 0], "positive": ["102", 0], "negative": ["102", 1],
                          "latent_image": ["100", 0], "seed": seed, "steps": 25, "cfg": 1,
                          "sampler_name": "euler", "scheduler": "simple", "denoise": 1},
               "class_type": "KSampler"},
        "104": {"inputs": {"samples": ["96", 0], "vae": ["103", 0]}, "class_type": "VAEDecode"},
        "95": {"inputs": {"images": ["104", 0], "filename_prefix": "image/rec_t2i"}, "class_type": "SaveImage"},
    }


def main():
    ap = argparse.ArgumentParser(description="文生图生成商品主图")
    ap.add_argument("out", help="输出 png 路径")
    ap.add_argument("prompt", help="提示词（建议英文，电商主图调性）")
    ap.add_argument("--seed", type=int, default=2026111101)
    ap.add_argument("--w", type=int, default=1024)
    ap.add_argument("--h", type=int, default=1024)
    args = ap.parse_args()

    negative = ("text, watermark, logo, subtitles, letters, cartoon, anime, illustration, "
                "3d render, lowres, blurry, deformed hands, extra fingers, cluttered background")
    pid = _post(COMFY + "/prompt", {"prompt": run_workflow(args.prompt, negative, args.w, args.h, args.seed),
                                    "client_id": "t2i-" + hashlib.md5(str(time.time()).encode()).hexdigest()[:8]})["prompt_id"]
    deadline = time.time() + 900
    while time.time() < deadline:
        hist = _get(COMFY + "/history/" + pid)
        if hist.get(pid):
            for node in (hist[pid].get("outputs") or {}).values():
                for key in ("images", "gifs", "videos"):
                    for item in node.get(key) or []:
                        url = (COMFY + "/view?filename=" + item["filename"]
                               + "&subfolder=" + (item.get("subfolder") or "") + "&type=" + item.get("type", "output"))
                        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
                        open(args.out, "wb").write(_get_raw(url))
                        print(f"saved {args.out}")
                        return 0
            raise RuntimeError("工作流结束但没有可用产物")
        time.sleep(2)
    raise TimeoutError("等待文生图超时")


if __name__ == "__main__":
    sys.exit(main())
