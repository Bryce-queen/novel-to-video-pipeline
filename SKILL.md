---
name: novel-to-video-pipeline
description: 将长篇小说转化为结构化分镜剧本的完整流水线。ArcReel 数据模型对齐，含 Python 校验、分段策略、跨集一致性检查、FFmpeg 合成。
---

# Novel-to-Video Pipeline v2.1.0

将长篇小说转化为结构化分镜剧本的完整流水线。纯文本处理由 Marvis 自闭环，图像/视频阶段输出平台无关的 prompt。

**v2.1 数据模型完全对齐 ArcReel project.json schema**：
角色/场景/道具用 **dict（name-keyed）** 而非数组 ID；
segment_id 强制 `E{n}S{nn}` 格式；
引用字段（characters_in_segment/scenes/props）存的是**名称**而非 ID。

## 触发条件

用户提到"小说转视频""小说改编""生成剧本""分镜脚本""novel to video"等关键词。

## 工作流总览

```
Stage 1:   源文件加载      →  read_text + 字数统计
Stage 1.5: 内容模式选择    →  ask_user (narration / drama)
Stage 2:   资产库建立      →  LLM 提取 → validators.py project 校验 → 产出量预估
Stage 3:   分段分集规划    →  LLM 分析 → validators.py episode 校验 → 用户确认
Stage 4:   分批剧本生成    →  逐批 LLM 生成 → validators.py script 逐集校验 →
                             validators.py crosscheck 跨集一致性 → 用户确认
Stage 4.5: 局部编辑(可选) →  用户指哪改哪，改后重跑对应校验
Stage 5:   图像 Prompt 输出 →  prompt 文件生成
Stage 6:   视频合成(可选)  →  ffmpeg_builder.py
```

**每 Stage 产出 JSON 后必须跑对应校验命令，不通过不进入下一 Stage。**

---

## 数据模型（v2.1 重写——对齐 ArcReel）

### project.json 结构

```json
{
  "title": "小说名",
  "content_mode": "narration",
  "style": "水墨古风",
  "word_count": 150000,
  "chapter_count": 120,
  "characters": {
    "叶辰": {
      "description": "外貌、性格、服装等详细描述...",
      "voice_style": "低沉磁性嗓音"
    },
    "林婉儿": {
      "description": "外貌、性格、服装等详细描述..."
    }
  },
  "scenes": {
    "青云宗大殿": {
      "description": "场景视觉描述：建筑风格、光线、氛围..."
    },
    "后山药园": {
      "description": "场景视觉描述..."
    }
  },
  "props": {
    "玄铁剑": {
      "description": "道具外观描述..."
    }
  },
  "episodes": [
    {
      "episode": 1,
      "title": "陨落的天才",
      "chapter_range": [1, 5],
      "script_file": "episode_1.json",
      "summary": "..."
    }
  ]
}
```

**关键约束**：
- `characters` / `scenes` / `props` 的 key 是资产名称，value 包含 `description`（必填，非空字符串）
- `characters.*.description` 必须 ≥ 30 中文字符
- `scenes.*.description` / `props.*.description` 必须 ≥ 20 中文字符
- `voice_style` 是角色可选字段，但若存在必须为非空字符串

### episode_N.json 结构（narration 模式）

```json
{
  "title": "陨落的天才",
  "content_mode": "narration",
  "segments": [
    {
      "segment_id": "E1S01",
      "duration_seconds": 6,
      "novel_text": "小说原文保留...",
      "characters_in_segment": ["叶辰", "林婉儿"],
      "scenes": ["青云宗大殿"],
      "props": ["玄铁剑"],
      "image_prompt": {
        "scene": "A young cultivator in tattered robes stands in the grand hall... (≥ 30 English words)",
        "composition": {
          "shot_type": "Medium Shot",
          "lighting": "Overhead chandeliers cast warm yellow light...",
          "ambiance": "Dust particles floating in light beams, tense atmosphere..."
        }
      },
      "video_prompt": {
        "action": "The young man slowly raises his head, fist clenching...",
        "camera_motion": "Tracking Shot",
        "ambiance_audio": "风穿过大殿的呼啸声，旁人的窃窃私语",
        "dialogue": []
      },
      "transition_to_next": "cut"
    }
  ]
}
```

**关键约束**：
- `segment_id` 格式：`E{集号}S{序号}` 或 `E{集号}S{序号}_{子序号}`（正则 `^E\d+S\d+(?:_\d+)?$`）
- `duration_seconds` 范围 1-60，必须是整数（不能是 bool）
- `characters_in_segment` 里的名称必须在 project.json 的 characters dict key 中存在
- `scenes` 里的名称必须在 project.json 的 scenes dict key 中存在
- `props` 里的名称必须在 project.json 的 props dict key 中存在
- `image_prompt.scene` ≥ 30 英文单词
- `video_prompt.action` 仅描述物理可观察动作，禁止 `陷入`/`回忆`/`意识到`/`决心`/`仿佛`
- `ambiance_audio` 仅描述场景内环境音，禁止 BGM/配乐/画外音
- `dialogue` 仅当原文有引号对话时填写

