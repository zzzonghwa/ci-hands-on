#!/usr/bin/env python3
"""CI 운영 가시성 대시보드 생성기 — 강의 Project 4의 4단계 "운영 추적"(노트 08).

self-healing CI(claude-fix-ci)와 AI 리뷰(claude-review)가 실제로 얼마나 잘
도는지를 숫자로 본다. gh CLI로 최근 run 데이터를 모아 dashboard.md 로 렌더한다.

- 표준 라이브러리만 사용한다(새 의존성 없음).
- gh 호출부(fetch_*)와 집계부(summarize_* 등 순수 함수)를 분리해,
  집계 로직은 gh 없이 test_ci_dashboard.py 에서 검증한다.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone

# 대시보드에 집계할 워크플로 이름들(.github/workflows 의 name: 과 일치해야 한다).
WORKFLOWS = ["CI", "Claude Review", "Claude Fix CI", "CodeQL"]
# claude-code-action 이 붙은 워크플로 = 토큰 비용 파싱 대상.
AGENT_WORKFLOWS = ["Claude Review", "Claude Fix CI"]

LOOKBACK = 200  # 최근 N개 run 을 조회한다.
COST_LOG_CAP = (
    5  # 토큰 비용은 최근 에이전트 run N개까지만 파싱(로그 다운로드가 비싸다).
)
OUTPUT = "dashboard.md"

FIELDS = (
    "databaseId,workflowName,conclusion,status,"
    "headBranch,headSha,createdAt,startedAt,updatedAt,url,event"
)


# ── gh 호출부 (테스트하지 않는다) ──


def fetch_runs(limit: int = LOOKBACK) -> list[dict]:
    """gh run list 로 최근 run 메타데이터를 가져온다."""
    out = subprocess.run(
        ["gh", "run", "list", "--limit", str(limit), "--json", FIELDS],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout)


def agent_token_cost(runs: list[dict], cap: int = COST_LOG_CAP) -> float | None:
    """최근 에이전트 run 의 로그에서 토큰 비용을 파싱해 합산한다(best-effort).

    로그 형식이 바뀌거나 비용 라인이 없으면 조용히 건너뛰고, 하나도 못 읽으면
    None 을 돌려준다(= 대시보드에 N/A). 게이트가 아니므로 실패해도 던지지 않는다.
    """
    agent = sorted(
        (r for r in runs if r.get("workflowName") in AGENT_WORKFLOWS),
        key=lambda r: r.get("createdAt") or "",
        reverse=True,
    )
    total = 0.0
    parsed_any = False
    for run in agent[:cap]:
        run_id = run.get("databaseId")
        if run_id is None:
            continue
        try:
            log = subprocess.run(
                ["gh", "run", "view", str(run_id), "--log"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        except subprocess.CalledProcessError:
            continue
        cost = parse_cost_from_log(log)
        if cost is not None:
            total += cost
            parsed_any = True
    return total if parsed_any else None


# ── 집계부 (순수 함수 — test_ci_dashboard.py 가 검증한다) ──


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _duration_sec(run: dict) -> float | None:
    start = _parse_ts(run.get("startedAt"))
    end = _parse_ts(run.get("updatedAt"))
    if start is None or end is None:
        return None
    delta = (end - start).total_seconds()
    return delta if delta >= 0 else None


def _completed(runs: list[dict]) -> list[dict]:
    return [r for r in runs if r.get("conclusion") in ("success", "failure")]


def summarize_by_workflow(runs: list[dict]) -> dict[str, dict]:
    """워크플로별 성공/실패율과 평균 실행 시간."""
    stats: dict[str, dict] = {}
    for name in WORKFLOWS:
        rows = [r for r in _completed(runs) if r.get("workflowName") == name]
        total = len(rows)
        success = sum(1 for r in rows if r["conclusion"] == "success")
        durations = [d for r in rows if (d := _duration_sec(r)) is not None]
        stats[name] = {
            "total": total,
            "success": success,
            "rate": (success / total) if total else None,
            "avg_sec": (sum(durations) / len(durations)) if durations else None,
        }
    return stats


def repair_success_rate(runs: list[dict]) -> tuple[float | None, int]:
    """Claude Fix CI 가 수리 커밋을 푸시한 뒤, 같은 브랜치의 다음 CI run 이 성공했는가.

    self-healing 이 말만이 아니라 실제로 코드를 고치는지 보는 핵심 학습 지표.
    반환: (성공률 또는 None, 표본 수).
    """
    fixes = [r for r in runs if r.get("workflowName") == "Claude Fix CI"]
    ci_runs = [r for r in runs if r.get("workflowName") == "CI"]
    considered = 0
    repaired = 0
    for fix in fixes:
        fix_ts = _parse_ts(fix.get("createdAt"))
        if fix_ts is None:
            continue
        branch = fix.get("headBranch")
        later = [
            r
            for r in ci_runs
            if r.get("headBranch") == branch
            and r.get("conclusion") in ("success", "failure")
            and (ts := _parse_ts(r.get("createdAt"))) is not None
            and ts > fix_ts
        ]
        if not later:
            continue
        later.sort(key=lambda r: r["createdAt"])  # ISO 문자열 = 사전순이 곧 시간순
        considered += 1
        if later[0]["conclusion"] == "success":
            repaired += 1
    if considered == 0:
        return None, 0
    return repaired / considered, considered


def recent_failures(runs: list[dict], n: int = 10) -> list[dict]:
    fails = [r for r in runs if r.get("conclusion") == "failure"]
    fails.sort(key=lambda r: r.get("createdAt") or "", reverse=True)
    return [
        {
            "workflow": r.get("workflowName"),
            "branch": r.get("headBranch"),
            "sha": (r.get("headSha") or "")[:7],
            "url": r.get("url"),
        }
        for r in fails[:n]
    ]


def total_action_seconds(runs: list[dict]) -> float:
    return sum(d for r in _completed(runs) if (d := _duration_sec(r)) is not None)


def parse_cost_from_log(text: str) -> float | None:
    """claude-code-action 로그에서 총 비용(USD)을 찾는다. 못 찾으면 None."""
    patterns = [
        r'"total_cost_usd"\s*:\s*([0-9]+\.?[0-9]*)',
        r"total cost[^$0-9]*\$?\s*([0-9]+\.[0-9]+)",
    ]
    found: list[float] = []
    for pat in patterns:
        for match in re.finditer(pat, text, re.IGNORECASE):
            try:
                found.append(float(match.group(1)))
            except ValueError:
                pass
    return max(found) if found else None


# ── 렌더 ──


def _pct(rate: float | None) -> str:
    return "N/A" if rate is None else f"{rate * 100:.0f}%"


def _dur(seconds: float | None) -> str:
    return "N/A" if seconds is None else f"{seconds / 60:.1f}분"


def render_markdown(
    stats: dict[str, dict],
    repair: tuple[float | None, int],
    action_sec: float,
    token_cost: float | None,
    failures: list[dict],
    generated_at: str,
) -> str:
    lines = [
        "# CI 대시보드",
        "",
        f"생성: {generated_at} · 최근 {LOOKBACK}개 run 기준 · 자동 생성(수정 금지)",
        "",
        "## 워크플로별 성공률",
        "",
        "| 워크플로 | 성공/전체 | 성공률 | 평균 시간 |",
        "|---|---|---|---|",
    ]
    for name in WORKFLOWS:
        s = stats[name]
        lines.append(
            f"| {name} | {s['success']}/{s['total']} | "
            f"{_pct(s['rate'])} | {_dur(s['avg_sec'])} |"
        )

    rate, sample = repair
    lines += [
        "",
        "## self-healing 지표",
        "",
        f"- 에이전트 수리 성공률: **{_pct(rate)}** (표본 {sample}건)",
        "  · Claude Fix CI 가 커밋을 푸시한 뒤 같은 브랜치의 다음 CI 가 통과한 비율",
        "",
        "## 비용",
        "",
        f"- Actions 실행 시간 합계: {action_sec / 60:.0f}분",
        f"- Claude 토큰 비용(최근 {COST_LOG_CAP}개 에이전트 run): "
        + ("N/A" if token_cost is None else f"${token_cost:.2f}"),
        "",
        "## 최근 실패",
        "",
    ]
    if failures:
        lines += ["| 워크플로 | 브랜치 | 커밋 | 로그 |", "|---|---|---|---|"]
        for f in failures:
            lines.append(
                f"| {f['workflow']} | {f['branch']} | "
                f"`{f['sha']}` | [보기]({f['url']}) |"
            )
    else:
        lines.append("최근 실패 없음 ✅")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    output = argv[1] if len(argv) > 1 else OUTPUT
    try:
        runs = fetch_runs()
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        json.JSONDecodeError,
    ) as exc:
        # gh 조회 실패 시 기존 대시보드를 덮어쓰지 않고 비-zero 로 끝낸다.
        print(f"run 데이터 조회 실패: {exc}", file=sys.stderr)
        return 1

    md = render_markdown(
        summarize_by_workflow(runs),
        repair_success_rate(runs),
        total_action_seconds(runs),
        agent_token_cost(runs),
        recent_failures(runs),
        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )
    with open(output, "w", encoding="utf-8") as fh:
        fh.write(md)
    print(f"{output} 생성 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
