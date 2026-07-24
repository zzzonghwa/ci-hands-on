"""harness 루프 제어 + main() 안전성 테스트 — LLM·git·gh 없이 검증한다."""

import pytest

from harness import loop
from harness.loop import build_prompt, harness_loop, slugify_task


class FakeAgent:
    """agent 호출을 기록만 하는 가짜(파일은 안 건드린다)."""

    def __init__(self):
        self.calls = []

    def __call__(self, task, feedback):
        self.calls.append((task, feedback))


def _gate_fail_then_pass(n):
    """앞의 n-1회는 서로 다른 실패, n회째 통과."""
    state = {"i": 0}

    def gate():
        state["i"] += 1
        if state["i"] >= n:
            return True, "ok"
        return False, f"fail-{state['i']}"

    return gate


def test_stops_green_when_gate_passes():
    agent = FakeAgent()
    res = harness_loop("t", agent, _gate_fail_then_pass(3), max_iters=5)
    assert res.status == "green"
    assert res.iterations == 3
    assert len(agent.calls) == 3


def test_no_progress_on_identical_failure():
    def gate_stuck():
        return False, "same error"

    res = harness_loop("t", FakeAgent(), gate_stuck, max_iters=5)
    assert res.status == "no_progress"
    assert res.iterations == 2  # 하드닝 1: 2회째에 조기 종료


def test_exhausted_when_never_green():
    state = {"i": 0}

    def gate_changing():
        state["i"] += 1
        return False, f"e{state['i']}"  # 매번 달라서 no_progress 는 안 걸림

    res = harness_loop("t", FakeAgent(), gate_changing, max_iters=4)
    assert res.status == "exhausted"
    assert res.iterations == 4


def test_loop_returns_non_green_on_persistent_failure():
    res = harness_loop("t", FakeAgent(), lambda: (False, "boom"), max_iters=5)
    assert res.status != "green"


def test_agent_called_each_iteration_until_no_progress():
    agent = FakeAgent()
    harness_loop("t", agent, lambda: (False, "same"), max_iters=5)
    assert len(agent.calls) == 2  # 2회째 no_progress 로 멈춤


def test_agent_called_max_iters_when_exhausted():
    agent = FakeAgent()
    state = {"i": 0}

    def gate_changing():
        state["i"] += 1
        return False, f"e{state['i']}"

    harness_loop("t", agent, gate_changing, max_iters=4)
    assert len(agent.calls) == 4


def test_feedback_threads_prior_failure():
    agent = FakeAgent()
    harness_loop("t", agent, _gate_fail_then_pass(3), max_iters=5)
    assert agent.calls[0][1] is None  # 첫 호출엔 피드백 없음
    assert agent.calls[1][1] == "fail-1"  # 둘째 호출은 첫 실패를 받음


def test_slugify_task():
    assert slugify_task("Add feature X") == "add-feature-x"
    assert slugify_task("!!!") == "task"  # ASCII 영숫자 없으면 기본값


def test_build_prompt_gate_bypass_and_feedback():
    base = build_prompt("t", None)
    assert "우회" in base  # 게이트 우회 금지 문구
    assert "실패 로그" not in base
    assert "실패 로그" in build_prompt("t", "boom")


# ── main() 안전성: git·gh 를 모킹해 실제 PR 이 만들어지는 조건을 못박는다 ──


def _wire(monkeypatch, tree_states, gate_result):
    """_tree_dirty·_git·run_agent·run_gates·subprocess.run 을 가짜로 교체.

    반환된 (git_calls, gh_calls) 로 어떤 git/gh 명령이 불렸는지 검사한다.
    """
    git_calls: list = []
    gh_calls: list = []
    states = iter(tree_states)
    monkeypatch.setattr(loop, "_tree_dirty", lambda: next(states))
    monkeypatch.setattr(loop, "_git", lambda *a: git_calls.append(a))
    monkeypatch.setattr(loop, "run_agent", lambda task, feedback: None)
    monkeypatch.setattr(loop, "run_gates", lambda: gate_result)
    monkeypatch.setattr(loop.subprocess, "run", lambda *a, **k: gh_calls.append(a[0]))
    return git_calls, gh_calls


def test_main_no_commit_no_pr_on_gate_failure(monkeypatch):
    git_calls, gh_calls = _wire(monkeypatch, [False], (False, "boom"))
    assert loop.main(["prog", "t", "--max-iters", "2"]) == 1
    assert not any("commit" in a for a in git_calls)  # 커밋 안 함
    assert gh_calls == []  # gh pr create 안 함


def test_main_no_pr_when_agent_changed_nothing(monkeypatch):
    # 시작 clean, green 이후에도 clean = agent 가 아무것도 안 바꿈.
    git_calls, gh_calls = _wire(monkeypatch, [False, False], (True, "ok"))
    assert loop.main(["prog", "t"]) == 1
    assert not any("commit" in a for a in git_calls)
    assert gh_calls == []


def test_main_commits_but_no_pr_without_open_pr(monkeypatch):
    # 시작 clean, green 이후 dirty = agent 가 변경함. push/PR 은 생략.
    git_calls, gh_calls = _wire(monkeypatch, [False, True], (True, "ok"))
    assert loop.main(["prog", "t"]) == 0
    assert any("commit" in a for a in git_calls)  # 커밋함
    assert not any("push" in a for a in git_calls)  # push 안 함
    assert gh_calls == []  # PR 안 만듦


def test_main_pushes_and_prs_with_open_pr(monkeypatch):
    git_calls, gh_calls = _wire(monkeypatch, [False, True], (True, "ok"))
    assert loop.main(["prog", "t", "--open-pr"]) == 0
    assert any("push" in a for a in git_calls)  # push 함
    assert len(gh_calls) == 1
    assert gh_calls[0][:3] == ["gh", "pr", "create"]  # draft PR 생성


def test_main_aborts_on_dirty_tree(monkeypatch):
    git_calls, gh_calls = _wire(monkeypatch, [True], (True, "ok"))
    assert loop.main(["prog", "t"]) == 1
    assert git_calls == []  # 브랜치 생성조차 안 함
    assert gh_calls == []


def test_max_iters_must_be_positive():
    with pytest.raises(SystemExit):  # argparse.error → SystemExit
        loop.main(["prog", "t", "--max-iters", "0"])
