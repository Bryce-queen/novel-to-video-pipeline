#!/usr/bin/env python3
"""Novel-to-Video Pipeline v2.1 — 产出物校验脚本集（ArcReel Schema 对齐版）。

使用方式：
    python validators.py project    <project.json>                    # 校验 project.json
    python validators.py episode    <episode_plan.json> <word_count>  # 校验分集方案
    python validators.py script     <project.json> <episode_N.json>   # 校验单集剧本
    python validators.py crosscheck <project.json> <scripts_dir>      # 跨集一致性
    python validators.py estimate   <project.json>                    # 预估产出量
"""

import json
import sys
import os
import re
from pathlib import Path
from typing import Any


# ──────────────────────────────────────────────
# 通用工具
# ──────────────────────────────────────────────

def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fail(msg: str, code: int = 1) -> None:
    print(f"[FAIL] {msg}")
    sys.exit(code)


def ok(msg: str) -> None:
    print(f"[OK] {msg}")


def warn(msg: str) -> None:
    print(f"[WARN] {msg}")


# ──────────────────────────────────────────────
# 枚举值（对齐 ArcReel lib/script_models.py）
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

# ID 格式：E{n}S{nn} 或 E{n}S{nn}_{x}（对齐 ArcReel ID_PATTERN）
SEGMENT_ID_PATTERN = re.compile(r"^E\d+S\d+(?:_\d+)?$")

# 禁止词族（中英混合检测）
FORBIDDEN_WORDS = re.compile(
    r"\b(陷入|回忆|思绪|意识到|画外音|BGM|精致|震撼|回忆翻涌|决心|仿佛|像蝴蝶般|"
    r"背景音乐|配乐|suddenly realize|flashback|nostalgia|masterpiece|breathtaking)\b",
    re.IGNORECASE,
)


def check_prompt_text(field_name: str, text: str, min_words: int = 0) -> None:
    """检查单个 prompt 字段的禁止词和最小字数。"""
    if FORBIDDEN_WORDS.search(text):
        fail(f"{field_name} 包含禁止词/短语: {text[:80]}...")
    words = text.split()
    if min_words > 0 and len(words) < min_words:
        fail(f"{field_name} 不足 {min_words} 个单词 (当前 {len(words)})")


# ──────────────────────────────────────────────
# 1. project.json 校验（v2.1 重写——对齐 ArcReel schema）
# ──────────────────────────────────────────────

