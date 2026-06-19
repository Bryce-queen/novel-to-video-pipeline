#!/usr/bin/env python3
"""Novel-to-Video Pipeline v2.4 — FFmpeg 视频合成（xfade 过渡 + 音频交叉淡化）。

使用方式:
    python ffmpeg_builder.py <episode_N.json> <images_dir>
        [--audio <audio.mp3>] [--output <output.mp4>]
        [--aspect 9:16|16:9] [--fps <24>] [--temp-dir <path>]

过渡效果:
    cut:     直接切换（默认）
    fade:    0.5s 黑场淡入淡出（xfade）
    dissolve: 0.5s 交叉溶解（xfade）

音频:
    支持叠加背景音频轨，在过渡点自动做 afade 交叉淡化。
"""

import json
import sys
import os
import subprocess
from pathlib import Path
from typing import Optional

XFADE_DURATION = 0.5
AFADE_DURATION = 0.5  # 音频交叉淡化的时长


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_xfade_filtergraph(
    durations: list[int],
    transitions: list[str],
    fps: int,
    width: int,
    height: int,
) -> tuple[str, float, list[float]]:
    """构建 FFmpeg xfade filtergraph + 计算各段实际起止时间。

    Returns:
        (filter_complex_string, total_duration_seconds, segment_boundaries)
        segment_boundaries: 每段结束时的累积时间（用于音频 afade）
    """
    n = len(durations)
    if n == 0:
        return "", 0.0, []

    parts: list[str] = []
    boundaries: list[float] = []

    scale_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"fps={fps},setpts=PTS-STARTPTS"
    )

    for i in range(n):
        parts.append(f"[{i}:v]{scale_filter}[v{i}]")

    prev_out = "v0"
    cumulative_offset = 0.0

    for i in range(1, n):
        tr = transitions[i - 1]
        dur = durations[i - 1]

        if n == 1:
            break

        if tr in ("fade", "dissolve"):
            xfade_type = "fade" if tr == "fade" else "dissolve"
            offset = max(0, cumulative_offset + dur - XFADE_DURATION)
            parts.append(
                f"[{prev_out}][v{i}]xfade=transition={xfade_type}:"
                f"duration={XFADE_DURATION}:offset={offset}[xf{i}]"
            )
            prev_out = f"xf{i}"
            cumulative_offset += dur
            boundaries.append(cumulative_offset)
        else:
            offset = cumulative_offset + dur
            parts.append(
                f"[{prev_out}][v{i}]xfade=transition=fade:"
                f"duration=0:offset={offset}[xf{i}]"
            )
            prev_out = f"xf{i}"
            cumulative_offset += dur
            boundaries.append(cumulative_offset)

    total_duration = cumulative_offset + (durations[-1] if durations else 0)
    boundaries.append(total_duration)

    return ";".join(parts), total_duration, boundaries


def _build_audio_afade_graph(
    boundaries: list[float],
    audio_input_idx: int,
) -> str:
    """为背景音频轨构建 afade 交叉淡化图。

    在每个过渡点对音频做 afade 实现平滑过渡，
    避免生硬的音频跳变。
    """
    n_segments = len(boundaries)
    if n_segments < 2:
        return ""

    parts: list[str] = []
    parts.append(f"[{audio_input_idx}:a]asplit={n_segments}")

    for i in range(n_segments):
        parts.append(f"[a{i}]")

    # 每段音频做 atrim + afade
    trimmed: list[str] = []
    prev_end = 0.0
    for i, end_time in enumerate(boundaries):
        seg_dur = end_time - prev_end
        fade_str = ""
        if i < n_segments - 1:
            fade_str = f"afade=t=out:st={max(0, seg_dur - AFADE_DURATION)}:d={AFADE_DURATION},"
        if i > 0:
            fade_str += f"afade=t=in:d={AFADE_DURATION},"

        trimmed.append(
            f"[a{i}]atrim={prev_end}:{end_time},{fade_str}asetpts=PTS-STARTPTS[as{i}]"
        )
        prev_end = end_time

    concat_inputs = "".join(f"[as{i}]" for i in range(n_segments))
    concat = f"{concat_inputs}concat=n={n_segments}:v=0:a=1[audio_out]"

    return ";".join(parts + trimmed) + ";" + concat


