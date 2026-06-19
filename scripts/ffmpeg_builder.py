#!/usr/bin/env python3
"""Novel-to-Video Pipeline v2.1 — FFmpeg 视频合成（ArcReel Schema 对齐版）。

使用方式:
    python ffmpeg_builder.py <episode_N.json> <images_dir>
        [--audio <audio.mp3>] [--output <output.mp4>]
        [--aspect 9:16|16:9] [--temp-dir <path>]

功能:
    - 从剧本 JSON 读取每个 segment 的 duration_seconds
    - 自动匹配 images_dir 下的分镜图
    - 生成 FFmpeg concat 文件并合成视频
    - 可选叠加音频轨
"""

import json
import sys
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_concat_file(
    episode_data: dict,
    image_files: list[str],
    output_path: str,
) -> None:
    """生成 FFmpeg concat demuxer 文件。

    从剧本 JSON 读取每个 segment/scene 的 duration_seconds，写入 concat 格式。
    过渡效果由后续版本通过 xfade filter 实现（当前 concat demuxer 为 cut-only）。
    """
    mode = episode_data.get("content_mode", "narration")
    segments_key = "segments" if mode == "narration" else "scenes"
    segments = episode_data.get(segments_key, [])

    if not segments:
        print("[ERROR] 剧本中没有 segment 数据")
        sys.exit(1)

    # 提取每个 segment 的时长和过渡类型
    durations: list[int] = []
    transitions: list[str] = []
    for seg in segments:
        dur = seg.get("duration_seconds", 5)
        if isinstance(dur, bool) or not isinstance(dur, int):
            dur = 5
        durations.append(max(1, dur))
        transitions.append(seg.get("transition_to_next", "cut"))

    total_images = len(image_files)
    if total_images == 0:
        print("[ERROR] images_dir 下无图片文件 (.png/.jpg/.jpeg/.webp)")
        sys.exit(1)

    n_frames = min(len(segments), total_images)
    print(f"[INFO] 剧本段数: {len(segments)}, 可用图片: {total_images}, 合成帧数: {n_frames}")

    # 检查是否有非 cut 的过渡
    has_transition = any(t in ("fade", "dissolve") for t in transitions)
    if has_transition:
        print("[WARN] 检测到 fade/dissolve 过渡；当前 concat demuxer 不支持过渡效果，将全部使用 cut。"
              "xfade 支持计划在 v2.2 实现。")

    # 生成 concat demuxer 文件
    with open(output_path, "w") as f:
        f.write(f"# FFmpeg concat demuxer — episode_{episode_data.get('episode', '?')}\n")
        f.write(f"# 模式: {mode}, 段数: {len(segments)}\n")
        f.write(f"# 过渡效果: {'cut only' if not has_transition else 'cut (xfade 待实现)'}\n\n")

        for i in range(n_frames):
            f.write(f"file '{image_files[i]}'\n")
            f.write(f"duration {durations[i]}\n")

        # concat demuxer 要求最后一张图写两次
        last_idx = n_frames - 1
        if last_idx >= 0:
            f.write(f"file '{image_files[last_idx]}'\n")


def run_ffmpeg(
    concat_path: str,
    output_path: str,
    audio_path: Optional[str] = None,
    fps: int = 24,
    aspect: str = "9:16",
) -> None:
    """执行 FFmpeg 合成。"""

    # 分辨率配置
    if aspect == "9:16":
        width, height = 1080, 1920
    elif aspect == "16:9":
        width, height = 1920, 1080
    else:
        print(f"[WARN] 未知 aspect '{aspect}'，使用 9:16")
        width, height = 1080, 1920

    scale_filter = (
        f"fps={fps},"
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_path,
        "-vf", scale_filter,
    ]

    if audio_path and os.path.exists(audio_path):
        cmd.extend(["-i", audio_path, "-shortest"])
        cmd.extend(["-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "128k"])

    cmd.extend([
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "medium",
        "-crf", "23",
        output_path,
    ])

    print(f"[RUN] ffmpeg (合成中...)")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        stderr_tail = result.stderr.strip().split("\n")[-10:]
        print(f"[ERROR] FFmpeg 失败:\n" + "\n".join(stderr_tail))
        sys.exit(1)

    file_size = os.path.getsize(output_path)
    print(f"[OK] 输出: {output_path} ({file_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "用法: ffmpeg_builder.py <episode_N.json> <images_dir>"
            " [--audio <audio.mp3>] [--output <output.mp4>]"
            " [--aspect 9:16|16:9] [--temp-dir <path>]"
        )
        sys.exit(1)

    episode_path = sys.argv[1]
    images_dir = sys.argv[2]

    # 解析可选参数
    audio_path = None
    output_path = None
    aspect = "9:16"
    temp_dir = None

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
        elif sys.argv[i] == "--temp-dir" and i + 1 < len(sys.argv):
            temp_dir = sys.argv[i + 1]
            i += 2
        else:
            i += 1

    # 加载剧本
    episode = load_json(episode_path)
    ep_num = episode.get("episode", Path(episode_path).stem.replace("episode_", ""))

    if output_path is None:
        output_path = f"episode_{ep_num}.mp4"

    # 收集图片文件
    img_exts = {".png", ".jpg", ".jpeg", ".webp"}
    img_dir = Path(images_dir)
    if not img_dir.exists():
        print(f"[ERROR] 图片目录不存在: {images_dir}")
        sys.exit(1)

    image_files = sorted([
        str(p) for p in img_dir.iterdir()
        if p.suffix.lower() in img_exts
    ])

    # 生成 concat 文件（使用指定的 temp 目录或系统临时目录）
    if temp_dir:
        os.makedirs(temp_dir, exist_ok=True)
        concat_path = os.path.join(temp_dir, f"nvp_concat_ep{ep_num}.txt")
    else:
        concat_fd, concat_path = tempfile.mkstemp(
            suffix=f"_ep{ep_num}.txt", prefix="nvp_concat_"
        )
        os.close(concat_fd)

    try:
        build_concat_file(episode, image_files, concat_path)
        run_ffmpeg(concat_path, output_path, audio_path, aspect=aspect)
    finally:
        # 清理临时 concat 文件
        if os.path.exists(concat_path):
            os.remove(concat_path)
