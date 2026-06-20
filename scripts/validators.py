#!/usr/bin/env python3
"""Novel-to-Video Pipeline v2.9.3 — 产出物校验脚本集（ArcReel 正典 schema 逐字段对齐 + extra='forbid'）。

使用方式:
    python validators.py project    <project.json> [--strict]                    # 校验 project.json
    python validators.py episode    <episode_plan.json> <word_count> [<project.json>]  # 校验分集方案
    python validators.py script     <project.json> <episode_N.json> [--strict]   # 校验单集剧本
    python validators.py crosscheck <project.json> <scripts_dir> [--strict]      # 跨集一致性 + script_file 存在性
    python validators.py estimate   <project.json>                               # 预估产出量
"""

import json
import sys
import re
from pathlib import Path
from typing import Optional, Any

# ──────────────────────────────────────────────
# 通用工具
# ──────────────────────────────────────────────

STRICT = False
WARNING_COUNT = 0


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fail(msg: str, code: int = 1) -> None:
    print(f"[FAIL] {msg}")
    sys.exit(code)


def ok(msg: str) -> None:
    print(f"[OK] {msg}")


def warn(msg: str) -> None:
    global WARNING_COUNT, STRICT
    WARNING_COUNT += 1
    if STRICT:
        fail(msg)
    else:
        print(f"[WARN] {msg}")


# ──────────────────────────────────────────────
# 枚举值
# ──────────────────────────────────────────────

VALID_SHOT_TYPES = frozenset({
    "Extreme Close-up", "Close-up", "Medium Close-up", "Medium Shot",
    "Medium Long Shot", "Long Shot", "Extreme Long Shot",
    "Over-the-shoulder", "Point-of-view",
})

VALID_CAMERA_MOTIONS = frozenset({
    "Static", "Pan Left", "Pan Right", "Tilt Up", "Tilt Down",
    "Zoom In", "Zoom Out", "Tracking Shot",
})

VALID_TRANSITIONS = frozenset({"cut", "fade", "dissolve"})

VALID_STYLES = frozenset({
    "水墨古风", "赛博朋克", "日系动画", "写实电影",
    "default",
})

VALID_CONTENT_MODES = frozenset({"narration", "drama"})

SEGMENT_ID_PATTERN = re.compile(r"^E\d+S\d+(?:_\d+)?$")

FORBIDDEN_WORDS = re.compile(
    r"\b(陷入|回忆|思绪|意识到|画外音|BGM|精致|震撼|回忆翻涌|决心|仿佛|像蝴蝶般|"
    r"背景音乐|配乐|suddenly realize|flashback|nostalgia|masterpiece|breathtaking)\b",
    re.IGNORECASE,
)

# v2.5: image_prompt.scene 中的动作动词检测（ArcReel: "动作请写到 video_prompt.action"）
SCENE_ACTION_VERBS = re.compile(
    r"\b(executes?|walks?|runs?|jumps?|strikes?|draws?|"
    r"sheathes?|turns?|steps?|pauses?|opens?|closes?|"
    r"grabs?|throws?|pulls?|pushes?|kicks?|dodges?|"
    r"swings?|crouches?|leaps?|climbs?|falls?|flies?|"
    r"sits?|stands?|kneels?|bows?|waves?|points?|"
    r"rushes?|charges?|retreats?|advances?|sprints?|"
    r"slashes?|parries?|blocks?|lunges?)\b",
    re.IGNORECASE,
)

MIN_CHAR_DESC_CHARS = 30
MIN_SCENE_DESC_CHARS = 20
MIN_PROP_DESC_CHARS = 20


def parse_seg_id(seg_id: str) -> Optional[tuple[int, int]]:
    m = re.match(r"^E(\d+)S(\d+)(?:_\d+)?$", seg_id)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def check_prompt_text(field_name: str, text: str, min_words: int = 0) -> None:
    if FORBIDDEN_WORDS.search(text):
        fail(f"{field_name} 包含禁止词/短语: {text[:80]}...")
    words = text.split()
    if min_words > 0 and len(words) < min_words:
        fail(f"{field_name} 不足 {min_words} 个单词 (当前 {len(words)})")


