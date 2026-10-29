---
name: douyin-product-rec
description: Generate ≤30s Douyin product-recommendation videos from a product link or image using local ComfyUI (Qwen-Image 2.1 + MiniMax H3). Use when the user wants a 带货/商品推荐 short video for a specific product. Not for multi-episode short dramas or general video editing.
---

# 抖音商品推荐视频

把「一个商品 + 几条剧情镜头提示词」自动变成一条竖屏带货短视频（768×1344，≤30s）。这是独立于短剧流程的单条带货片，结构固定为：

```
[ 3 段 AI 剧情镜头，不出现商品、不做卖点推销 ]  →  [ 最后 ~3.6s：商品视频镜头 + 推荐语 + 点击下方小黄车 ]
```

## 流程

1. **拿商品素材**：从抖音商品短链（`v.douyin.com/xxx`）跟 302 落地，URL 的 `goods_detail` 里有 `img.url_list`（主图 CDN）与 `min_price`。价格与用户分享文案冲突时不要标价，留空 `price`。
2. **写规格文件** `products/xx.json`：3 个剧情镜头 + 结尾商品镜头 + 推荐语。完整字段见 [references/spec_format.md](references/spec_format.md)。
3. **生成**：`python scripts/douyin_product_rec.py --spec products/xx.json`。环境依赖见 [references/environment.md](references/environment.md)。剧情镜头约 2min/镜，商品镜头约 1.5min，全流程约 10min。
4. **质检**：
   - `python scripts/check_motion.py <成片> --ends 3.6` —— 逐帧运动量检测。**核心不变量：结尾商品段必须真视频**（H3 视频 MAD≥2.5，静态推镜卡只有 ~1.4），返回 WARN 就重出商品镜头。
   - `python scripts/qc_sheet.py <成片> -o sheet.png` —— 9 宫格逐帧图，发给用户确认。
5. **交付**：`输出/卖货视频_*.mp4` + 同名 `.srt` 外挂字幕。

## 关键约束（踩过的坑）

- **结尾不能是静态照片**：默认对商品主图直接跑 MiniMax H3 生成动态商品镜头；只有生成失败才退回静态卡（`--end-mode photo` 强制）。商品镜头的动态要肉眼可见（面料飘动、光影移动）；「缓慢推镜+扫光」太含蓄，成片里仍像照片。
- **H3 跨镜头会换脸**：剧情镜一律用不露脸的细节镜头（手、脚、背影、环境），不要给同一人物正脸。
- **推荐语形态**：`<主题短句>，就选它` + CTA「点击下方小黄车」；结尾段会自动延长到话术放得下，不截断。
- **剧情段不推销**：台词只讲故事/情绪，不报价、不喊卖点；商品只在最后一段出现。
- **配音与基调匹配**：女装/童装用女声（zh-CN-XiaoxiaoNeural），男装/通用品可用男声（zh-CN-YunxiNeural）。
- **缓存按内容哈希**：关键帧、镜头、配音存在就复用；改动台词或提示词才会重生成对应段落。
