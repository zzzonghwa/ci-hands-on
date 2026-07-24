#!/usr/bin/env python3
"""pre-PR harness 루프 — 게이트를 PR *이전* agent 반복 루프 안으로 옮긴다.

발표 "Agents Need Continuous Compute"의 핵심: build/test가 PR 이후 게이트가
아니라 agent inner loop의 일부가 된다. 통과한 결과만 draft PR로 나간다.

- 루프 제어(`harness_loop`)는 agent·gate를 주입받는 순수 함수 → LLM·네트워크
  없이 test_harness.py 에서 검증한다.
- git·claude·gh 같은 부작용은 `main()`에만 있다.
- agent에는 Bash·git 권한을 주지 않는다. 커밋·푸시·PR·게이트 실행은 전부
  이 harness가 결정론적으로 수행한다(게이트 우회·자기 PR 생성 차단).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import namedtuple

MAX_ITERS = 5
# agent가 쓸 수 있는 도구 — Bash·git 없음(하드닝 3).
AGENT_TOOLS = "Edit Read Write Grep Glob"
# Bash 를 명시적으로 거부한다. allowedTools 는 "무프롬프트 허용"일 뿐 whitelist 가
# 아니므로, 게이트 우회·자기 커밋을 막으려면 disallowedTools 로 못박아야 한다.
# (soft 경계다 — 커널 샌드박스가 아니라 claude 권한 레이어에 의존한다.)
AGENT_DENY = "Bash"
# evaluator(회의적 리뷰어)는 읽기 전용 — 편집·커밋 없이 판정만 한다(코딩과 역할 분리).
EVALUATOR_TOOLS = "Read Grep Glob"
EVALUATOR_DENY = "Bash Edit Write"

LoopResult = namedtuple("LoopResult", "status iterations output")


# ── 순수 제어부 (test_harness.py 가 검증한다) ──


def build_prompt(task: str, feedback: str | None) -> str:
    parts = [
        f"작업: {task}",
        "제약: 게이트를 우회하지 마라(테스트 삭제, 커버리지·설정 완화 금지). "
        "커밋·푸시는 하지 마라(하네스가 한다).",
    ]
    if feedback:
        parts.append(
            f"직전 게이트 실패 로그:\n{feedback}\n이 실패의 근본 원인을 고쳐라."
        )
    return "\n\n".join(parts)


def build_eval_prompt(task: str, gate_output: str) -> str:
    """evaluator(회의적 리뷰어)용 프롬프트. 게이트가 못 잡는 것을 본다."""
    return "\n\n".join(
        [
            f"원래 작업(의도): {task}",
            "너는 회의적 코드 리뷰어다. 방금 변경이 게이트(ruff·black·pytest)를 통과했다. "
            "게이트가 못 잡는 것을 보라: 의도를 실제로 충족하는가? 설계·정확성·엣지케이스 "
            "결함은 없는가? 기본 태도는 의심(REVISE)이고, 의도를 충족하고 결함이 없을 때만 ACCEPT.",
            f"참고용 게이트 출력(모두 통과한 상태):\n{gate_output}",
            "변경된 파일을 직접 읽어 확인하라(Read/Grep). 편집·커밋은 하지 마라.",
            "마지막 줄에 정확히 이 형식으로만 판정하라: '판정: ACCEPT' 또는 '판정: REVISE'. "
            "REVISE면 그 위에 고쳐야 할 구체적 이유를 적어라.",
        ]
    )


def parse_verdict(output: str) -> tuple[bool, str]:
    """evaluator 출력에서 판정을 뽑는다. 기본은 REVISE(회의적) — 명시적 ACCEPT만 통과.

    여러 '판정:' 줄이 있으면 마지막 것이 최종. 반환 (accept, review).
    """
    accept = False
    for line in output.splitlines():
        if "판정:" in line:
            accept = "ACCEPT" in line.upper()
    return accept, output


def slugify_task(task: str, maxlen: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", task.lower()).strip("-")
    return slug[:maxlen].strip("-") or "task"


def harness_loop(
    task, agent_fn, gate_fn, evaluator_fn=None, max_iters: int = MAX_ITERS
) -> LoopResult:
    """agent → gate → (evaluator) 를 반복한다. 부작용 없음.

    흐름(A안): 게이트가 통과하면 evaluator_fn(있을 때)이 accept/revise 를 판정한다.
    accept 면 green, revise 면 그 리뷰를 되먹여 재반복한다(게이트 실패와 동일 취급).
    evaluator_fn=None 이면 게이트만으로 green(하위호환).

    반환 status: "green"(게이트 통과 + evaluator accept) · "no_progress"(동일 사유 2회)
    · "exhausted"(횟수 소진). green 이 아니면 main 은 PR 을 만들지 않는다.
    """
    feedback = None
    prev_reason = None
    for i in range(1, max_iters + 1):
        agent_fn(task, feedback)
        ok, gate_output = gate_fn()
        if ok:
            if evaluator_fn is None:
                return LoopResult("green", i, gate_output)
            accept, review = evaluator_fn(task, gate_output)
            if accept:
                return LoopResult("green", i, gate_output)
            reason = f"[게이트는 통과했으나 리뷰어가 재작업 요청]\n{review}"
        else:
            reason = gate_output
        if reason == prev_reason:  # 하드닝 1: 무진전(게이트 실패든 리뷰든) 조기 종료.
            return LoopResult("no_progress", i, reason)
        prev_reason = reason
        feedback = reason
    return LoopResult("exhausted", max_iters, prev_reason)


# ── 부작용부 (main 에서만 호출) ──


def run_agent(task: str, feedback: str | None) -> None:
    # ponytail: claude CLI 플래그는 버전에 따라 다를 수 있다. 필요 시 조정.
    subprocess.run(
        [
            "claude",
            "-p",
            build_prompt(task, feedback),
            "--allowedTools",
            AGENT_TOOLS,
            "--disallowedTools",
            AGENT_DENY,
            "--permission-mode",
            "acceptEdits",
        ],
        check=True,
    )


def run_gates() -> tuple[bool, str]:
    """ci.yml 과 동일 게이트를 로컬에서 돌린다. 하나라도 실패하면 즉시 반환.

    pytest 는 ci.yml 처럼 커버리지 100% 게이트까지 맞춘다(pytest-cov 필요).
    """
    outputs = []
    gates = (
        ["ruff", "check", "."],
        ["black", "--check", "."],
        ["pytest", "--cov=app", "--cov-fail-under=100"],
    )
    for cmd in gates:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        outputs.append(f"$ {' '.join(cmd)}\n{proc.stdout}{proc.stderr}")
        if proc.returncode != 0:
            return False, "\n".join(outputs)
    return True, "\n".join(outputs)


def run_evaluator(task: str, gate_output: str) -> tuple[bool, str]:
    """게이트 통과분을 회의적 리뷰어(claude)가 판정한다. 읽기 전용, 편집·커밋 없음.

    자기검증 편향 완화: refute-first 프롬프트 + 편집 권한 미부여(코딩과 역할 분리).
    """
    proc = subprocess.run(
        [
            "claude",
            "-p",
            build_eval_prompt(task, gate_output),
            "--allowedTools",
            EVALUATOR_TOOLS,
            "--disallowedTools",
            EVALUATOR_DENY,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return parse_verdict(proc.stdout)


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True)


def _tree_dirty() -> bool:
    return bool(_git("status", "--porcelain").stdout.strip())


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="pre-PR harness 루프")
    parser.add_argument("task", help="agent 에게 시킬 작업(intent)")
    parser.add_argument("--max-iters", type=int, default=MAX_ITERS)
    parser.add_argument(
        "--open-pr",
        action="store_true",
        help="push + draft PR 까지 생성(기본: 브랜치·커밋만, push/PR 안 함)",
    )
    parser.add_argument(
        "--no-evaluator",
        action="store_true",
        help="LLM evaluator 단계를 끄고 게이트만으로 판정(기본: evaluator 켜짐)",
    )
    args = parser.parse_args(argv)
    if args.max_iters < 1:  # "max 5" 계약 방어 — 0/음수 거부.
        parser.error("--max-iters 는 1 이상이어야 한다")
    return args


def main(argv: list[str]) -> int:
    args = _parse_args(argv[1:])

    if _tree_dirty():  # 하드닝 2: 더러운 트리에서 시작 금지.
        print("작업 트리가 더럽다. 커밋/스태시 후 다시 실행하라.", file=sys.stderr)
        return 1

    branch = f"harness/{slugify_task(args.task)}"
    _git("switch", "-c", branch)
    print(f"브랜치 생성: {branch}")

    evaluator = None if args.no_evaluator else run_evaluator
    result = harness_loop(args.task, run_agent, run_gates, evaluator, args.max_iters)
    print(f"루프 종료: {result.status} ({result.iterations}회)")

    if result.status != "green":
        print("초록불 실패 → PR 만들지 않음. 마지막 게이트 출력:", file=sys.stderr)
        print(result.output or "(없음)", file=sys.stderr)
        return 1

    if not _tree_dirty():  # 하드닝 2: green 인데 변경이 없으면 PR 안 만듦.
        print("agent 가 변경한 파일이 없다 → PR 만들지 않음.", file=sys.stderr)
        return 1

    # 트리는 시작 시 깨끗했으므로 -A 는 agent 변경만 스테이징한다.
    _git("add", "-A")
    _git("commit", "-m", f"feat: {args.task}")

    if not args.open_pr:
        # 기본 모드도 브랜치·커밋은 실제로 남긴다(정직하게: dry-run 아님).
        print(f"로컬 모드: {branch} 에 커밋 완료. push/PR 은 생략. 올리려면 --open-pr")
        return 0

    _git("push", "-u", "origin", branch)
    subprocess.run(["gh", "pr", "create", "--draft", "--fill"], check=True)
    print("draft PR 생성 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