# ──────────────────────────────────────────────
# v2.5: 字段越界检测（ArcReel 正典 schema 逐字段对齐）
# ──────────────────────────────────────────────

# project.json 合法字段
PROJECT_VALID_FIELDS = frozenset({
    "title", "content_mode", "style", "word_count", "chapter_count",
    "characters", "scenes", "props", "episodes",
})

# v2.5: 对齐 ArcReel project.ts Character 接口
CHAR_VALID_FIELDS = frozenset({"description", "voice_style", "character_sheet", "reference_image"})
# v2.5: 对齐 ArcReel project.ts Scene 接口
SCENE_VALID_FIELDS = frozenset({"description", "scene_sheet"})
# v2.5: 对齐 ArcReel project.ts Prop 接口
PROP_VALID_FIELDS = frozenset({"description", "prop_sheet"})

# episode_N.json 合法顶层字段
# v2.5: +duration_seconds, +novel, +schema_version（ArcReel episode 脚本正典字段）
EPISODE_VALID_FIELDS = frozenset({
    "episode", "title", "content_mode",
    "segments", "scenes",
    "duration_seconds", "novel", "schema_version",
})

# v2.5: segment 字段按 content_mode 拆分（禁止 narration 出现 scene_id / drama 出现 segment_id）
SEGMENT_CORE_FIELDS = frozenset({
    "duration_seconds", "scenes", "props",
    "image_prompt", "video_prompt", "transition_to_next",
    "segment_break",
    "note",  # v2.5: ArcReel NarrationSegment / DramaScene 均有 note 字段
})
NARRATION_EXTRA_FIELDS = frozenset({"segment_id", "novel_text", "characters_in_segment"})
DRAMA_EXTRA_FIELDS = frozenset({"scene_id", "characters_in_scene"})

# image_prompt 子字段
IMAGE_PROMPT_VALID_FIELDS = frozenset({"scene", "composition"})
COMPOSITION_VALID_FIELDS = frozenset({"shot_type", "lighting", "ambiance"})

# video_prompt 子字段
VIDEO_PROMPT_VALID_FIELDS = frozenset({"action", "camera_motion", "ambiance_audio", "dialogue"})

# episode_plan.json 合法字段
PLAN_TOP_VALID_FIELDS = frozenset({"version", "episodes"})
PLAN_EPISODE_VALID_FIELDS = frozenset({
    "episode", "title", "chapter_range", "summary",
    "key_events", "key_characters", "key_scenes",
})

DIALOGUE_LINE_VALID_FIELDS = frozenset({"speaker", "line"})


def _check_extra_fields(obj: dict, valid: frozenset, path: str, errors: list[str]) -> None:
    """检测未知字段（对齐 Arcreel ConfigDict(extra='forbid')）。"""
    extra = set(obj.keys()) - valid
    if extra:
        errors.append(f"{path}: 存在未声明的字段 (extra fields): {sorted(extra)}")


# ──────────────────────────────────────────────
# 1. project.json 校验（v2.3: extra_fields + style + script_file）
# ──────────────────────────────────────────────

