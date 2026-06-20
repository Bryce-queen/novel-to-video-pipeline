---
name: novel-to-video-pipeline
description: >
  将长篇小说转化为结构化分镜剧本的完整流水线。六阶段：源文件加载 → 资产库建立（角色/场景/道具 dict name-keyed）→ 分集规划 → 剧本生成（shot-by-shot 结构化 JSON，narration/drama 双模式）→ 图像 Prompt 输出 → 视频合成（xfade dissolve/fade + afade 音频淡化）。v2.9.3 修正：dialogue 从 segment 级移至 video_prompt 内，对齐 ArcReel Pydantic VideoPrompt.dialogue 正典位置。
version: 2.9.3
---

# Novel-to-Video Pipeline v2.9.3

将长篇小说转化为结构化分镜剧本的完整流水线。纯文本处理由 Marvis 自闭环，图像/视频阶段输出平台无关的 prompt 与调用指令。

## 版本升级摘要

| 版本 | 核心变更 |
|------|---------|
| v2.9.2 | 修正：dialogue 从 segment/scene 级移至 video_prompt.dialogue，对齐 ArcReel Pydantic DramaScene/VideoPrompt 正典结构 |
| v2.9.1 | 修正：移除 v2.9.0 自创约束（action 最低 20 词 + ambiance_audio 必非空），对齐 ArcReel Pydantic schema — 质量约束在 prompt 层，runtime 只做结构校验 |
| v2.9.0 | narration 模式 video_prompt.action 最低 20 词 + ambiance_audio 必填（已废弃，约束无正典依据） |
| v2.8.1 | duration_seconds 按 mode 区分必填（narration 必填/drama 默认 8 可选）、版本号/SKILL.md 补齐、移除孤儿夹具 |
| v2.7 | image_prompt.composition 必填 + composition 子字段 shot_type/lighting/ambiance 必填 |
| v2.6 | narration 禁 dialogue + narration/drama 强制 characters 字段 + 旧 dialogue 键名 migration 提示 |
| v2.5 | ArcReel Pydantic 正典 schema 逐字段对齐：dialogue speaker/line、mode-specific 字段拆分、scene action verb 检测、字段集扩展 |
| v2.4 | episode_plan 顶层 extra_fields 检测，drama 模式测试夹具及校验覆盖，夹具从 7 增至 10 |
| v2.3 | `_check_extra_fields()` 全层级字段越界检测（Arcreel forbid 对齐），style 枚举校验，script_file 存在性交叉校验，FFmpeg afade 音频交叉淡化，单帧退化保护，7 夹具测试套件 |
| v2.2 | validators.py `--strict` 模式（WARN→FAIL），episode_plan↔project.json 交叉校验，xfade fade/dissolve 实现，segment_id 跳号检测，drama 模式 dialogue 结构校验 |
| v2.1 | 数据模型从数组 ID 改为 dict name-keyed，validators.py 完整重写，segment_id 正则（E{n}S{nn}），duration_seconds 1-60 约束，引用一致性校验 |

## 触发条件

用户提到"小说转视频""小说改编""生成剧本""分镜脚本""novel to video"等关键词，或直接提供小说文件要求结构化处理。

## 工作流总览

```
Stage 1: 源文件加载     →  纯文本提取
  └─ 内容模式选择       →  用户选择 narration / drama
Stage 2: 资产库建立     →  project.json（角色/场景/道具，dict name-keyed）
Stage 3: 分集规划       →  episode_plan.json
Stage 4: 剧本生成       →  逐集 episode_N.json（shot-by-shot）
  └─ 4.5: 局部编辑     →  按片段号/字段精准修改已验证剧本
Stage 5: 图像 prompt 输出 →  角色/场景/道具/分镜 prompt + 平台适配指南
Stage 6: 视频合成       →  FFmpeg xfade + afade（可选）
```

---

## 数据模型（dict name-keyed，v2.1+）

所有资产（角色/场景/道具）使用 **名称作为 key 的 dict**，而非数组 ID：

