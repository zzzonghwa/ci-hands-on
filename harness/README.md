# pre-PR harness 루프

## 이게 가르치는 한 가지

**게이트(ruff·black·pytest)를 PR *이후*가 아니라 agent 반복 루프 *이전*으로 옮긴다.**
통과한 결과만 draft PR로 나간다. 발표 "Agents Need Continuous Compute"의 핵심
(control plane이 PR 파이프라인에서 agent harness로 이동)을 학습 규모에서 체험한다.

진단·배경: `../docs/2026-07-21-continuous-compute-gap.md`
설계: `../docs/specs/2026-07-21-pre-pr-harness-design.md`

## 의도(intent) 흐름 — ①⑥

사람은 코드가 아니라 **의도**를 넣는다. 대화(Claude Code)로 확정한 의도를
`intents/<slug>.md`(무엇·왜·**수용 기준**)로 적어 `--intent-file`로 넘기면:

- **①** 의도가 harness의 입력이 된다 (코드·PR을 사람이 직접 안 씀)
- **④** evaluator가 **수용 기준**을 rubric으로 accept/revise 판정
- **⑥** draft PR 본문에 의도+수용기준이 담겨, 사람은 **diff가 아니라 "수용 기준 충족?"**으로 승인

즉 입력(의도)·실행(harness)·승인(의도 충족)이 분리된다.

## 기존 self-healing과의 차이

| | claude-fix-ci.yml | harness/loop.py (이것) |
|---|---|---|
| 언제 | PR CI 실패 *이후* | PR 열기 *이전* |
| 게이트 위치 | 파이프라인 마지막 관문 | agent 루프의 매 반복 |
| 결과 | 실패를 사후 수리 | 통과분만 PR로 승격 |

## 실행

```bash
# 로컬 모드 (기본) — 브랜치 생성 + 커밋까지. push·PR 은 안 함(dry-run 아님)
python harness/loop.py "app.py에 clamp(x, lo, hi) 함수와 테스트 추가"

# 실제 push + draft PR 생성
python harness/loop.py "..." --open-pr

# 반복 횟수 조정 (기본 5, 1 이상)
python harness/loop.py "..." --max-iters 3

# evaluator(LLM 회의적 리뷰) 끄고 게이트만 (빠르게/저렴하게)
python harness/loop.py "..." --no-evaluator

# ①⑥ 의도 파일로 실행 — 의도+수용기준을 harness로 흘린다 (intents/TEMPLATE.md 참고)
python harness/loop.py --intent-file intents/add-clamp.md --open-pr
```

## 흐름

```
[0] 깨끗한 트리 확인 + harness/<slug> 브랜치 생성
[1] agent 구현/수정 (claude -p, Bash·git 권한 없음)
[2] 로컬 게이트 (ruff·black·pytest) — 결정론
[3] 게이트 green이면 evaluator(claude, 회의적 리뷰어)가 accept/revise 판정 — LLM
[4] accept → 종료 / revise → 리뷰를 되먹여 반복 / 2회 연속 동일 사유 → 조기 종료 / max 소진 → 종료
[5] green(게이트+accept)이면 harness가 커밋
[6] --open-pr이면 push + gh pr create --draft
```

## 안전장치

- **max 5회** + **무진전 조기 종료**(동일 실패 2회면 중단). `--max-iters`는 1 이상만
- **로컬 모드 기본** — `--open-pr` 없으면 브랜치·커밋까지만(push·PR 안 함). dry-run 아님
- **draft PR only** — 자동 머지 아님. 사람이 "의도+결과"를 승인
- **agent에 Bash·git 미부여** — `--disallowedTools "Bash"`로 명시 차단. 커밋·푸시·PR·게이트는 harness만. soft 경계(claude 권한 레이어 의존)
- **evaluator는 읽기 전용** — `--allowedTools "Read Grep Glob"`, 편집·커밋 불가. 자기검증 편향은 refute-first 프롬프트 + 코딩과 역할 분리로 완화(soft)
- **깨끗한 트리 강제** — 시작 시 dirty면 중단, green인데 변경 없으면 PR 안 만듦

## 전제

- `claude` CLI 로그인 완료(헤드리스 `claude -p` 사용)
- `gh` CLI 로그인 완료(`--open-pr` 시)
- 현재 브랜치가 base(main)이고 작업 트리가 깨끗함
