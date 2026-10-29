# 规格文件格式（products/xx.json）

一个商品一个 JSON，脚本按 `id` 命名中间文件，按内容哈希缓存，改词自动重生成。

## 顶层字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 是 | 单字母/短串，用于中间文件名前缀（`输出/C_s1.mp4` 等） |
| `name` | 是 | 商品短名，用于成片文件名与日志 |
| `product_image` | 是 | 商品主图相对路径（相对工作目录） |
| `price` | 否 | 结尾卡右上角小角标，如 `7.59元起`；**不确定时留空**，不标虚假价格 |
| `recommend_line` | 是 | 结尾推荐语（也是口播），建议 `<主题短句>，就选它` |
| `cta` | 否 | 默认 `点击下方小黄车` |
| `voice` | 是 | edge-tts 语音名；女装/童装建议 `zh-CN-XiaoxiaoNeural`，通用品可 `zh-CN-YunxiNeural` |
| `voice_rate` | 否 | 剧情台词语速，默认 `+0%` |
| `end_voice_rate` | 否 | 推荐语单独提速（如 `+25%`），保证挤进 3 秒档 |
| `end_seconds` | 否 | 结尾商品段基础时长，默认 `3.5`；脚本会自动延长到话术放得下（发声时长 + 0.35s） |
| `end_vo` | 是 | 结尾配音缓存路径，如 `音频/C_end.mp3` |
| `end_clip` | 否 | 结尾商品视频镜头缓存路径，如 `输出/C_end.mp4`；不存在时自动生成 |
| `end_seed` | 否 | 商品镜头随机种子 |
| `end_motion_prompt` | 是 | 商品主图图生视频提示词（见下） |
| `end_mode` | 否 | `video`（默认，H3 商品视频）/ `photo`（静态商品卡） |
| `output` | 是 | 成片文件名，如 `卖货视频_C_秋冬半高领打底衫.mp4` |
| `negative` | 否 | 文生图负向提示词，默认带排除文字/卡通/低质 |
| `shots` | 是 | 3 段剧情镜头（见下） |

## 剧情镜头 shots[]

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 是 | `s1`/`s2`/`s3`，用于配音文件名 |
| `seed` | 否 | 关键帧与镜头随机种子 |
| `keyframe` | 是 | 关键帧缓存路径，如 `键帧/C1.png` |
| `clip` | 是 | 镜头缓存路径，如 `输出/C_s1.mp4` |
| `keyframe_prompt` | 条件必填 | 关键帧不存在时才用，文生图提示词（建议英文，9:16 竖屏构图） |
| `motion_prompt` | 是 | H3 参考生视频提示词（见下） |
| `vo` | 是 | 该镜头口播台词 |

## 提示词写法

脚本会在 `motion_prompt` 前自动拼接三段前缀：

1. `NO_TEXT`：禁止画面出现任何文字/字幕/水印
2. `AMBIENT`：只保留环境音、无人声
3. `LOOK`：电影级真实竖屏质感

所以 `motion_prompt` 本身只要写：

- 第一句用 `<Picture 1>` 指代关键帧内容（"shows a woman's hands gripping her coat collar..."）
- `Timeline 0-5s:` 之后的动作描述：**动作要具体、肉眼可见**（手部动作、布料飘动、落叶、呼吸），别只写"缓慢推镜"
- 收尾固定句：`Keep the ... exactly as in <Picture 1>.` 锁定人物/服装/光影不漂移
- 露脸限制：剧情镜一律不露脸（`No face in frame.` / 只拍手、脚、背影、环境）——H3 跨镜头会换脸

**商品镜头 `end_motion_prompt`** 同理，直接描述商品主图里的实物，动态要明显（面料被微风吹起、褶皱飘动、光影扫过），并锁定 `Keep the garment's exact shape, color, collar, folds and fabric exactly as in <Picture 1>.` 太含蓄的"缓慢推镜+扫光"在成片里仍像照片。