def validate_project(path: str) -> None:
    data = load_json(path)
    errors: list[str] = []

    _check_extra_fields(data, PROJECT_VALID_FIELDS, "project.json", errors)

    for key in ("title", "content_mode", "characters", "scenes", "props"):
        if key not in data:
            errors.append(f"project.json 缺少字段: {key}")

    if errors:
        fail("\n".join(errors))

    cm = data["content_mode"]
    if cm not in VALID_CONTENT_MODES:
        fail(f"content_mode 无效: '{cm}'，必须是 narration 或 drama")

    # v2.3: style 枚举校验
    style = data.get("style", "default")
    if style not in VALID_STYLES:
        warn(f"style 不在已知列表: '{style}' (已知: {sorted(VALID_STYLES)})")

    chars = data["characters"]
    if not isinstance(chars, dict):
        fail(f"characters 字段必须是对象（dict），当前类型: {type(chars).__name__}")
    if len(chars) < 2:
        fail(f"角色数不足: {len(chars)} (至少需要 2 个)")

    # v2.3: 检测角色子字段越界
    for name, c in chars.items():
        if not isinstance(c, dict):
            errors.append(f"角色 '{name}' 数据格式错误，应为对象")
            continue
        _check_extra_fields(c, CHAR_VALID_FIELDS, f"characters.{name}", errors)
        desc = c.get("description", "")
        if not isinstance(desc, str) or not desc.strip():
            errors.append(f"角色 '{name}' 缺少必填字段: description（须为非空字符串）")
        elif len(desc.strip()) < MIN_CHAR_DESC_CHARS:
            errors.append(
                f"角色 '{name}' 的 description 不足 {MIN_CHAR_DESC_CHARS} 个中文字符 "
                f"(当前 {len(desc.strip())})"
            )
        vs = c.get("voice_style")
        if vs is not None and (not isinstance(vs, str) or not vs.strip()):
            errors.append(f"角色 '{name}' 的 voice_style 若存在必须为非空字符串")

    scenes = data["scenes"]
    if not isinstance(scenes, dict):
        errors.append("scenes 字段必须是对象（dict）")
    for name, s in scenes.items():
        if not isinstance(s, dict):
            errors.append(f"场景 '{name}' 数据格式错误，应为对象")
            continue
        _check_extra_fields(s, SCENE_VALID_FIELDS, f"scenes.{name}", errors)
        desc = s.get("description", "")
        if not isinstance(desc, str) or not desc.strip():
            errors.append(f"场景 '{name}' 缺少必填字段: description（须为非空字符串）")
        elif len(desc.strip()) < MIN_SCENE_DESC_CHARS:
            errors.append(
                f"场景 '{name}' 的 description 不足 {MIN_SCENE_DESC_CHARS} 个中文字符 "
                f"(当前 {len(desc.strip())})"
            )

    props = data["props"]
    if not isinstance(props, dict):
        errors.append("props 字段必须是对象（dict）")
    for name, p in props.items():
        if not isinstance(p, dict):
            errors.append(f"道具 '{name}' 数据格式错误，应为对象")
            continue
        _check_extra_fields(p, PROP_VALID_FIELDS, f"props.{name}", errors)
        desc = p.get("description", "")
        if not isinstance(desc, str) or not desc.strip():
            errors.append(f"道具 '{name}' 缺少必填字段: description（须为非空字符串）")
        elif len(desc.strip()) < MIN_PROP_DESC_CHARS:
            errors.append(
                f"道具 '{name}' 的 description 不足 {MIN_PROP_DESC_CHARS} 个中文字符 "
                f"(当前 {len(desc.strip())})"
            )

    # v2.3: script_file 字段存在性（仅记录，不阻塞——crosscheck 时做实际存在性校验）
    if "episodes" in data:
        for ei, ep in enumerate(data["episodes"]):
            if "script_file" not in ep:
                warn(f"project.json episodes[{ei}] 缺少 script_file 字段")

    if errors:
        fail("\n".join(errors))

    ok(f"project.json: {len(chars)} 角色, {len(scenes)} 场景, {len(props)} 道具 — 全部通过")


# ──────────────────────────────────────────────
# 2. episode_plan.json 校验
# ──────────────────────────────────────────────

