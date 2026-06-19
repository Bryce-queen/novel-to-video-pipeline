#!/usr/bin/env python3
"""v2.3 测试套件 — 覆盖 project / episode / script / crosscheck / estimate 全部命令。

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
    print(f"{BOLD}║   novel-to-video-pipeline v2.3      ║{RESET}")
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
