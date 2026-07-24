# pre-PR harness 루프

## 이게 가르치는 한 가지

**게이트(ruff·black·pytest)를 PR *이후*가 아니라 agent 반복 루프 *이전*으로 옮긴다.**
통과한 결과만 draft PR로 나간다. 발표 "Agents Need Continuous Compute"의 핵심
(control plane이 PR 파이프라인에서 agent harness로 이동)을 학습 규모에서 체험한다.

진단·배경: `../docs/2026-07-21-continuous-compute-gap.md`
설계: `../docs/specs/2026-07-21-pre-pr-harness-design.md`

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
```

## 흐름

```
[0] 깨끗한 트리 확인 + harness/<slug> 브랜치 생성
[1] agent 구현/수정 (claude -p, Bash·git 권한 없음)
[2] 로컬 게이트 (ruff·black·pytest)
[3] 초록불? → 종료 / 2회 연속 동일 실패 → 조기 종료 / max 소진 → 종료 / 아니면 되먹임 후 반복
[4] green이면 harness가 커밋
[5] --open-pr이면 push + gh pr create --draft
```

## 안전장치

- **max 5회** + **무진전 조기 종료**(동일 실패 2회면 중단). `--max-iters`는 1 이상만
- **로컬 모드 기본** — `--open-pr` 없으면 브랜치·커밋까지만(push·PR 안 함). dry-run 아님
- **draft PR only** — 자동 머지 아님. 사람이 "의도+결과"를 승인
- **agent에 Bash·git 미부여** — `--disallowedTools "Bash"`로 명시 차단. 커밋·푸시·PR·게이트는 harness만. soft 경계(claude 권한 레이어 의존)
- **깨끗한 트리 강제** — 시작 시 dirty면 중단, green인데 변경 없으면 PR 안 만듦

## 전제

- `claude` CLI 로그인 완료(헤드리스 `claude -p` 사용)
- `gh` CLI 로그인 완료(`--open-pr` 시)
- 현재 브랜치가 base(main)이고 작업 트리가 깨끗함