```json
{
  "characters": {
    "叶尘": {"description": "...", "voice_style": "..."},
    "柳青": {"description": "...", "voice_style": "..."}
  },
  "scenes": {
    "青云宗练武场": {"description": "..."},
    "后山瀑布": {"description": "..."}
  },
  "props": {
    "青冥剑": {"description": "..."},
    "寒玉剑": {"description": "..."}
  }
}
```

**字段约束**（v2.5 对齐 ArcReel Pydantic 正典）：
- `project.json` 顶层仅允许: `title, content_mode, style, word_count, chapter_count, characters, scenes, props, episodes`
- 角色仅允许: `description, voice_style, character_sheet, reference_image`
- 场景仅允许: `description, scene_sheet`
- 道具仅允许: `description, prop_sheet`
- narration 模式 segment 仅允许: `segment_id, duration_seconds, novel_text, characters_in_segment, scenes, props, image_prompt, video_prompt, transition_to_next, segment_break, note`（**禁止 scene_id**）
- drama 模式 scene 仅允许: `scene_id, duration_seconds, characters_in_scene, scenes, props, image_prompt, video_prompt, transition_to_next, segment_break, dialogue, note`（**禁止 segment_id**）
- image_prompt 仅允许: `scene, composition`
- composition 仅允许: `shot_type, lighting, ambiance`
- video_prompt 仅允许: `action, camera_motion, ambiance_audio, dialogue`
- dialogue 行仅允许: `speaker, line`（v2.5 对齐 ArcReel `Dialogue` 模型，原 `character/text` 已废弃）

**v2.3+ 字段检测**：`validators.py` 在所有层级运行 `_check_extra_fields()`，未知字段直接 FAIL（对齐 Arcreel `ConfigDict(extra='forbid')`）。

---

## Stage 1: 源文件加载

**输入**: 用户提供的小说文件路径（支持 .txt / .md）

**流程**:
1. 使用 `read_text` 读取全文
2. 超长文件分段读取后拼接
3. 统计字数、章节数等基础信息

**输出**: 内存中的纯文本全文 + 基础统计信息

**质量门槛**:
- 字数 ≥ 500
- 编码无乱码

**Stage 1 完成后，必须先完成「内容模式选择」，再进入 Stage 2。**

---

## 内容模式选择（Stage 1 后强制执行）

使用 `ask_user` 让用户选择：

| 模式 | content_mode | 画面结构 | 构图 | 驱动方式 |
|------|-------------|---------|------|---------|
| 说书模式 | narration | segments (segment_id) | 9:16 竖屏 | 旁白叙述 |
| 剧集动画 | drama | scenes (scene_id) | 16:9 横屏 | 角色对白 |

---

## Stage 2: 资产库建立 → project.json

**输入**: Stage 1 全文

**流程**:
1. LLM 提取角色/场景/道具，各含 `description`（中文 ≥30/20/20 字符）
2. 角色需 `voice_style`
3. 写入 `project.json`（dict name-keyed 格式）

**v2.3 新增字段**:
- `style`: 风格标签，仅允许 `水墨古风 | 赛博朋克 | 日系动画 | 写实电影 | default`
- `episodes[].script_file`: 每集对应的剧本文件名

**校验**: Stage 2 完成后立即运行 `python validators.py project project.json`

**质量门槛**:
- 至少 2 个角色
- 角色 description ≥30 中文字符
- 场景 description ≥20 中文字符
- 道具 description ≥20 中文字符

---

## Stage 3: 分集规划 → episode_plan.json

**流程**:
1. LLM 分析断点，给出分集方案
2. 使用 `ask_user` 让用户确认
3. 写入 `episode_plan.json`

**校验**: `python validators.py episode episode_plan.json <word_count> [project.json]`
- 检查 chapter_range 连续性
- 检查 key_characters / key_scenes 引用（若给定 project.json）

---

## Stage 4: 剧本生成 → episode_N.json

**逐集生成**，每集完成后立即校验:

```bash
python validators.py script project.json episode_N.json
```