def validate_episode_plan(plan_path: str, novel_word_count: int,
                          project_path: Optional[str] = None) -> None:
    data = load_json(plan_path)
    errors: list[str] = []

    # v2.4: 顶层字段越界检测
    _check_extra_fields(data, PLAN_TOP_VALID_FIELDS, "episode_plan.json", errors)

    if "episodes" not in data:
        fail("episode_plan.json 缺少 episodes 数组")

    eps = data["episodes"]
    if not eps:
        fail("episode_plan.json 的 episodes 为空")

    valid_chars: set[str] = set()
    valid_scenes: set[str] = set()
    if project_path:
        project = load_json(project_path)
        valid_chars = set(project.get("characters", {}).keys())
        valid_scenes = set(project.get("scenes", {}).keys())

    if errors:
        fail("\n".join(errors))

    prev_end = 0
    for i, ep in enumerate(eps):
        _check_extra_fields(ep, PLAN_EPISODE_VALID_FIELDS, f"episodes[{i}]", errors)

        for k in ("episode", "title", "chapter_range", "summary", "key_events"):
            if k not in ep:
                fail(f"第 {i+1} 集缺少字段: {k}")

        cr = ep["chapter_range"]
        if (not isinstance(cr, list) or len(cr) != 2
                or not all(isinstance(x, int) for x in cr) or cr[0] > cr[1]):
            fail(f"第 {i+1} 集 chapter_range 非法: {cr}")

        if i > 0 and cr[0] != prev_end + 1:
            fail(f"第 {i} 集与第 {i+1} 集断点不连续: [{prev_end}] -> [{cr[0]}]")
        prev_end = cr[1]

        if not ep["key_events"]:
            fail(f"第 {i+1} 集 key_events 为空")

        if "key_characters" in ep:
            if not isinstance(ep["key_characters"], list):
                fail(f"第 {i+1} 集 key_characters 必须是数组")
            if valid_chars:
                for cname in ep["key_characters"]:
                    if cname not in valid_chars:
                        warn(f"第 {i+1} 集 key_characters 引用了 project.json 中不存在的角色: '{cname}'")

        if "key_scenes" in ep:
            if not isinstance(ep["key_scenes"], list):
                fail(f"第 {i+1} 集 key_scenes 必须是数组")
            if valid_scenes:
                for sname in ep["key_scenes"]:
                    if sname not in valid_scenes:
                        warn(f"第 {i+1} 集 key_scenes 引用了 project.json 中不存在的场景: '{sname}'")

    if errors:
        fail("\n".join(errors))

    if novel_word_count > 0 and eps:
        avg_words = novel_word_count / len(eps)
        print(f"[INFO] 共 {len(eps)} 集, 预估每集约 {int(avg_words)} 字")

    ok(f"episode_plan.json: {len(eps)} 集 — 断点连续，全部通过")


# ──────────────────────────────────────────────
# 3. 单集剧本 episode_N.json 校验（v2.3: extra_fields 全层级）
# ──────────────────────────────────────────────

def _validate_composition(seg_id: str, comp: dict, errors: list[str]) -> None:
    _check_extra_fields(comp, COMPOSITION_VALID_FIELDS, f"{seg_id}.composition", errors)
    # v2.7: ArcReel Composition 三个字段均必填（无 default）
    shot_type = comp.get("shot_type", "")
    if not shot_type:
        errors.append(f"{seg_id}: composition 缺少 shot_type（ArcReel 必填字段）")
    elif shot_type not in VALID_SHOT_TYPES:
        errors.append(
            f"{seg_id}: shot_type 非法: '{shot_type}' "
            f"(合法值: {sorted(VALID_SHOT_TYPES)})"
        )
    for field in ("lighting", "ambiance"):
        val = comp.get(field, "")
        if not val:
            errors.append(f"{seg_id}: composition 缺少 {field}（ArcReel 必填字段）")
        else:
            check_prompt_text(f"{seg_id} composition.{field}", val)


