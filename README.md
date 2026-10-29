# douyin-product-rec

一个 Codex 技能（skill）+ 本地自动化管线：把抖音店铺里的商品，自动做成「剧情动画 + 结尾商品露出」的竖屏带货短视频（768×1344，≤30s，全片 AI 生成视频）。
<!-- 核心 AI 与生成管线 -->
[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![ComfyUI](https://img.shields.io/badge/ComfyUI-000000?style=for-the-badge&logo=comfyui&logoColor=white)](https://github.com/comfyanonymous/ComfyUI)
[![Qwen](https://img.shields.io/badge/Qwen--Image_2.1-6A0DAD?style=for-the-badge&logo=alibabacloud&logoColor=white)]()
[![MiniMax](https://img.shields.io/badge/MiniMax_H3-FF4500?style=for-the-badge&logo=openai&logoColor=white)]()

<!-- 音视频处理与平台 -->
[![FFmpeg](https://img.shields.io/badge/FFmpeg-007808?style=for-the-badge&logo=ffmpeg&logoColor=white)](https://ffmpeg.org/)
[![Edge TTS](https://img.shields.io/badge/Edge--TTS-0078D7?style=for-the-badge&logo=microsoft-edge&logoColor=white)]()
[![Douyin](https://img.shields.io/badge/Douyin-000000?style=for-the-badge&logo=tiktok&logoColor=white)](https://www.douyin.com/)

<!-- 项目属性 -->
[![Codex Skill](https://img.shields.io/badge/Codex_Skill-4B0082?style=for-the-badge&logo=github&logoColor=white)]()
[![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)]()
## 片子结构

```
[ 3 段 AI 剧情镜头 · 约 5.2s/镜 · 不出现商品、不做卖点推销 ]
        ↓
[ 最后 ~3.6s：商品视频镜头 + 一句主题推荐语 + 「点击下方小黄车」 ]
```

剧情段只讲故事与情绪，商品只在最后一段出现 —— 不硬广。**结尾段同样是 MiniMax H3 生成的动态视频**，不是静态商品照片。

参考视频链接：[![Douyin](https://img.shields.io/badge/Douyin-000000?style=for-the-badge&logo=tiktok&logoColor=white)](https://v.douyin.com/J09UeJsGs0o/)


## 能做什么

- 从抖音商品短链抓主图与价格（短链 302 落地后解析 `goods_detail`）
- Qwen-Image 2.1 文生图生成剧情关键帧 → MiniMax H3 参考生视频（含环境音）
- 对商品主图直接跑 H3 生成动态商品镜头（含失败时回退静态卡的兜底）
- edge-tts 中文配音（剧情段 + 结尾推荐语分开合成，按内容哈希缓存）
- ffmpeg 拼接、混音、`loudnorm` 响度归一化，输出 h264+aac 成片 + `.srt` 外挂字幕
- 逐帧运动量质检（`check_motion.py`）与 9 宫格逐帧图（`qc_sheet.py`）

## 快速开始

环境要求（ComfyUI 节点/模型清单、ffmpeg、edge-tts、中文字体）见 [references/environment.md](references/environment.md)。

```powershell
# 1) 启动 ComfyUI（127.0.0.1:8188）

# 2) 复制模板写一个商品规格
copy products\example.json products\my_product.json

# 3) 生成（约 10 分钟，RTX 5090 实测）
python scripts\douyin_product_rec.py --spec products/my_product.json

# 4) 质检
python scripts/check_motion.py 输出/卖货视频_*.mp4 --ends 3.6
python scripts/qc_sheet.py 输出/卖货视频_*.mp4 -o sheet.png --ends 3.6
```

仓库里 `products/example_dadishan.json` 是一个真实跑通的完整案例（秋冬半高领打底衫），商品图在 `输入参考图/`，可直接复现。

规格文件字段（剧情镜头、提示词写法、价格角标等）见 [references/spec_format.md](references/spec_format.md)。

想换工作目录（不把生成产物放仓库里）：

```powershell
python scripts/douyin_product_rec.py --spec products/my_product.json --root D:\shop_videos
```

模型文件名、字体路径都支持环境变量覆盖，换量化版本或非 Windows 环境不用改代码。

## 安装为 Codex 技能

```powershell
python "$env:USERPROFILE\.codex\skills\.system\skill-installer\scripts\install-skill-from-github.py" `
    --repo xingguangYan/douyin-product-rec --path . --name douyin-product-rec
```

安装后用 `$douyin-product-rec` 或直接说「帮我给这个商品做个带货视频」即可触发。

## 目录结构

```text
douyin-product-rec/
├── SKILL.md                  技能入口（Codex 读取的指令）
├── scripts/
│   ├── douyin_product_rec.py 生成主脚本
│   ├── check_motion.py       逐帧运动量检测（防静态照片结尾）
│   └── qc_sheet.py           9 宫格逐帧质检图
├── products/                 商品规格 JSON（模板 + 真实案例）
├── references/
│   ├── environment.md        ComfyUI/模型/依赖环境
│   └── spec_format.md        规格文件字段与提示词写法
├── 输入参考图/               商品主图存放处（随仓库提交）
├── agents/openai.yaml        UI 元数据
└── README.md
```

生成产物（`键帧/ 输出/ 音频/ 卡片/` 等）运行时按需创建，已 gitignore。

## 已知注意点

- **H3 跨镜头会换脸**：剧情镜一律不露脸（手、脚、背影、环境）。
- **商品镜头动态要明显**：面料飘动/光影移动这类才算视频；「缓慢推镜+扫光」太含蓄，成片里仍像照片。`check_motion.py` 会数值化地把关。
- **价格以链接结构化数据为准**，与分享文案冲突时不标价。
- ComfyUI-GGUF 依赖 `gguf` 包，多套 venv 共存时注意选对环境。