def validate_project(path: str) -> None:
    data = load_json(path)
    errors: list[str] = []

    # 顶层必填字段
    for key in ("title", "content_mode", "characters", "scenes", "props"):
        if key not in data:
            errors.append(f"project.json 缺少字段: {key}")

    if errors:
        fail("\n".join(errors))

    # content_mode
    if data["content_mode"] not in ("narration", "drama"):
        fail(f"content_mode 无效: '{data['content_mode']}'，必须是 narration 或 drama")

    # characters 必须是 dict（name-keyed，对齐 ArcReel）
    chars = data["characters"]
    if not isinstance(chars, dict):
        fail(f"characters 字段必须是对象（dict），当前类型: {type(chars).__name__}")

    if len(chars) < 2:
        fail(f"角色数不足: {len(chars)} (至少需要 2 个)")

    for name, c in chars.items():
        if not isinstance(c, dict):
            errors.append(f"角色 '{name}' 数据格式错误，应为对象")
            continue

        desc = c.get("description", "")
        if not isinstance(desc, str) or not desc.strip():
            errors.append(f"角色 '{name}' 缺少必填字段: description（须为非空字符串）")
        elif len(desc.strip()) < 30:
            errors.append(f"角色 '{name}' 的 description 不足 30 个中文字符 (当前 {len(desc.strip())})")

        # voice_style 可选，但若存在必须为非空字符串
        vs = c.get("voice_style")
        if vs is not None and (not isinstance(vs, str) or not vs.strip()):
            errors.append(f"角色 '{name}' 的 voice_style 若存在必须为非空字符串")

    # scenes 必须是 dict
    scenes = data["scenes"]
    if not isinstance(scenes, dict):
        errors.append(f"scenes 字段必须是对象（dict）")

    for name, s in scenes.items():
        if not isinstance(s, dict):
            errors.append(f"场景 '{name}' 数据格式错误，应为对象")
            continue
        desc = s.get("description", "")
        if not isinstance(desc, str) or not desc.strip():
            errors.append(f"场景 '{name}' 缺少必填字段: description（须为非空字符串）")
        elif len(desc.strip()) < 20:
            errors.append(f"场景 '{name}' 的 description 不足 20 个中文字符 (当前 {len(desc.strip())})")

    # props 必须是 dict
    props = data["props"]
    if not isinstance(props, dict):
        errors.append(f"props 字段必须是对象（dict）")

    for name, p in props.items():
        if not isinstance(p, dict):
            errors.append(f"道具 '{name}' 数据格式错误，应为对象")
            continue
        desc = p.get("description", "")
        if not isinstance(desc, str) or not desc.strip():
            errors.append(f"道具 '{name}' 缺少必填字段: description（须为非空字符串）")
        elif len(desc.strip()) < 20:
            errors.append(f"道具 '{name}' 的 description 不足 20 个中文字符 (当前 {len(desc.strip())})")

    if errors:
        fail("\n".join(errors))

    ok(f"project.json: {len(chars)} 角色, {len(scenes)} 场景, {len(props)} 道具 — 全部通过")


# ──────────────────────────────────────────────
# 2. episode_plan.json 校验
# ──────────────────────────────────────────────

def validate_episode_plan(path: str, novel_word_count: int) -> None:
    data = load_json(path)

    if "episodes" not in data:
        fail("episode_plan.json 缺少 episodes 数组")

    eps = data["episodes"]
    if not eps:
        fail("episode_plan.json 的 episodes 为空")

    # 断点连续性检查
    prev_end = 0
    for i, ep in enumerate(eps):
        for k in ("episode", "title", "chapter_range", "summary", "key_events"):
            if k not in ep:
                fail(f"第 {i+1} 集缺少字段: {k}")

        cr = ep["chapter_range"]
        if not isinstance(cr, list) or len(cr) != 2 or not all(isinstance(x, int) for x in cr) or cr[0] > cr[1]:
            fail(f"第 {i+1} 集 chapter_range 非法: {cr}")

        if i > 0 and cr[0] != prev_end + 1:
            fail(f"第 {i} 集与第 {i+1} 集断点不连续: [{prev_end}] -> [{cr[0]}]")

        prev_end = cr[1]

        if not ep["key_events"]:
            fail(f"第 {i+1} 集 key_events 为空")

        if "key_characters" in ep and not isinstance(ep["key_characters"], list):
            fail(f"第 {i+1} 集 key_characters 必须是数组")

    # 预估每集平均字数
    if novel_word_count > 0 and eps:
        avg_words = novel_word_count / len(eps)
        print(f"[INFO] 共 {len(eps)} 集, 预估每集约 {int(avg_words)} 字")

    ok(f"episode_plan.json: {len(eps)} 集 — 断点连续，全部通过")


# ──────────────────────────────────────────────
# 3. 单集剧本 episode_N.json 校验（v2.1 重写）
# ──────────────────────────────────────────────