def _validate_segment_entry(
    sid: str,
    seg: dict,
    mode: str,
    valid_chars: set[str],
    valid_scenes: set[str],
    valid_props: set[str],
    errors: list[str],
) -> None:
    # v2.5: segment 级 extra_fields 按 content_mode 拆分
    valid_fields = SEGMENT_CORE_FIELDS
    if mode == "narration":
        valid_fields = valid_fields | NARRATION_EXTRA_FIELDS
        # 禁止 narration 段出现 scene_id（ArcReel NarrationSegment 无此字段）
        if "scene_id" in seg:
            errors.append(f"{sid}: narration 段禁止 scene_id 字段（仅 drama 模式使用）")
    else:
        valid_fields = valid_fields | DRAMA_EXTRA_FIELDS
        # 禁止 drama 段出现 segment_id（ArcReel DramaScene 无此字段）
        if "segment_id" in seg:
            errors.append(f"{sid}: drama 段禁止 segment_id 字段（仅 narration 模式使用）")
    _check_extra_fields(seg, valid_fields, sid, errors)

    id_field = "segment_id" if mode == "narration" else "scene_id"
    seg_id = seg.get(id_field, sid)
    if not SEGMENT_ID_PATTERN.match(seg_id):
        errors.append(
            f"{seg_id}: {id_field} 格式错误，应为 E{{n}}S{{nn}} 或 E{{n}}S{{nn}}_{{x}}"
        )

    dur = seg.get("duration_seconds")
    if dur is None:
        if mode == "narration":
            # NarrationSegment 无 default，必填
            errors.append(f"{seg_id}: 缺少 duration_seconds")
        # drama 模式下 duration_seconds 有 default=8，可省略
    elif isinstance(dur, bool) or not isinstance(dur, int):
        errors.append(f"{seg_id}: duration_seconds 必须是整数 (当前 {type(dur).__name__})")
    elif dur < 1 or dur > 60:
        errors.append(f"{seg_id}: duration_seconds 超出范围 1-60 (当前 {dur})")

    ip = seg.get("image_prompt")
    if not ip:
        errors.append(f"{seg_id}: 缺少 image_prompt")
    else:
        _check_extra_fields(ip, IMAGE_PROMPT_VALID_FIELDS, f"{seg_id}.image_prompt", errors)
        scene_text = ip.get("scene", "")
        if not scene_text:
            errors.append(f"{seg_id}: image_prompt.scene 为空")
        else:
            check_prompt_text(f"{seg_id} image_prompt.scene", scene_text, min_words=30)
            # v2.5: 检测 image_prompt.scene 中的动作动词（ArcReel 规定 scene 只描述静态画面）
            action_matches = SCENE_ACTION_VERBS.findall(scene_text)
            if action_matches:
                unique_matches = sorted(set(m.lower() for m in action_matches))
                warn(
                    f"{seg_id}: image_prompt.scene 包含动作动词 {unique_matches}，"
                    "请只描述静态画面，动作应写入 video_prompt.action"
                )
        # v2.7: ArcReel ImagePrompt.composition 必填（无 default）
        comp = ip.get("composition")
        if not comp:
            errors.append(f"{seg_id}: image_prompt 缺少 composition（ArcReel 必填字段）")
        else:
            _validate_composition(seg_id, comp, errors)

    vp = seg.get("video_prompt")
    if not vp:
        errors.append(f"{seg_id}: 缺少 video_prompt")
    else:
        _check_extra_fields(vp, VIDEO_PROMPT_VALID_FIELDS, f"{seg_id}.video_prompt", errors)
        for k in ("action", "camera_motion", "ambiance_audio"):
            if k not in vp:
                errors.append(f"{seg_id}: video_prompt 缺少 {k}")
        action = vp.get("action", "")
        check_prompt_text(f"{seg_id} video_prompt.action", action)
        cam = vp.get("camera_motion", "")
        if cam not in VALID_CAMERA_MOTIONS:
            errors.append(
                f"{seg_id}: camera_motion 非法: '{cam}' "
                f"(合法值: {sorted(VALID_CAMERA_MOTIONS)})"
            )
        aos = vp.get("ambiance_audio", "")
        if aos:
            lower = aos.lower()
            if any(kw in lower for kw in ("bgm", "配乐", "画外音", "背景音乐")):
                errors.append(f"{seg_id}: ambiance_audio 包含 BGM/配乐/画外音")


    tt = seg.get("transition_to_next", "cut")
    if tt not in VALID_TRANSITIONS:
        errors.append(
            f"{seg_id}: transition_to_next 非法: '{tt}' "
            f"(合法值: {sorted(VALID_TRANSITIONS)})"
        )

    chars_field = "characters_in_segment" if mode == "narration" else "characters_in_scene"
    seg_chars = seg.get(chars_field)
    if isinstance(seg_chars, list):
        for cname in seg_chars:
            if cname not in valid_chars:
                errors.append(f"{seg_id}: 引用了 project.json 中不存在的角色: '{cname}'")
    elif seg_chars is not None:
        errors.append(f"{seg_id}: {chars_field} 必须是数组")

    seg_scenes = seg.get("scenes")
    if isinstance(seg_scenes, list):
        for sname in seg_scenes:
            if sname not in valid_scenes:
                errors.append(f"{seg_id}: 引用了 project.json 中不存在的场景: '{sname}'")

    seg_props = seg.get("props")
    if isinstance(seg_props, list):
        for pname in seg_props:
            if pname not in valid_props:
                errors.append(f"{seg_id}: 引用了 project.json 中不存在的道具: '{pname}'")

    # v2.6: narration 模式必须包含 characters_in_segment
    if mode == "narration":
        if "novel_text" not in seg:
            errors.append(f"{seg_id}: narration 模式缺少 novel_text")
        if "characters_in_segment" not in seg:
            errors.append(f"{seg_id}: narration 模式缺少 characters_in_segment")
        # v2.9.3: narration 模式 video_prompt 禁止 dialogue（ArcReel 正典 dialogue 仅 drama 场景用）
        narration_dl = vp.get("dialogue", []) if vp else []
        if isinstance(narration_dl, list) and len(narration_dl) > 0:
            errors.append(f"{seg_id}: narration 模式 video_prompt 禁止 dialogue（仅 drama 场景使用）")

    # v2.6: drama 模式必须包含 characters_in_scene
    if mode == "drama" and "characters_in_scene" not in seg:
        errors.append(f"{seg_id}: drama 模式缺少 characters_in_scene")

    sb = seg.get("segment_break")
    if sb is not None and not isinstance(sb, bool):
        errors.append(f"{seg_id}: segment_break 必须是布尔值")


