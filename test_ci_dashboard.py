"""ci_dashboard 집계 로직 테스트 — gh 호출 없이 순수 함수만 검증한다."""

from scripts.ci_dashboard import (
    parse_cost_from_log,
    recent_failures,
    repair_success_rate,
    summarize_by_workflow,
)


def _run(name, conclusion, branch="main", created="2026-07-20T00:00:00Z", **extra):
    run = {
        "workflowName": name,
        "conclusion": conclusion,
        "status": "completed",
        "headBranch": branch,
        "headSha": "abc1234def",
        "createdAt": created,
        "startedAt": created,
        "updatedAt": created,
        "url": "https://example.com/run",
    }
    run.update(extra)
    return run


def test_summarize_counts_only_completed():
    runs = [
        _run("CI", "success"),
        _run("CI", "failure"),
        _run("CI", None, status="in_progress"),  # 진행 중 → 집계 제외
    ]
    stats = summarize_by_workflow(runs)
    assert stats["CI"]["total"] == 2
    assert stats["CI"]["success"] == 1
    assert stats["CI"]["rate"] == 0.5


def test_summarize_empty_workflow_is_none():
    stats = summarize_by_workflow([_run("CI", "success")])
    assert stats["CodeQL"]["total"] == 0
    assert stats["CodeQL"]["rate"] is None


def test_repair_success_when_next_ci_passes():
    runs = [
        _run("Claude Fix CI", "success", branch="feat", created="2026-07-20T10:00:00Z"),
        _run("CI", "success", branch="feat", created="2026-07-20T10:05:00Z"),
    ]
    rate, sample = repair_success_rate(runs)
    assert rate == 1.0
    assert sample == 1


def test_repair_failure_when_next_ci_still_fails():
    runs = [
        _run("Claude Fix CI", "success", branch="feat", created="2026-07-20T10:00:00Z"),
        _run("CI", "failure", branch="feat", created="2026-07-20T10:05:00Z"),
    ]
    rate, sample = repair_success_rate(runs)
    assert rate == 0.0
    assert sample == 1


def test_repair_ignores_fix_without_subsequent_ci():
    runs = [
        _run("Claude Fix CI", "success", branch="feat", created="2026-07-20T10:00:00Z"),
        # 수리 이전(더 이른) CI 는 표본에서 제외돼야 한다.
        _run("CI", "success", branch="feat", created="2026-07-20T09:00:00Z"),
    ]
    rate, sample = repair_success_rate(runs)
    assert rate is None
    assert sample == 0


def test_recent_failures_sorted_desc_and_capped():
    runs = [
        _run("CI", "failure", created="2026-07-20T01:00:00Z"),
        _run("CI", "failure", created="2026-07-20T03:00:00Z"),
        _run("CI", "success", created="2026-07-20T02:00:00Z"),
    ]
    fails = recent_failures(runs, n=1)
    assert len(fails) == 1
    assert fails[0]["sha"] == "abc1234"  # 7자 축약


def test_parse_cost_from_json_and_text():
    assert parse_cost_from_log('{"total_cost_usd": 0.12}') == 0.12
    assert parse_cost_from_log("Total cost: $0.34") == 0.34


def test_parse_cost_absent_returns_none():
    assert parse_cost_from_log("no cost line here") is None