def _validate_composition(seg_id: str, comp: dict, errors: list[str]) -> None:
    """校验 composition 子结构。"""
    shot_type = comp.get("shot_type", "")
    if shot_type not in VALID_SHOT_TYPES:
        errors.append(f"{seg_id}: shot_type 非法: '{shot_type}' (合法值: {sorted(VALID_SHOT_TYPES)})")

    for field in ("lighting", "ambiance"):
        val = comp.get(field, "")
        if val:
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
    """校验单段（narration segment 或 drama scene）的内部字段。"""

    # segment_id / scene_id 格式校验
    id_field = "segment_id" if mode == "narration" else "scene_id"
    seg_id = seg.get(id_field, sid)
    if not SEGMENT_ID_PATTERN.match(seg_id):
        errors.append(f"{seg_id}: {id_field} 格式错误，应为 E{{n}}S{{nn}} 或 E{{n}}S{{nn}}_{{x}}")

    # duration_seconds
    dur = seg.get("duration_seconds")
    if dur is None:
        errors.append(f"{seg_id}: 缺少 duration_seconds")
    elif isinstance(dur, bool) or not isinstance(dur, int):
        errors.append(f"{seg_id}: duration_seconds 必须是整数 (当前 {type(dur).__name__})")
    elif dur < 1 or dur > 60:
        errors.append(f"{seg_id}: duration_seconds 超出范围 1-60 (当前 {dur})")

    # image_prompt
    ip = seg.get("image_prompt")
    if not ip:
        errors.append(f"{seg_id}: 缺少 image_prompt")
    else:
        scene_text = ip.get("scene", "")
        if not scene_text:
            errors.append(f"{seg_id}: image_prompt.scene 为空")
        else:
            check_prompt_text(f"{seg_id} image_prompt.scene", scene_text, min_words=30)

        comp = ip.get("composition", {})
        if comp:
            _validate_composition(seg_id, comp, errors)

    # video_prompt
    vp = seg.get("video_prompt")
    if not vp:
        errors.append(f"{seg_id}: 缺少 video_prompt")
    else:
        for k in ("action", "camera_motion", "ambiance_audio"):
            if k not in vp:
                errors.append(f"{seg_id}: video_prompt 缺少 {k}")

        action = vp.get("action", "")
        check_prompt_text(f"{seg_id} video_prompt.action", action)

        cam = vp.get("camera_motion", "")
        if cam not in VALID_CAMERA_MOTIONS:
            errors.append(f"{seg_id}: camera_motion 非法: '{cam}' (合法值: {sorted(VALID_CAMERA_MOTIONS)})")

        aos = vp.get("ambiance_audio", "")
        if aos:
            lower = aos.lower()
            if any(kw in lower for kw in ("bgm", "配乐", "画外音", "背景音乐")):
                errors.append(f"{seg_id}: ambiance_audio 包含 BGM/配乐/画外音")

    # transition_to_next
    tt = seg.get("transition_to_next", "cut")
    if tt not in VALID_TRANSITIONS:
        errors.append(f"{seg_id}: transition_to_next 非法: '{tt}' (合法值: {sorted(VALID_TRANSITIONS)})")

    # 引用一致性：角色/场景/道具名称必须在 project.json 对应 bucket 中存在
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

    # novel_text 必填（narration 必须保留原文用于配音）
    if mode == "narration" and "novel_text" not in seg:
        errors.append(f"{seg_id}: narration 模式缺少 novel_text")

    # segment_break 类型检查（可选字段）
    sb = seg.get("segment_break")
    if sb is not None and not isinstance(sb, bool):
        errors.append(f"{seg_id}: segment_break 必须是布尔值")


def validate_script(project_path: str, script_path: str) -> None:
    project = load_json(project_path)
    script = load_json(script_path)

    valid_chars = set(project.get("characters", {}).keys())
    valid_scenes = set(project.get("scenes", {}).keys())
    valid_props = set(project.get("props", {}).keys())

    errors: list[str] = []

    if "episode" not in script:
        errors.append("剧本缺少 episode 字段")
    if "title" not in script:
        errors.append("剧本缺少 title 字段")

    content_mode = script.get("content_mode", project.get("content_mode", "narration"))
    if content_mode not in ("narration", "drama"):
        errors.append(f"content_mode 无效: '{content_mode}'")

    # 模式派发
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

        # ID 去重
        if sid in seg_ids:
            errors.append(f"{sid}: ID 重复")
        seg_ids.add(sid)

        _validate_segment_entry(sid, seg, content_mode, valid_chars, valid_scenes, valid_props, errors)

    if errors:
        fail("\n".join(errors))

    ep_num = script.get("episode", Path(script_path).stem.replace("episode_", ""))
    ok(f"episode_{ep_num}.json: {len(segments)} 段 — 全部通过")