def _validate_drama_dialogue(seg_id: str, vp: dict, errors: list[str]) -> None:
    dialogue = vp.get("dialogue")
    if dialogue is None:
        return
    if not isinstance(dialogue, list):
        errors.append(f"{seg_id}: dialogue 必须是数组")
        return
    for di, line in enumerate(dialogue):
        if not isinstance(line, dict):
            errors.append(f"{seg_id}: dialogue[{di}] 必须是对象")
            continue
        # v2.6: 旧键名 migration 友好提示
        if "character" in line or "text" in line:
            errors.append(
                f"{seg_id}: dialogue[{di}]: 检测到旧键名 character/text，"
                "v2.5+ ArcReel 正典要求 speaker/line，请迁移"
            )
        _check_extra_fields(line, DIALOGUE_LINE_VALID_FIELDS, f"{seg_id}.dialogue[{di}]", errors)
        for k in ("speaker", "line"):
            if k not in line:
                errors.append(f"{seg_id}: dialogue[{di}] 缺少字段: {k}")
        txt = line.get("line", "")
        if txt and FORBIDDEN_WORDS.search(txt):
            errors.append(
                f"{seg_id}: dialogue[{di}].line 包含禁止词: {txt[:60]}..."
            )


def validate_script(project_path: str, script_path: str) -> None:
    project = load_json(project_path)
    script = load_json(script_path)

    # v2.3: 顶层 extra_fields
    errors: list[str] = []
    _check_extra_fields(script, EPISODE_VALID_FIELDS, Path(script_path).name, errors)

    valid_chars = set(project.get("characters", {}).keys())
    valid_scenes = set(project.get("scenes", {}).keys())
    valid_props = set(project.get("props", {}).keys())

    if "episode" not in script:
        errors.append("剧本缺少 episode 字段")
    else:
        script_ep = script["episode"]
        fname = Path(script_path).stem
        m = re.match(r"^episode_(\d+)$", fname)
        if m:
            file_ep = int(m.group(1))
            if script_ep != file_ep:
                warn(
                    f"episode 字段 ({script_ep}) 与文件名 ({fname}) 不一致，"
                    f"应为 {file_ep}"
                )

    if "title" not in script:
        errors.append("剧本缺少 title 字段")

    content_mode = script.get("content_mode", project.get("content_mode", "narration"))
    if content_mode not in VALID_CONTENT_MODES:
        errors.append(f"content_mode 无效: '{content_mode}'")

    # v2.5: schema_version 校验
    sv = script.get("schema_version")
    if sv is not None and (not isinstance(sv, int) or isinstance(sv, bool) or sv < 1):
        errors.append(f"schema_version 必须是正整数 (当前 {sv})")

    if content_mode == "narration":
        segments_key = "segments"
        id_key = "segment_id"
    else:
        segments_key = "scenes"
        id_key = "scene_id"

    if segments_key not in script:
        errors.append(f"剧本缺少 {segments_key} 数组")
    if errors:
        fail("\n".join(errors))

    segments = script[segments_key]
    if not segments:
        fail(f"剧本 {segments_key} 为空")

    seg_ids = set()
    for i, seg in enumerate(segments):
        sid = seg.get(id_key, f"#{i+1}")
        if sid in seg_ids:
            errors.append(f"{sid}: ID 重复")
        seg_ids.add(sid)

        _validate_segment_entry(
            sid, seg, content_mode, valid_chars, valid_scenes, valid_props, errors
        )

        if content_mode == "drama":
            _validate_drama_dialogue(sid, seg.get("video_prompt", {}), errors)

    if errors:
        fail("\n".join(errors))

    ep_num = script.get("episode", Path(script_path).stem.replace("episode_", ""))
    ok(f"episode_{ep_num}.json: {len(segments)} 段 — 全部通过")