**校验内容** (v2.3 全层级):
- 顶层、segment、image_prompt、composition、video_prompt、dialogue 所有层级字段越界检测
- segment_id 正则 `E{n}S{nn}` + 禁止词族扫描
- shot_type / camera_motion / transition 枚举校验
- duration_seconds 1-60 整数约束
- 角色/场景/道具引用一致性
- drama 模式 dialogue 数组结构和字段
- image_prompt.scene ≥30 单词
- 禁止词族: `陷入|回忆|思绪|意识到|画外音|BGM|精致|震撼|回忆翻涌|决心|仿佛|像蝴蝶般|suddenly realize|flashback|nostalgia|masterpiece|breathtaking`

**禁止项**:
- image_prompt / video_prompt 中禁止平台特定语法（如 `--ar`、`negative:`）
- video_prompt.ambiance_audio 禁止 BGM/配乐/画外音/旁白

### Stage 4.5: 局部编辑

已生成的 episode_N.json 可精准修改：按 segment_id 定位 → 修改指定字段 → 重新校验。

---

## Stage 5: 图像 Prompt 输出

**目录结构**:
```
prompts/
├── README.md
├── 01_characters/
├── 02_scenes/
├── 03_props/
└── 04_segments/
```

**角色设计图 prompt**: 风格前缀 + 角色 description + 16:9 四格布局（胸像特写 + 正面 / 四分之三侧面 / 背面 A-Pose）

**场景设计图 prompt**: 风格前缀 + 场景 description + 四分之三主画面 + 右下细节小图

**道具设计图 prompt**: 风格前缀 + 道具 description + 三视图

**分镜图 prompt**: `[REFERENCE IMAGES REQUIRED]` 块 + `[PROMPT]` 块（scene + composition）+ `[VIDEO PROMPT]` 块（action + camera_motion + ambiance_audio + dialogue）

**平台适配**: Gemini / OpenAI / Midjourney / ComfyUI

---

## Stage 6: 视频合成

**使用方法**:
```bash
python ffmpeg_builder.py episode_N.json images_dir \
    --audio background.mp3 \
    --output episode_N.mp4 \
    --aspect 9:16 \
    --fps 24
```

**v2.2 xfade 过渡**: fade → 0.5s 黑场淡入淡出，dissolve → 0.5s 交叉溶解

**v2.3 afade 音频淡化**: 每个过渡点对背景音频轨做 `afade` 交叉淡化，避免生硬跳变。单帧时自动退化为 concat 式覆盖。

---

## 校验命令速查

| 命令 | 用途 | v2.3 新增 |
|------|------|----------|
| `validators.py project project.json` | 校验资产库 | 字段越界 + style 枚举 |
| `validators.py episode plan.json <wc> [project.json]` | 校验分集方案 | - |
| `validators.py script project.json ep_N.json` | 校验单集剧本 | 全层级越界 |
| `validators.py crosscheck project.json scripts_dir/` | 跨集一致性 | script_file 存在性 |
| `validators.py estimate project.json` | 产出量预估 | script_file 缺失提示 |
| `--strict` | WARN 提升为 FAIL | - |

## 测试套件

```
tests/
├── run_tests.py          # 主测试脚本
├── fixtures/
│   ├── valid/            # 有效夹具（project + plan + episode_1/2/3）
│   └── invalid/          # 无效夹具（越界字段 + 禁止词 + 格式错误）
```

运行: `python tests/run_tests.py [--strict]`

## 工作目录约定

- 所有产出写入 `{output_dir}/novel-to-video/{novel_title}/`
- 中间临时文件写入 `{temp_dir}/novel-to-video/`

## 执行原则

1. **逐 Stage 推进**: 每完成一个 Stage 运行对应校验，再进入下一 Stage
2. **Stage 1-4 全自动**: 文本处理不需要用户干预
3. **Stage 5 纯输出**: 只生成 prompt 文件，不调用图像 API
4. **Stage 6 按需**: 仅当用户明确要求时执行
5. **暂停点**: >100K 字时 Stage 1 后提示确认

## 模型行为约束

- 分析小说用中文，image_prompt.scene 须英文
- 角色外貌从原文提取，不自行编造
- 原文未详述的标注"原文未详述，已基于上下文推断"
- 分集断点优先章节边界
- duration_seconds 默认 5-8 秒，对白密集可延长到 10-12 秒
- image_prompt.scene 描述静态画面，video_prompt.action 描述物理动作
*（内容由AI生成，仅供参考）*
