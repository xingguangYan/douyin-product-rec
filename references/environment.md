# 运行环境

本管线全部本地生成，不调云端 API。需要四样东西：ComfyUI（带指定模型与节点）、ffmpeg/ffprobe、edge-tts、一个中文字体。

## ComfyUI

- 地址 `http://127.0.0.1:8188`（可用环境变量 `COMFY_BASE` 覆盖）
- 必装自定义节点：
    - `ComfyUI-GGUF`（提供 `UnetLoaderGGUF`）
    - MiniMax H3 节点包（如 `ComfyUI-MiniMaxH3-FirstBlockCache` / `comfyui-AICG3D-SKILLS`，提供 `MiniMaxH3ReferenceToVideo`、`MiniMaxH3SigmaShift`、`ModelAttentionBackend`、`ApplyMiniMaxH3FirstBlockCache`）
- 启动：
    ```powershell
    cd <ComfyUI 目录>
    .\.venv\Scripts\python.exe main.py --port 8188 --listen 127.0.0.1
    ```

**坑**：ComfyUI-GGUF 依赖 Python 包 `gguf`。启动日志若出现 `ModuleNotFoundError: No module named 'gguf'`，文生图会因 `UnetLoaderGGUF` 缺失而失败。同一台机器装多套 venv 时，先 `python -c "import gguf"` 确认哪套能用，缺就 `pip install gguf`。生成前可请求 `GET /object_info` 确认 `UnetLoaderGGUF` 在节点列表里。

## 模型

默认文件名如下，可用环境变量覆盖（适配其他量化版本）：

| 用途 | 默认文件名 | 环境变量 |
| --- | --- | --- |
| 文生图 unet | `qwen-image-2.1-Q8_0.gguf` | `DPR_T2I_UNET` |
| 文生图 clip | `qwen3vl_8b_bf16.safetensors` | `DPR_T2I_CLIP` |
| 文生图 vae | `qwen_image_2.1_vae_bf16.safetensors` | `DPR_T2I_VAE` |
| 图生视频 unet | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | `DPR_R2V_UNET` |
| 图生视频 clip | `qwen3vl_32b_h3_ultra_uncensored_heretic_int8_convrot.safetensors` | `DPR_R2V_CLIP` |
| 图生视频 vae | `minimax_h3_video_vae_fp16.safetensors` | `DPR_R2V_VAE` |
| 图生视频音频 vae | `minimax_h3_audio_vae_fp32.safetensors` | `DPR_R2V_VAEA` |

显存参考：RTX 5090 32GB 单镜（124 帧 768×1344）约 2 分钟，文生图约 20 秒/张。

## 其他

- **ffmpeg / ffprobe** 在 PATH。
- **edge-tts**：`pip install edge-tts`，中文语音常用 `zh-CN-YunxiNeural`（男）与 `zh-CN-XiaoxiaoNeural`（女）。
- **中文字体**：自动探测微软雅黑 / Noto Sans CJK / 思源黑体 / 文泉驿正黑，可用 `DPR_FONT` / `DPR_FONT_BOLD` 指定具体 ttc 路径。
- **网络**：模型与节点都在本地；从国内访问 GitHub 需自带代理（如本机 Clash），git 与 API 请求要走代理。