def run_ffmpeg_xfade(
    image_files: list[str],
    durations: list[int],
    transitions: list[str],
    output_path: str,
    audio_path: Optional[str] = None,
    fps: int = 24,
    aspect: str = "9:16",
) -> None:
    """使用 xfade 滤镜合成视频，支持 fade/dissolve 过渡 + 音频交叉淡化。"""

    if aspect == "9:16":
        width, height = 1080, 1920
    elif aspect == "16:9":
        width, height = 1920, 1080
    else:
        print(f"[WARN] 未知 aspect '{aspect}'，使用 9:16")
        width, height = 1080, 1920

    n_frames = min(len(image_files), len(durations))
    if n_frames == 0:
        print("[ERROR] 无图片或时长数据")
        sys.exit(1)

    has_transition = any(t in ("fade", "dissolve") for t in transitions[:n_frames])
    has_audio = audio_path and os.path.exists(audio_path)

    filter_complex, total_duration, boundaries = _build_xfade_filtergraph(
        durations[:n_frames], transitions[:n_frames], fps, width, height
    )

    cmd = ["ffmpeg", "-y"]

    # 输入所有图片
    for img in image_files[:n_frames]:
        cmd.extend(["-loop", "1", "-i", img])

    audio_input_idx = n_frames
    if has_audio:
        cmd.extend(["-i", audio_path])

    # 构建完整 filter_complex（视频 + 音频处理）
    filter_parts: list[str] = [filter_complex]

    if has_audio and n_frames > 1:
        afade_graph = _build_audio_afade_graph(boundaries, audio_input_idx)
        if afade_graph:
            filter_parts.append(afade_graph)
            cmd.extend(["-filter_complex", ";".join(filter_parts)])
            # 映射
            last_label = f"xf{n_frames - 1}" if n_frames > 1 else "v0"
            cmd.extend(["-map", f"[{last_label}]", "-map", "[audio_out]"])
            cmd.extend(["-c:a", "aac", "-b:a", "128k"])
            cmd.extend(["-shortest"])
        else:
            cmd.extend(["-filter_complex", filter_complex])
            last_label = f"xf{n_frames - 1}" if n_frames > 1 else "v0"
            cmd.extend(["-map", f"[{last_label}]"])
            if has_audio:
                cmd.extend(["-map", f"{audio_input_idx}:a", "-c:a", "aac", "-b:a", "128k"])
                if total_duration > 0:
                    cmd.extend(["-t", str(total_duration)])
    elif has_audio:
        # 单帧无法 xfade，退化为 concat 式覆盖
        cmd.extend(["-filter_complex", filter_complex])
        cmd.extend(["-map", "[v0]"])
        cmd.extend(["-map", f"{audio_input_idx}:a", "-c:a", "aac", "-b:a", "128k"])
        if total_duration > 0:
            cmd.extend(["-t", str(total_duration)])
        cmd.extend(["-shortest"])
    else:
        cmd.extend(["-filter_complex", filter_complex])
        last_label = f"xf{n_frames - 1}" if n_frames > 1 else "v0"
        cmd.extend(["-map", f"[{last_label}]"])

    cmd.extend([
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "medium",
        "-crf", "23",
        output_path,
    ])

    mode = "xfade" if has_transition else "concat"
    audio_note = " + afade" if (has_audio and n_frames > 1) else ""
    print(
        f"[RUN] ffmpeg {mode}{audio_note} (合成中, {n_frames} 帧, "
        f"过渡: {'fade/dissolve' if has_transition else 'cut only'})"
    )

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        stderr_tail = result.stderr.strip().split("\n")[-15:]
        print(f"[ERROR] FFmpeg 失败:\n" + "\n".join(stderr_tail))
        sys.exit(1)

    file_size = os.path.getsize(output_path)
    print(f"[OK] 输出: {output_path} ({file_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "用法: ffmpeg_builder.py <episode_N.json> <images_dir>"
            " [--audio <audio.mp3>] [--output <output.mp4>]"
            " [--aspect 9:16|16:9] [--fps <24>] [--temp-dir <path>]"
        )
        sys.exit(1)

    episode_path = sys.argv[1]
    images_dir = sys.argv[2]

    audio_path: Optional[str] = None
    output_path: Optional[str] = None
    aspect = "9:16"
    fps = 24

    i = 3
    while i < len(sys.argv):
        if sys.argv[i] == "--audio" and i + 1 < len(sys.argv):
            audio_path = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--output" and i + 1 < len(sys.argv):
            output_path = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--aspect" and i + 1 < len(sys.argv):
            aspect = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--fps" and i + 1 < len(sys.argv):
            fps = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--temp-dir" and i + 1 < len(sys.argv):
            i += 2  # v2.3 不再需要 temp dir，保留参数兼容
        else:
            i += 1

    episode = load_json(episode_path)
    ep_num = episode.get("episode", Path(episode_path).stem.replace("episode_", ""))

    if output_path is None:
        output_path = f"episode_{ep_num}.mp4"

    img_exts = {".png", ".jpg", ".jpeg", ".webp"}
    img_dir = Path(images_dir)
    if not img_dir.exists():
        print(f"[ERROR] 图片目录不存在: {images_dir}")
        sys.exit(1)

    image_files = sorted([
        str(p) for p in img_dir.iterdir()
        if p.suffix.lower() in img_exts
    ])

    if not image_files:
        print(f"[ERROR] {images_dir} 下无图片文件 (.png/.jpg/.jpeg/.webp)")
        sys.exit(1)

    mode = episode.get("content_mode", "narration")
    segments_key = "segments" if mode == "narration" else "scenes"
    segments = episode.get(segments_key, [])

    durations: list[int] = []
    transitions: list[str] = []
    for seg in segments:
        dur = seg.get("duration_seconds", 5)
        if isinstance(dur, bool) or not isinstance(dur, int):
            dur = 5
        durations.append(max(1, dur))
        transitions.append(seg.get("transition_to_next", "cut"))

    n_frames = min(len(image_files), len(durations))
    print(
        f"[INFO] 剧本段数: {len(segments)}, 可用图片: {len(image_files)}, "
        f"合成帧数: {n_frames}, 过渡效果: {set(transitions)}"
    )

    run_ffmpeg_xfade(
        image_files=image_files,
        durations=durations,
        transitions=transitions,
        output_path=output_path,
        audio_path=audio_path,
        fps=fps,
        aspect=aspect,
    )