### episode_N.json 结构（drama 模式）

与 narration 相同，但用 `scenes` 数组（每项含 `scene_id` 格式 `E{n}S{nn}`、`characters_in_scene` 等）。

---

## 工作目录约定

- 所有产出: `{output_dir}/novel-to-video/{novel_title}/`
- 中间临时文件: `{temp_dir}/novel-to-video/`
- 校验脚本: 本 Skill 目录下的 `scripts/validators.py` 和 `scripts/ffmpeg_builder.py`
- `output_dir` / `temp_dir` 从环境信息中获取

---

## 分段策略

长篇小说的 LLM 处理容易因上下文窗口限制导致遗忘或截断。Stage 2 后根据 `validators.py estimate` 输出决定策略：

| segment 预估数 | 策略 |
|---------------|------|
| ≤ 50 | 全文一次处理 |
| 51-100 | Stage 4 每 5 集一批，批次结束后跑 crosscheck |
| > 100 | Stage 3 增加一级"幕"结构，每幕 3-5 集独立处理；跨幕用角色摘要注入 |

每批处理时，下一批输入必须包含前一批的核心角色/场景摘要，防止 LLM 遗忘。

---

## Stage 1: 源文件加载

1. 使用 `read_text` 读取全文；超长文件分段读取后拼接
2. 统计字数、章节数
3. 字数 < 500 时提示用户确认

---

## Stage 1.5: 内容模式选择（强制执行）

**必须**使用 `ask_user` 让用户选择：

```
type: single_select
title: "选择视频内容模式"
display_type: text
options:
  - label: "说书模式 (narration)"
    description: "旁白叙述驱动，画面配合朗读节奏。9:16 竖屏。分镜按朗读段落拆分。"
  - label: "剧集动画模式 (drama)"
    description: "角色对白驱动，按场景和对话结构组织。16:9 横屏。分镜按场景拆分。"
```

---

## Stage 2: 资产库建立

1. LLM 通读全文，提取角色/场景/道具
2. 写入 `{output_dir}/project.json`（**对齐 ArcReel schema**：dict keyed by name）

**角色提取要求**：
- `description` 必须从原文提取外貌细节（发型、服饰、体型、标志性特征），≥ 30 中文字符
- 推断的标注"原文未详述"
- `voice_style` 可选，根据角色性格推断配音风格

**场景提取要求**：
- `description` 必须包含建筑风格/光线/氛围等可画面化信息，≥ 20 中文字符

**道具提取要求**：
- `description` 必须描述外观、材质、特殊效果

3. **完成后立即跑校验**：

```bash
python3 validators.py project {output_dir}/project.json
```

4. **产出量预估**：

```bash
python3 validators.py estimate {output_dir}/project.json
```

---

## Stage 3: 分段分集规划

1. LLM 分析全文结构，标记自然断点（章节转换、时间跳跃、场景切换）
2. 每集 2-5 个 segment，总镜头数 6-15 个
3. 写入 `{output_dir}/episode_plan.json`

**episode_plan.json 结构**:

```json
{
  "novel_title": "小说名",
  "total_chapters": 120,
  "batch_strategy": "full",
  "episodes": [
    {
      "episode": 1,
      "title": "集标题",
      "chapter_range": [1, 3],
      "summary": "本集内容概要",
      "key_events": ["事件1", "事件2"],
      "key_characters": ["叶辰", "林婉儿"],
      "key_scenes": ["青云宗大殿"]
    }
  ]
}
```

4. **校验分集方案**：

```bash
python3 validators.py episode {output_dir}/episode_plan.json {word_count}
```

5. 使用 `ask_user(multi_select)` 展示分集方案，让用户确认或调整。

---

## Stage 4: 分批剧本生成

**核心原则：不许一次性生成全部 JSON，必须逐批处理。**

### 批次规划

```
总集数 ≤ 5          → 1 批全部
总集数 6-10         → 2 批
总集数 > 10         → 每批 5 集
```

### 每批流程

1. LLM 生成该批各集的 `scripts/episode_N.json`
2. 每集生成后立即跑校验：
```bash
python3 validators.py script {output_dir}/project.json {output_dir}/scripts/episode_N.json
```
3. 该批全部通过后，跑跨集一致性：
```bash
python3 validators.py crosscheck {output_dir}/project.json {output_dir}/scripts/
```
4. 下一批输入前，提取前一批的核心角色/场景摘要，注入 LLM 上下文

### 禁止词族（强制约束 LLM prompt）

以下词汇在 `image_prompt.scene` 和 `video_prompt.action` 中**绝对禁止**：

| 类别 | 禁止词 |
|------|--------|
| 抽象情绪 | 陷入、回忆、思绪、意识到、决心、仿佛、像蝴蝶般 |
| 抽象形容词 | 精致、震撼、绝美、惊艳、无与伦比 |
| 内心动词 | suddenly realize、flashback、nostalgia |
| 音频越界 | BGM、配乐、画外音、背景音乐 |

---

## Stage 4.5: 局部编辑（新增）

