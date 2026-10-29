#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
抖音商品推荐视频 · 自动生成器  (douyin-product-rec)
=================================================
独立于短剧流程（short-drama / series_run / 壮哥的酒馆 那条线）。
本脚本只做一种片子：**剧情片段 + 最后 3 秒商品卡** 的商品推荐短视频。

结构固定为：
    [若干段 AI 剧情镜头（不含商品推广）]  ->  [最后 ~3 秒：商品视频镜头 + 推荐语 + 点击下方小黄车]

结尾段同样是对商品主图跑 MiniMax H3 图生视频得到的动态镜头，
不再使用静态商品照片，保证全片每一帧都是视频。

用法：
    python douyin_product_rec.py --spec products/A.json
    python douyin_product_rec.py --spec products/A.json --force-clips   # 重出剧情镜头
    python douyin_product_rec.py --spec products/C.json --end-mode photo  # 结尾退回静态卡

依赖：本机 ComfyUI(8188) 已起，ffmpeg/ffprobe 在 PATH，edge-tts 可用。

模型文件名与字体路径都做了自动探测/环境变量覆盖，换量化版本或非 Windows
环境时不用改代码，详见 references/environment.md。
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # scripts/ 的上一层（仓库/工作目录根）
COMFY = os.environ.get("COMFY_BASE", "http://127.0.0.1:8188")
FF = "ffmpeg"
FPS = 25
W, H = 768, 1344
KEY_W, KEY_H = 832, 1216
CLIP_FRAMES = 124          # H3 单镜帧数 @24fps ≈ 5.17s

# ComfyUI 模型文件名（可用同名环境变量覆盖，适配不同量化版本）
MODELS = {
    "t2i_unet": os.environ.get("DPR_T2I_UNET", "qwen-image-2.1-Q8_0.gguf"),
    "t2i_clip": os.environ.get("DPR_T2I_CLIP", "qwen3vl_8b_bf16.safetensors"),
    "t2i_vae": os.environ.get("DPR_T2I_VAE", "qwen_image_2.1_vae_bf16.safetensors"),
    "r2v_unet": os.environ.get("DPR_R2V_UNET", "minimax_h3_fl2va_pruned_int8_convrot.safetensors"),
    "r2v_clip": os.environ.get("DPR_R2V_CLIP",
                               "qwen3vl_32b_h3_ultra_uncensored_heretic_int8_convrot.safetensors"),
    "r2v_vae": os.environ.get("DPR_R2V_VAE", "minimax_h3_video_vae_fp16.safetensors"),
    "r2v_vaea": os.environ.get("DPR_R2V_VAEA", "minimax_h3_audio_vae_fp32.safetensors"),
}

_FONT_CANDIDATES = {
    "bold": ["msyhbd.ttc", "msyh.ttf", "NotoSansCJKsc-Bold.otf", "NotoSansCJK-Bold.ttc",
             "SourceHanSansSC-Bold.otf", "wqy-zenhei.ttc"],
    "regular": ["msyh.ttc", "msyh.ttf", "NotoSansCJKsc-Regular.otf", "NotoSansCJK-Regular.ttc",
                "SourceHanSansSC-Regular.otf", "wqy-zenhei.ttc"],
}


def resolve_font(kind="bold"):
    """按环境变量 -> Windows -> Linux 常见字体目录的顺序找一个可用中文字体。"""
    env = os.environ.get("DPR_FONT_BOLD" if kind == "bold" else "DPR_FONT")
    if env and os.path.isfile(env):
        return env
    dirs = [r"C:\Windows\Fonts", "/usr/share/fonts", "/usr/local/share/fonts",
            os.path.expanduser("~/.fonts")]
    for name in _FONT_CANDIDATES[kind]:
        for d in dirs:
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return p
    return _FONT_CANDIDATES[kind][0]   # 兜底：交给 PIL 抛可读错误

NO_TEXT = ("CRITICAL — NO ON-SCREEN TEXT OF ANY KIND: no subtitles, caption bars, "
           "written dialogue, letters or typography anywhere in the frame. ")
AMBIENT = "All audio is ambient sound only, no speech. "
LOOK = "Cinematic photorealistic live-action vertical 9:16 footage. "


# ---------------------------------------------------------------- ComfyUI