# ──────────────────────────────────────────────
# 4. 跨集一致性校验（v2.1 增强）
# ──────────────────────────────────────────────

def validate_crosscheck(project_path: str, scripts_dir: str) -> None:
    project = load_json(project_path)
    valid_chars = set(project.get("characters", {}).keys())
    valid_scenes = set(project.get("scenes", {}).keys())
    valid_props = set(project.get("props", {}).keys())

    ep_dir = Path(scripts_dir)
    episode_files = sorted(ep_dir.glob("episode_*.json"))
    if not episode_files:
        fail(f"未找到剧本文件: {scripts_dir}/episode_*.json")

    issues: list[str] = []
    summary: list[str] = []

    for ep_file in episode_files:
        data = load_json(str(ep_file))
        mode = data.get("content_mode", project.get("content_mode", "narration"))
        segments_key = "segments" if mode == "narration" else "scenes"
        chars_field = "characters_in_segment" if mode == "narration" else "characters_in_scene"

        ep_num = data.get("episode", ep_file.stem.replace("episode_", ""))
        seg_count = len(data.get(segments_key, []))
        total_dur = sum(
            s.get("duration_seconds", 0)
            for s in data.get(segments_key, [])
            if isinstance(s.get("duration_seconds"), int) and not isinstance(s.get("duration_seconds"), bool)
        )

        for seg in data.get(segments_key, []):
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

    print(f"[INFO] 跨集一致性概要:")
    for line in summary:
        print(line)

    if issues:
        for issue in issues:
            print(f"[WARN] {issue}")
        fail(f"跨集一致性检查发现 {len(issues)} 个引用问题")

    ok(f"跨集一致性: {len(episode_files)} 集 — 全部通过")


# ──────────────────────────────────────────────
# 5. 产出量预估
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

    # 粗略估算: 每 2000 字约 1 个 segment
    est_segments = max(1, word_count // 2000)
    est_episodes = max(1, n_chapters // 5)

    prompt_files = n_chars + n_scenes + n_props + est_segments

    print(f"""
═══════════════════════════════════════
  产出量预估
═══════════════════════════════════════
  总字数:        {word_count:,}
  章节数:        {n_chapters}
  预估集数:      {est_episodes}
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
        print("[WARN] segment 数 > 100，强烈建议: 1) 分批生成 2) 每批后 crosscheck 3) 跨批注入角色摘要")


# ──────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────

if __name__ == "__main__":
    USAGE = """用法: validators.py <command> [args...]
  project    <project.json>
  episode    <episode_plan.json> <novel_word_count>
  script     <project.json> <episode_N.json>
  crosscheck <project.json> <scripts_dir>
  estimate   <project.json>"""

    if len(sys.argv) < 2:
        print(USAGE)
        sys.exit(1)

    cmd = sys.argv[1]

    try:
        if cmd == "project" and len(sys.argv) >= 3:
            validate_project(sys.argv[2])
        elif cmd == "episode" and len(sys.argv) >= 4:
            validate_episode_plan(sys.argv[2], int(sys.argv[3]))
        elif cmd == "script" and len(sys.argv) >= 4:
            validate_script(sys.argv[2], sys.argv[3])
        elif cmd == "crosscheck" and len(sys.argv) >= 4:
            validate_crosscheck(sys.argv[2], sys.argv[3])
        elif cmd == "estimate" and len(sys.argv) >= 3:
            estimate_output(sys.argv[2])
        else:
            fail(f"未知命令或参数不足: {cmd}\n\n{USAGE}")
    except SystemExit:
        raise
    except Exception as e:
        fail(f"执行异常: {e}")
