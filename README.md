# Novel-to-Video Pipeline

将长篇小说转化为结构化分镜剧本的完整流水线。

## 概述

纯文本处理由 Marvis 自闭环，图像/视频阶段输出平台无关的 Prompt 与 FFmpeg 合成指令，无厂商锁定。

## 六阶段流水线

1. **源文件加载** — 支持 .txt 等小说文件解析
2. **资产库建立** — 角色/场景/道具 dict name-keyed 资产表
3. **分集规划** — 按节奏切分章节，输出 episode_plan
4. **剧本生成** — shot-by-shot 结构化 JSON，支持 narration / drama 双模式
5. **图像 Prompt 输出** — 输出兼容 ArcReel / Midjourney / Stable Diffusion 的 image_prompt
6. **视频合成** — FFmpeg xfade dissolve/fade + afade 音频淡化

## 核心模块

| 文件 | 说明 |
|------|------|
| `validators.py` | 结构校验器，严格对齐 ArcReel Pydantic VideoPrompt 正典 |
| `ffmpeg_builder.py` | FFmpeg 视频合成脚本 |
| `run_tests.py` | 完整测试套件 |
| `tests/fixtures/` | 场景 fixtures |

## 剧本模式

- **narration 模式** — 旁白驱动，禁 dialogue，适合第一人称/内心叙事
- **drama 模式** — 对话驱动，含 dialogue + characters，输出 shot-by-shot 分镜

## 输出格式

每个 segment 包含：`shot_sequence` / `shot_type` / `action` / `image_prompt`（含 composition / camera_motion / ambiance_audio 等字段），严格校验字段类型与必填约束。

## 版本

当前版本：v2.9.3

**版本历史**：见 [SKILL.md](SKILL.md)