def _post(url, body):
    import urllib.request
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def _get(url):
    import urllib.request
    return json.loads(urllib.request.urlopen(url, timeout=60).read())


def upload_image(path):
    import urllib.request, uuid
    name = "rec_" + re.sub(r"[^\w.\-]", "_", os.path.basename(path))
    boundary = "----rec" + uuid.uuid4().hex
    body = b""
    body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; "
             f"filename=\"{name}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode()
    body += open(path, "rb").read() + b"\r\n"
    body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\n"
             f"true\r\n--{boundary}--\r\n").encode()
    req = urllib.request.Request(COMFY + "/upload/image", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    urllib.request.urlopen(req, timeout=120).read()
    return name


def t2i_workflow(prompt, negative, width, height, seed):
    return {
        "105": {"inputs": {"unet_name": MODELS["t2i_unet"]}, "class_type": "UnetLoaderGGUF"},
        "106": {"inputs": {"clip_name": MODELS["t2i_clip"], "type": "qwen_image",
                           "device": "default"}, "class_type": "CLIPLoader"},
        "103": {"inputs": {"vae_name": MODELS["t2i_vae"]}, "class_type": "VAELoader"},
        "100": {"inputs": {"width": width, "height": height, "batch_size": 1}, "class_type": "EmptyLatentImage"},
        "102": {"inputs": {"clip": ["106", 0], "prompt": prompt, "negative_prompt": negative,
                           "resolution": max(width, height)}, "class_type": "TextEncodeQwenImage21"},
        "96": {"inputs": {"model": ["105", 0], "positive": ["102", 0], "negative": ["102", 1],
                          "latent_image": ["100", 0], "seed": seed, "steps": 25, "cfg": 1,
                          "sampler_name": "euler", "scheduler": "simple", "denoise": 1}, "class_type": "KSampler"},
        "104": {"inputs": {"samples": ["96", 0], "vae": ["103", 0]}, "class_type": "VAEDecode"},
        "95": {"inputs": {"images": ["104", 0], "filename_prefix": "image/rec_t2i"}, "class_type": "SaveImage"},
    }


def r2v_workflow(prompt, ref_images, width, height, frames, seed):
    wf = {
        "2": {"inputs": {"clip": ["13", 0], "vae": ["11", 0], "audio_vae": ["24", 0], "prompt": prompt,
                         "width": width, "height": height, "length": frames, "ref_image_size": "max"},
              "class_type": "MiniMaxH3ReferenceToVideo"},
        "6": {"inputs": {"unet_name": MODELS["r2v_unet"], "weight_dtype": "default"},
              "class_type": "UNETLoader"},
        "9": {"inputs": {"model": ["200", 0], "scheduler": "simple", "steps": 20, "denoise": 1},
              "class_type": "BasicScheduler"},
        "10": {"inputs": {"samples": ["14", 0], "vae": ["11", 0]}, "class_type": "VAEDecode"},
        "11": {"inputs": {"vae_name": MODELS["r2v_vae"]}, "class_type": "VAELoader"},
        "12": {"inputs": {"video": ["91", 0], "filename_prefix": "video/rec_r2v", "format": "auto",
                          "codec": "auto"}, "class_type": "SaveVideo"},
        "13": {"inputs": {"clip_name": MODELS["r2v_clip"], "type": "minimax",
                          "device": "default"}, "class_type": "CLIPLoader"},
        "14": {"inputs": {"noise": ["15", 0], "guider": ["16", 0], "sampler": ["17", 0],
                          "sigmas": ["9", 0], "latent_image": ["2", 1]}, "class_type": "SamplerCustomAdvanced"},
        "15": {"inputs": {"noise_seed": seed}, "class_type": "RandomNoise"},
        "16": {"inputs": {"model": ["200", 0], "conditioning": ["2", 0]}, "class_type": "BasicGuider"},
        "17": {"inputs": {"sampler_name": "res_multistep"}, "class_type": "KSamplerSelect"},
        "23": {"inputs": {"samples": ["14", 0], "vae": ["24", 0]}, "class_type": "VAEDecodeAudio"},
        "24": {"inputs": {"vae_name": MODELS["r2v_vaea"]}, "class_type": "VAELoader"},
        "91": {"inputs": {"images": ["10", 0], "audio": ["23", 0], "fps": 24, "bit_depth": "auto",
                          "color_space": "sRGB", "codec": "none"}, "class_type": "CreateVideo"},
        "128": {"inputs": {"model": ["148", 0], "attention": "comfy kitchen attention"},
                "class_type": "ModelAttentionBackend"},
        "148": {"inputs": {"model": ["6", 0], "shift_video": 10, "shift_audio": 3},
                "class_type": "MiniMaxH3SigmaShift"},
        "200": {"inputs": {"model": ["128", 0], "mode": "H3 Fast — 0.10 / max 2", "threshold": 0.1,
                           "start_percent": 0.1, "end_percent": 0.95, "max_consecutive_hits": 2,
                           "temporal_guard": False}, "class_type": "ApplyMiniMaxH3FirstBlockCache"},
    }
    if ref_images:
        arr = []
        for i, fn in enumerate(ref_images):
            nid = str(1000 + i)
            wf[nid] = {"inputs": {"image": fn}, "class_type": "LoadImage"}
            arr.append([nid, 0])
        wf["2"]["inputs"]["ref_images"] = arr
    return wf


def run_workflow(wf, out_path, timeout_s=2400):
    pid = _post(COMFY + "/prompt", {"prompt": wf, "client_id": "rec-" + hashlib.md5(str(time.time()).encode()).hexdigest()[:8]})["prompt_id"]
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        hist = _get(COMFY + "/history/" + pid)
        if hist.get(pid):
            entry = hist[pid]
            if (entry.get("status") or {}).get("status_str") == "error":
                raise RuntimeError("ComfyUI 执行错误: " + json.dumps(entry.get("status"), ensure_ascii=False)[:800])
            for node in (entry.get("outputs") or {}).values():
                for key in ("images", "gifs", "videos"):
                    for item in node.get(key) or []:
                        url = (COMFY + "/view?filename=" + item["filename"]
                               + "&subfolder=" + (item.get("subfolder") or "") + "&type=" + item.get("type", "output"))
                        data = _get_raw(url)
                        os.makedirs(os.path.dirname(out_path), exist_ok=True)
                        open(out_path, "wb").write(data)
                        return out_path
            raise RuntimeError("工作流结束但没有可用产物")
        time.sleep(2)
    raise TimeoutError("等待 ComfyUI 超时")


def _get_raw(url):
    import urllib.request
    return urllib.request.urlopen(url, timeout=300).read()


# ---------------------------------------------------------------- helpers

def sh(args, check=True):
    p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        print("命令失败:", " ".join(args)[:300], "\n", p.stderr[-1500:])
        raise SystemExit(1)
    return p.stdout


def duration(path):
    return float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "csv=p=0", path]).strip())


