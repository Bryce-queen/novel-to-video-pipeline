#!/usr/bin/env python3
"""v2.9.2 测试套件 — 覆盖 project / episode / script / crosscheck / estimate 全部命令，含 drama 模式 + ArcReel 正典 schema 对齐。

用法:
    python run_tests.py [--strict]
"""

import sys
import os
import subprocess
from pathlib import Path

VALIDATORS_PATH = Path(__file__).resolve().parent.parent / "scripts" / "validators.py"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
VALID_DIR = FIXTURES_DIR / "valid"
INVALID_DIR = FIXTURES_DIR / "invalid"

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"


def run(cmd: list[str], expect_fail: bool = False) -> bool:
    """运行 validators 命令，根据 expect_fail 判断结果。"""
    args = [sys.executable, str(VALIDATORS_PATH)] + cmd
    result = subprocess.run(args, capture_output=True, text=True)
    passed = (result.returncode == 0) != expect_fail

    status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    if not passed:
        print(f"  {status}")
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        if stderr:
            lines = stderr.split("\n")[-10:]
            for line in lines:
                print(f"    {YELLOW}{line}{RESET}")
        elif stdout:
            lines = stdout.split("\n")[-10:]
            for line in lines:
                print(f"    {YELLOW}{line}{RESET}")
    else:
        if expect_fail:
            print(f"  {status} (correctly rejected)")
        else:
            print(f"  {status}")
    return passed