用户指出某段文案/分镜有问题时，不走全量重生成，改为：

1. 读取目标 `scripts/episode_N.json`
2. 定位到用户指定的 segment/scene（按 segment_id / scene_id）
3. 仅修改用户指定的字段
4. 修改后重跑 `validators.py script` 校验
5. 确认通过后落盘

---

## Stage 5: 图像 Prompt 输出

### 输出结构

```
{output_dir}/novel-to-video/{novel_title}/prompts/
├── 01_characters/
│   ├── 叶辰.txt
│   └── 林婉儿.txt
├── 02_scenes/
│   └── 青云宗大殿.txt
├── 03_props/
│   └── 玄铁剑.txt
├── 04_segments/
│   ├── E1S01.txt
│   └── E1S02.txt
├── REFERENCE_MAP.txt
└── README.md
```

### 分镜 prompt 引用路径（相对路径）

```
[REFERENCE IMAGES REQUIRED]
角色设计: prompts/01_characters/叶辰.txt
场景设计: prompts/02_scenes/青云宗大殿.txt
前一分镜: prompts/04_segments/E1S01.txt
```

### REFERENCE_MAP.txt

```
叶辰   → 角色  → 去 Gemini/ComfyUI 时上传角色设计图作为参考
林婉儿 → 角色  → 去 Gemini/ComfyUI 时上传角色设计图作为参考
青云宗大殿 → 场景 → 上传场景设计图作为参考
```

### 平台适配

写入 `prompts/README.md`，建议的生成顺序：
1. Gemini Imagen / Midjourney: 角色设计图（上传参考图确保一致性）
2. 场景设计图（作为分镜背景参考）
3. Kling / Runway / Vidu: 分镜图合成视频（逐段生成，保持角色一致性）

### 输出量检查

Stage 5 开始前核对：
```bash
# 预期 prompt 文件数 = 角色数 + 场景数 + 道具数 + segment 数
```

---

## Stage 6: 视频合成（可选）

使用 `scripts/ffmpeg_builder.py`：

```bash
python3 ffmpeg_builder.py \
  {output_dir}/scripts/episode_1.json \
  {images_dir}/episode_1/ \
  --aspect 9:16 \
  --audio {audio.mp3} \
  --output episode_1.mp4
```

**功能**：
- 自动从剧本 JSON 读取 duration_seconds
- 支持 `cut` / `fade` / `dissolve` 过渡类型
- 自动 scale + pad 到目标分辨率 (9:16=1080x1920, 16:9=1920x1080)
- 可选叠加音频轨（--audio 参数）

---

## Style 模板集成

ArcReel 支持 style 模板注入到 prompt 中。生成 `image_prompt.scene` 和 `video_prompt.action` 时，LLM 应参考用户选择的 style：

| style 示例 | 对 prompt 的影响 |
|-----------|-----------------|
| 水墨古风 | 画面描述增加"水墨渲染"、"留白意境"、"墨色浓淡" |
| 赛博朋克 | 增加"霓虹灯管"、"全息投影"、"金属义体"、"雨夜街道" |
| 日系动画 | 增加"赛璐珞风格"、"柔焦背景"、"色彩明快" |
| 写实电影 | 增加"自然光"、"实景质感"、"景深虚化" |

Stage 1.5 之后，在 `ask_user` 中增加 style 选择确认环节。

---

## Reference Video 模式（提及）

ArcReel 支持 `generation_mode = "reference_video"`，通过 `ReferenceVideoUnit`（unit + shots 结构）生成视频。本 Skill 当前以 narration/drama 为主；若用户选择 reference_video，切换到 ArcReel 的 `lib/script_models.py` 中 `ReferenceVideoScript` schema，并按 `ReferenceVideoUnit` 模型校验（unit_id 格式 `E{n}U{nn}`、shots 1-4 个/unit、duration 1-15 秒）。

---

## 执行原则

1. **逐 Stage 推进**：每 Stage 产出后展示摘要，等待用户确认
2. **产出必校验**：任何 JSON 产出后**必须**跑对应 validators.py 命令，不通过不进入下一 Stage
3. **分段不可跳过**：segment 预估 > 50 时强制执行分批策略
4. **Stage 5 纯输出**：不调用任何图像 API
5. **Stage 6 按需**：仅用户明确要求时执行
6. **文件 I/O**：优先使用 `write_file` 工具写入产出
7. **局部修改优于全量重来**：用户指出单段问题时走 Stage 4.5 编辑流程

## 模型行为约束

- 分析用中文，`image_prompt.scene` 用英文
- 角色外貌必须从原文提取，不得编造；推断的标注"原文未详述"
- 分集断点优先章节边界，其次场景转换
- `duration_seconds` 默认 5-8 秒，对白密集可延长到 10-12 秒，上限 60 秒
- 严格遵循禁止词族
- `ambiance_audio` 只写环境音，不写 BGM/配乐/画外音
- `dialogue` 仅在原文有引号对话时填写
- 资产名称（角色/场景/道具）使用原文出现的中文名，不要自创英文 ID
*（内容由AI生成，仅供参考）*