# ──────────────────────────────────────────────
# 4. 跨集一致性校验（v2.3: script_file 存在性）
# ──────────────────────────────────────────────

def _check_segment_continuity(ep_files: list[Path]) -> None:
    for ep_file in ep_files:
        data = load_json(str(ep_file))
        mode = data.get("content_mode", "narration")
        segments_key = "segments" if mode == "narration" else "scenes"
        id_field = "segment_id" if mode == "narration" else "scene_id"

        segments = data.get(segments_key, [])
        if not segments:
            continue

        ep_num = data.get("episode", ep_file.stem.replace("episode_", ""))
        ids: list[tuple[int, int]] = []
        for seg in segments:
            sid = seg.get(id_field, "")
            parsed = parse_seg_id(sid)
            if parsed:
                ids.append(parsed)

        if not ids:
            continue

        ids.sort()
        for j in range(1, len(ids)):
            prev_ep, prev_s = ids[j - 1]
            cur_ep, cur_s = ids[j]
            if cur_ep == prev_ep and cur_s != prev_s + 1:
                warn(
                    f"episode_{ep_num}: segment_id 跳号 "
                    f"(E{prev_ep}S{prev_s:02d} → E{cur_ep}S{cur_s:02d})"
                )


def _check_script_files_exist(project_path: str, scripts_dir: Path) -> None:
    """v2.3: 校验 project.json episodes[].script_file 指向的文件是否存在。"""
    project = load_json(project_path)
    episodes = project.get("episodes", [])
    if not episodes:
        return

    missing: list[str] = []
    for ep in episodes:
        sf = ep.get("script_file")
        if not sf:
            continue
        full_path = scripts_dir / sf
        if not full_path.exists():
            missing.append(sf)

    if missing:
        warn(f"project.json 声明的 script_file 在 {scripts_dir} 下不存在: {missing}")


def validate_crosscheck(project_path: str, scripts_dir: str) -> None:
    project = load_json(project_path)
    valid_chars = set(project.get("characters", {}).keys())
    valid_scenes = set(project.get("scenes", {}).keys())
    valid_props = set(project.get("props", {}).keys())

    ep_dir = Path(scripts_dir)
    episode_files = sorted(ep_dir.glob("episode_*.json"))
    if not episode_files:
        fail(f"未找到剧本文件: {scripts_dir}/episode_*.json")

    # v2.3: script_file 存在性校验
    _check_script_files_exist(project_path, ep_dir)

    issues: list[str] = []
    summary: list[str] = []

    for ep_file in episode_files:
        data = load_json(str(ep_file))
        mode = data.get("content_mode", project.get("content_mode", "narration"))
        segments_key = "segments" if mode == "narration" else "scenes"
        chars_field = (
            "characters_in_segment" if mode == "narration" else "characters_in_scene"
        )

        ep_num = data.get("episode", ep_file.stem.replace("episode_", ""))
        segs = data.get(segments_key, [])
        seg_count = len(segs)
        total_dur = sum(
            s.get("duration_seconds", 0)
            for s in segs
            if isinstance(s.get("duration_seconds"), int)
            and not isinstance(s.get("duration_seconds"), bool)
        )

        for seg in segs:
            seg_id = seg.get("segment_id", seg.get("scene_id", "?"))
            for cname in seg.get(chars_field, []):
                if cname not in valid_chars:
                    issues.append(f"ep_{ep_num}/{seg_id}: 引用不存在角色 '{cname}'")
            for sname in seg.get("scenes", []):
                if sname not in valid_scenes:
                    issues.append(f"ep_{ep_num}/{seg_id}: 引用不存在场景 '{sname}'")
            for pname in seg.get("props", []):
                if pname not in valid_props:
                    issues.append(f"ep_{ep_num}/{seg_id}: 引用不存在道具 '{pname}'")

        summary.append(f"  第 {ep_num} 集: {seg_count} 段, 总时长 {total_dur}s")

    _check_segment_continuity(episode_files)

    print("[INFO] 跨集一致性概要:")
    for line in summary:
        print(line)

    if issues:
        for issue in issues:
            print(f"[WARN] {issue}")
        fail(f"跨集一致性检查发现 {len(issues)} 个引用问题")

    ok(f"跨集一致性: {len(episode_files)} 集 — 全部通过")