def main():
    strict = "--strict" in sys.argv

    print(f"\n{BOLD}╔══════════════════════════════════════╗{RESET}")
    print(f"{BOLD}║  novel-to-video-pipeline v2.9.2   ║{RESET}")
    print(f"{BOLD}║   测试套件                          ║{RESET}")
    print(f"{BOLD}╚══════════════════════════════════════╝{RESET}")
    print(f"\n  strict 模式: {'ON' if strict else 'OFF'}")
    print(f"  fixtures: {FIXTURES_DIR}\n")

    base_cmd = ["--strict"] if strict else []
    results: dict[str, bool] = {}

    # ── 有效夹具（应该全部通过）──
    print(f"{BOLD}── 有效夹具（预期通过）──{RESET}")

    print("\n  project.json:")
    results["valid_project"] = run(
        base_cmd + ["project", str(VALID_DIR / "project.json")]
    )

    print("\n  episode_plan.json:")
    results["valid_plan"] = run(
        base_cmd + ["episode", str(VALID_DIR / "episode_plan.json"), "150000",
                     str(VALID_DIR / "project.json")]
    )

    print("\n  script (episode_1.json):")
    results["valid_script"] = run(
        base_cmd + ["script", str(VALID_DIR / "project.json"),
                     str(VALID_DIR / "episode_1.json")]
    )

    print("\n  crosscheck:")
    results["valid_crosscheck"] = run(
        base_cmd + ["crosscheck", str(VALID_DIR / "project.json"), str(VALID_DIR)]
    )

    print("\n  estimate:")
    results["valid_estimate"] = run(
        base_cmd + ["estimate", str(VALID_DIR / "project.json")]
    )

    print("\n  script drama (episode_drama_1.json):")
    results["valid_drama_script"] = run(
        base_cmd + ["script", str(VALID_DIR / "project_drama.json"),
                     str(VALID_DIR / "episode_drama_1.json")]
    )

    # v2.8.1: drama 模式 duration_seconds 省略（ArcReel default=8）
    print("\n  script drama defaults (drama_default_dur.json):")
    results["valid_drama_default_dur"] = run(
        base_cmd + ["script", str(VALID_DIR / "project_drama.json"),
                     str(VALID_DIR / "drama_default_dur.json")]
    )

    # ── 无效夹具（应该全部拒绝）──
    print(f"\n{BOLD}── 无效夹具（预期拒绝）──{RESET}")

    print("\n  project_bad.json (extra fields + 无效 style + 短 description):")
    results["invalid_project"] = run(
        base_cmd + ["project", str(INVALID_DIR / "project_bad.json")],
        expect_fail=True,
    )

    print("\n  episode_bad.json (extra fields + 禁止词 + 格式错误 + dialogue):")
    results["invalid_script"] = run(
        base_cmd
        + [
            "script",
            str(VALID_DIR / "project.json"),
            str(INVALID_DIR / "episode_bad.json"),
        ],
        expect_fail=True,
    )

    print("\n  episode_plan_bad.json (顶层 extra field):")
    results["invalid_plan"] = run(
        base_cmd + ["episode", str(INVALID_DIR / "episode_plan_bad.json"), "150000"],
        expect_fail=True,
    )

    # v2.5 新增: ArcReel 正典 schema 对齐——禁止 narration 段含 scene_id
    print("\n  narration_scene_id.json (narration 段含 scene_id 应被拒):")
    results["invalid_narration_scene_id"] = run(
        base_cmd
        + [
            "script",
            str(VALID_DIR / "project.json"),
            str(INVALID_DIR / "narration_scene_id.json"),
        ],
        expect_fail=True,
    )

    # v2.5 新增: 禁止 drama 段含 segment_id
    print("\n  drama_segment_id.json (drama 段含 segment_id 应被拒):")
    results["invalid_drama_segment_id"] = run(
        base_cmd
        + [
            "script",
            str(VALID_DIR / "project_drama.json"),
            str(INVALID_DIR / "drama_segment_id.json"),
        ],
        expect_fail=True,
    )

    # v2.5 新增: 禁止 dialogue 使用 character/text 键名（应为 speaker/line）
    print("\n  dialogue_wrong_keys.json (dialogue 键名错误 character/text 应被拒):")
    results["invalid_dialogue_keys"] = run(
        base_cmd
        + [
            "script",
            str(VALID_DIR / "project_drama.json"),
            str(INVALID_DIR / "dialogue_wrong_keys.json"),
        ],
        expect_fail=True,
    )

    # v2.6 新增: narration 段禁止 dialogue
    print("\n  narration_with_dialogue.json (narration 段含 dialogue 应被拒):")
    results["invalid_narration_dialogue"] = run(
        base_cmd
        + [
            "script",
            str(VALID_DIR / "project.json"),
            str(INVALID_DIR / "narration_with_dialogue.json"),
        ],
        expect_fail=True,
    )

    # v2.6 新增: narration 段缺 characters_in_segment
    print("\n  narration_no_characters.json (narration 段缺 characters_in_segment 应被拒):")
    results["invalid_narration_no_chars"] = run(
        base_cmd
        + [
            "script",
            str(VALID_DIR / "project.json"),
            str(INVALID_DIR / "narration_no_characters.json"),
        ],
        expect_fail=True,
    )

    # v2.6 新增: drama 段缺 characters_in_scene
    print("\n  drama_no_characters.json (drama 段缺 characters_in_scene 应被拒):")
    results["invalid_drama_no_chars"] = run(
        base_cmd
        + [
            "script",
            str(VALID_DIR / "project_drama.json"),
            str(INVALID_DIR / "drama_no_characters.json"),
        ],
        expect_fail=True,
    )

    # v2.7 新增: image_prompt 缺少 composition
    print("\n  no_composition.json (image_prompt 缺 composition 应被拒):")
    results["invalid_no_composition"] = run(
        base_cmd
        + [
            "script",
            str(VALID_DIR / "project.json"),
            str(INVALID_DIR / "no_composition.json"),
        ],
        expect_fail=True,
    )

    # v2.7 新增: composition 缺少 shot_type
    print("\n  no_shot_type.json (composition 缺 shot_type 应被拒):")
    results["invalid_no_shot_type"] = run(
        base_cmd
        + [
            "script",
            str(VALID_DIR / "project.json"),
            str(INVALID_DIR / "no_shot_type.json"),
        ],
        expect_fail=True,
    )

    # v2.7 新增: composition 缺少 lighting 和 ambiance
    print("\n  no_lighting_ambiance.json (composition 缺 lighting/ambiance 应被拒):")
    results["invalid_no_lighting_ambiance"] = run(
        base_cmd
        + [
            "script",
            str(VALID_DIR / "project.json"),
            str(INVALID_DIR / "no_lighting_ambiance.json"),
        ],
        expect_fail=True,
    )

    # ── 汇总 ──
    print(f"\n{BOLD}╔══════════════════════════════════════╗{RESET}")
    print(f"{BOLD}║   测试结果汇总                      ║{RESET}")
    print(f"{BOLD}╚══════════════════════════════════════╝{RESET}")
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    for name, ok_flag in results.items():
        status = f"{GREEN}PASS{RESET}" if ok_flag else f"{RED}FAIL{RESET}"
        print(f"  {name:30s} {status}")

    print(f"\n  通过: {passed}/{total}")
    if passed < total:
        print(f"  {RED}{total - passed} 个测试失败{RESET}")
        sys.exit(1)
    else:
        print(f"  {GREEN}全部通过!{RESET}")


if __name__ == "__main__":
    main()