def speech_end(path):
    """实际发声结束时间（去掉 TTS 末尾的静音），避免结尾多出一大截空白。"""
    p = subprocess.run([FF, "-hide_banner", "-i", path, "-af", "silencedetect=n=-45dB:d=0.15",
                        "-f", "null", "-"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    total = duration(path)
    log = (p.stderr or "") + (p.stdout or "")
    starts = [float(x) for x in re.findall(r"silence_start:\s*([0-9.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([0-9.]+)", log)]
    if starts and ends and abs(ends[-1] - total) < 0.3 and starts[-1] > 0.4:
        return starts[-1]
    return total


def tts(text, out_mp3, voice, rate):
    key = hashlib.md5((voice + "|" + rate + "|" + text).encode("utf-8")).hexdigest()
    meta = out_mp3 + ".key"
    if (os.path.exists(out_mp3) and os.path.exists(meta)
            and open(meta, encoding="utf-8").read().strip() == key):
        return out_mp3
    os.makedirs(os.path.dirname(out_mp3), exist_ok=True)
    err = ""
    for attempt in range(4):
        p = subprocess.run([sys.executable, "-m", "edge_tts", "--voice", voice, "--rate", rate,
                            "--text", text, "--write-media", out_mp3],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if p.returncode == 0 and os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 512:
            open(meta, "w", encoding="utf-8").write(key)
            return out_mp3
        err = (p.stderr or "")[-400:]
        time.sleep(2 + attempt * 2)
    raise SystemExit("edge-tts 合成失败: " + text[:20] + " | " + err)


# ---------------------------------------------------------------- endcard

def build_endcard(spec, out_card, out_ov):
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
    os.makedirs(os.path.dirname(out_card) or ".", exist_ok=True)
    img = Image.open(os.path.join(ROOT, spec["product_image"])).convert("RGB")
    bg = img.copy()
    r = max(W / bg.width, H / bg.height)
    bg = bg.resize((int(bg.width * r + 1), int(bg.height * r + 1)), Image.LANCZOS)
    bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2,
                  (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
    bg = ImageEnhance.Brightness(bg.filter(ImageFilter.GaussianBlur(52))).enhance(0.5)
    canvas = bg.convert("RGBA")

    fg = img.copy()
    box = (660, 660)
    k = min(box[0] / fg.width, box[1] / fg.height)
    fg = fg.resize((int(fg.width * k), int(fg.height * k)), Image.LANCZOS)
    mask = Image.new("L", fg.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, fg.width - 1, fg.height - 1], 26, fill=255)
    fg = fg.convert("RGBA"); fg.putalpha(mask)
    sh_img = Image.new("RGBA", (fg.width + 80, fg.height + 80), (0, 0, 0, 0))
    ImageDraw.Draw(sh_img).rounded_rectangle([40, 40, 40 + fg.width, 40 + fg.height], 26, fill=(0, 0, 0, 150))
    sh_img = sh_img.filter(ImageFilter.GaussianBlur(26))
    cy = 470
    canvas.alpha_composite(sh_img, (W // 2 - sh_img.width // 2, cy - sh_img.height // 2 + 18))
    canvas.alpha_composite(fg, (W // 2 - fg.width // 2, cy - fg.height // 2))
    canvas.convert("RGB").save(out_card)

    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    grad = Image.new("L", (1, 560))
    for i in range(560):
        grad.putpixel((0, i), int(215 * (i / 559) ** 1.4))
    sc = Image.new("RGBA", (W, 560), (0, 0, 0, 255)); sc.putalpha(grad.resize((W, 560)))
    ov.alpha_composite(sc, (0, H - 560))

    def tw(s, f):
        b = d.textbbox((0, 0), s, font=f, stroke_width=0)
        return b[2] - b[0], b[3] - b[1]

    if spec.get("price"):
        f = ImageFont.truetype(resolve_font("bold"), 40)
        s = spec["price"]
        w_, h_ = tw(s, f)
        d.rounded_rectangle([W - w_ - 76, 84, W - 32, 84 + h_ + 34], 18, fill=(255, 64, 96, 255))
        d.text((W - w_ - 54, 100), s, font=f, fill=(255, 255, 255, 255))

    line = spec["recommend_line"]
    f = ImageFont.truetype(resolve_font("bold"), 62)
    # 简单折行
    rows, cur = [], ""
    for ch in line:
        if tw(cur + ch, f)[0] > W - 130:
            rows.append(cur); cur = ch
        else:
            cur += ch
    if cur:
        rows.append(cur)
    y = H - 420
    for row in rows[:2]:
        w_, _ = tw(row, f)
        d.text(((W - w_) / 2, y), row, font=f, fill=(255, 255, 255, 255),
               stroke_width=8, stroke_fill=(12, 12, 16, 255))
        y += 84
    f2 = ImageFont.truetype(resolve_font("bold"), 46)
    cta = spec.get("cta", "点击下方小黄车")
    w2, h2 = tw(cta, f2)
    cx = (W - w2) / 2
    d.rounded_rectangle([cx - 36, y + 24, cx + w2 + 36, y + h2 + 82], 24, fill=(255, 64, 96, 255))
    d.text((cx, y + 42), cta, font=f2, fill=(255, 255, 255, 255))
    ov.save(out_ov)
    return out_card, out_ov


# ---------------------------------------------------------------- assemble

def card_segment(card, ov, dur, out):
    n = max(2, int(dur * FPS))
    vf = (f"[0:v]scale=1536:2688,zoompan=z='min(1+0.06*on/{n},1.06)'"
          f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS},setsar=1[bg];"
          f"[bg][1:v]overlay=0:0,format=yuv420p[v]")
    sh([FF, "-y", "-hide_banner", "-loglevel", "error", "-loop", "1", "-i", card, "-loop", "1", "-i", ov,
        "-filter_complex", vf, "-map", "[v]", "-t", str(dur), "-r", str(FPS),
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high",
        "-pix_fmt", "yuv420p", "-an", out])


def end_segment(src, ov, dur, out):
    """结尾商品段：H3 商品动态视频 + 渐入文字卡，整段保持真实视频（非静态照片）。"""
    n = max(2, int(dur * FPS))
    vf = (f"[0:v]scale=1536:2688:force_original_aspect_ratio=increase,crop=1536:2688,fps={FPS},"
          f"zoompan=z='min(1+0.035*on/{n},1.035)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
          f":d=1:s={W}x{H}:fps={FPS},setsar=1[bg];"
          f"[1:v]format=rgba,fade=in:st=0.2:d=0.5:alpha=1[ov];"
          f"[bg][ov]overlay=0:0:format=auto,format=yuv420p[v]")
    sh([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", src, "-loop", "1", "-i", ov,
        "-filter_complex", vf, "-map", "[v]", "-t", str(dur), "-r", str(FPS),
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high",
        "-pix_fmt", "yuv420p", "-an", out])


def clip_segment(src, out):
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1,format=yuv420p")
    sh([FF, "-y", "-hide_banner", "-loglevel", "error", "-i", src, "-vf", vf, "-r", str(FPS),
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high",
        "-pix_fmt", "yuv420p", "-an", out])


def assemble(spec, clip_paths, vo_paths, end_mode, end_src, end_card, end_ov, end_seconds, out_mp4):
    tmp = os.path.join(ROOT, "_build")
    os.makedirs(tmp, exist_ok=True)
    sid = spec["id"]
    segs = []
    for i, c in enumerate(clip_paths):
        p = os.path.join(tmp, f"{sid}_seg{i+1}.mp4")
        clip_segment(c, p); segs.append(p)
    p = os.path.join(tmp, f"{sid}_seg_end.mp4")
    if end_mode == "video":
        end_segment(end_src, end_ov, end_seconds, p)
    else:
        card_segment(end_card, end_ov, end_seconds, p)
    segs.append(p)

    lst = os.path.join(tmp, f"{sid}_list.txt")
    open(lst, "w", encoding="utf-8").write("".join("file '" + s.replace("\\", "/") + "'\n" for s in segs))
    base = os.path.join(tmp, f"{sid}_base.mp4")
    sh([FF, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
        "-i", lst, "-c", "copy", base])

    durs = [duration(s) for s in segs]
    total = sum(durs)
    starts, acc = [], 0.0
    for dd in durs:
        starts.append(acc); acc += dd

    inputs, parts, labels = [], [], []
    for i, c in enumerate(clip_paths):                      # H3 环境音做底
        inputs += ["-i", c]
        off = int(round(starts[i] * 1000))
        parts.append(f"[{len(inputs)//2-1}:a]volume=0.30,adelay={off}|{off}[amb{i}]")
        labels.append(f"[amb{i}]")
    for i, v in enumerate(vo_paths):                        # 每段台词
        inputs += ["-i", v]
        off = int(round((starts[i] + 0.45) * 1000))
        parts.append(f"[{len(inputs)//2-1}:a]volume=1.0,adelay={off}|{off}[vo{i}]")
        labels.append(f"[vo{i}]")
    idx = len(inputs) // 2
    inputs += ["-i", os.path.join(ROOT, spec["end_vo"])]     # 结尾推荐语
    off = int(round((starts[-1] + 0.12) * 1000))
    parts.append(f"[{idx}:a]volume=1.08,adelay={off}|{off}[voend]")
    labels.append("[voend]")
    parts.append("".join(labels) + f"amix=inputs={len(labels)}:duration=longest[mix]")
    parts.append("[mix]volume=6,loudnorm=I=-15:TP=-1.5:LRA=11[aout]")

    sh([FF, "-y", "-hide_banner", "-loglevel", "error"] + inputs +
       ["-i", base, "-filter_complex", ";".join(parts),
        "-map", f"{len(inputs)//2}:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-t", f"{total:.3f}", "-movflags", "+faststart", out_mp4])
    return total


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="抖音商品推荐视频自动生成器")
    ap.add_argument("--spec", required=True, help="商品规格 JSON")
    ap.add_argument("--force-clips", action="store_true", help="忽略已有镜头，全部重出")
    ap.add_argument("--skip-generate", action="store_true", help="只做卡片与合成，不调 ComfyUI")
    ap.add_argument("--end-mode", choices=["video", "photo"], default=None,
                    help="强制结尾方式：video=H3 商品视频（默认），photo=静态商品卡")
    ap.add_argument("--root", default=None,
                    help="工作目录（默认脚本所在目录）；规格文件与媒体产物的相对路径都基于此目录")
    args = ap.parse_args()

    global ROOT
    if args.root:
        ROOT = os.path.abspath(args.root)
        os.makedirs(ROOT, exist_ok=True)
    spec = json.load(open(os.path.join(ROOT, args.spec), encoding="utf-8"))
    sid = spec["id"]
    print(f"=== {sid} {spec['name']} ===")

    clip_paths, vo_paths = [], []
    for shot in spec["shots"]:
        key = os.path.join(ROOT, shot["keyframe"])
        clip = os.path.join(ROOT, shot["clip"])
        if args.force_clips or not os.path.exists(clip):
            if not os.path.exists(key):
                if args.skip_generate:
                    raise SystemExit(f"缺少关键帧 {key}")
                print("  文生图", shot["id"])
                run_workflow(t2i_workflow(shot["keyframe_prompt"], shot.get("negative", spec.get("negative", "")),
                                          KEY_W, KEY_H, shot.get("seed", 2026101100)), key)
            print("  参考生视频", shot["id"])
            fn = upload_image(key)
            run_workflow(r2v_workflow(NO_TEXT + AMBIENT + LOOK + shot["motion_prompt"],
                                      [fn], W, H, CLIP_FRAMES, shot.get("seed", 2026101100) + 1), clip)
        clip_paths.append(clip)
        vo_paths.append(tts(shot["vo"], os.path.join(ROOT, "音频", f"{sid}_{shot['id']}.mp3"),
                            spec["voice"], spec.get("voice_rate", "+0%")))

    end_vo = tts(spec["recommend_line"] + "。" + spec.get("cta", "点击下方小黄车"),
                 os.path.join(ROOT, spec["end_vo"]), spec["voice"],
                 spec.get("end_voice_rate", spec.get("voice_rate", "+0%")))
    vo_paths_end = end_vo

    card = os.path.join(ROOT, "卡片", f"{sid}_end.png")
    ov_card = os.path.join(ROOT, "卡片", f"{sid}_end_ov.png")
    build_endcard(spec, card, ov_card)

    # 结尾商品镜头：对商品主图直接跑图生视频，保证全片都是视频（失败退回静态卡）
    end_mode = args.end_mode or spec.get("end_mode", "video")
    end_clip = os.path.join(ROOT, spec.get("end_clip", f"输出/{sid}_end.mp4"))
    if end_mode == "video":
        if not os.path.exists(end_clip) and args.skip_generate:
            print("  未找到商品视频且 --skip-generate，结尾退回静态卡")
            end_mode = "photo"
        elif args.force_clips or not os.path.exists(end_clip):
            print("  商品镜头 图生视频")
            try:
                fn = upload_image(os.path.join(ROOT, spec["product_image"]))
                run_workflow(r2v_workflow(NO_TEXT + AMBIENT + LOOK + spec["end_motion_prompt"],
                                          [fn], W, H, CLIP_FRAMES, spec.get("end_seed", 2026103001)),
                             end_clip)
            except Exception as e:
                print(f"  !! 商品视频生成失败：{e}　结尾退回静态卡")
                end_mode = "photo"
        if end_mode == "video" and not os.path.exists(end_clip):
            end_mode = "photo"

    # 结尾卡至少要比推荐语长 0.25s，避免话术被截断
    end_seconds = max(spec.get("end_seconds", 3.5), speech_end(end_vo) + 0.35)
    print(f"  结尾商品镜头({end_mode}) {end_seconds:.2f}s（推荐语发声 {speech_end(end_vo):.2f}s）")
    out_mp4 = os.path.join(ROOT, "输出", spec["output"])
    os.makedirs(os.path.dirname(out_mp4), exist_ok=True)
    total = assemble(spec, clip_paths, vo_paths, end_mode, end_clip, card, ov_card, end_seconds, out_mp4)
    print(f"完成 {out_mp4}  时长 {total:.2f}s")


if __name__ == "__main__":
    main()