# ──────────────────────────────────────────────
# 5. 产出量预估（v2.3: 增加 script_file check 提示）
# ──────────────────────────────────────────────

def estimate_output(path: str) -> None:
    data = load_json(path)

    chars = data.get("characters", {})
    scenes = data.get("scenes", {})
    props = data.get("props", {})

    n_chars = len(chars) if isinstance(chars, dict) else 0
    n_scenes = len(scenes) if isinstance(scenes, dict) else 0
    n_props = len(props) if isinstance(props, dict) else 0
    n_chapters = data.get("chapter_count", 1)
    word_count = data.get("word_count", 0)
    n_episodes = len(data.get("episodes", []))

    est_segments = max(1, word_count // 2000)
    est_episodes = max(1, n_chapters // 5)
    prompt_files = n_chars + n_scenes + n_props + est_segments

    print(f"""
═══════════════════════════════════════
  产出量预估
═══════════════════════════════════════
  总字数:        {word_count:,}
  章节数:        {n_chapters}
  预估集数:      {est_episodes}  (project.json 已声明 {n_episodes} 集)
  预估 segment 数: {est_segments}
  ─────────────────────────────────
  角色设计 prompt:  {n_chars}
  场景设计 prompt:  {n_scenes}
  道具设计 prompt:  {n_props}
  分镜 prompt:      {est_segments}
  ─────────────────────────────────
  prompt 文件总数:  {prompt_files}
  建议分段策略:     {'分批处理 (每 5 集一批)' if est_segments > 50 else '全文一次处理'}
═══════════════════════════════════════
""")

    if est_segments > 100:
        print(
            "[WARN] segment 数 > 100，强烈建议: "
            "1) 分批生成 2) 每批后 crosscheck 3) 跨批注入角色摘要"
        )

    # v2.3: 提示 script_file 缺失
    missing_sf = [
        e.get("episode", i + 1)
        for i, e in enumerate(data.get("episodes", []))
        if "script_file" not in e
    ]
    if missing_sf:
        print(f"[WARN] 以下集缺少 script_file 字段: {missing_sf}")


# ──────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────

if __name__ == "__main__":
    USAGE = """用法: validators.py <command> [args...] [--strict]
  project    <project.json>
  episode    <episode_plan.json> <novel_word_count> [<project.json>]
  script     <project.json> <episode_N.json>
  crosscheck <project.json> <scripts_dir>
  estimate   <project.json>

  --strict: 将 WARN 提升为 FAIL"""

    if len(sys.argv) < 2:
        print(USAGE)
        sys.exit(1)

    args = [a for a in sys.argv[1:] if a != "--strict"]
    STRICT = len(args) < len(sys.argv) - 1

    if not args:
        print(USAGE)
        sys.exit(1)

    cmd = args[0]

    try:
        if cmd == "project" and len(args) >= 2:
            validate_project(args[1])
        elif cmd == "episode" and len(args) >= 3:
            project_path = args[3] if len(args) >= 4 else None
            validate_episode_plan(args[1], int(args[2]), project_path)
        elif cmd == "script" and len(args) >= 3:
            validate_script(args[1], args[2])
        elif cmd == "crosscheck" and len(args) >= 3:
            validate_crosscheck(args[1], args[2])
        elif cmd == "estimate" and len(args) >= 2:
            estimate_output(args[1])
        else:
            fail(f"未知命令或参数不足: {cmd}\n\n{USAGE}")
    except SystemExit:
        raise
    except Exception as e:
        fail(f"执行异常: {e}")
