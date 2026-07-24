# pre-PR harness 루프 설계 (검증 반영본)

작성일: 2026-07-21
상태: 승인됨 (구멍 1 + 하드닝 3 반영)
목적: build/test 게이트를 PR *이후* 게이트가 아니라 agent 반복 루프 *이전*으로 옮긴다. 발표 "Continuous Compute"의 ②harness loop·③내부 검증 상시화·⑥결과 승인을 학습 규모에서 체험. 진단: `docs/2026-07-21-continuous-compute-gap.md`

## 제어 흐름 (검증 반영)

```
intent(task) 입력
  → [0] 깨끗한 작업트리 확인 + 새 브랜치 생성 (harness/<slug>)   ← 구멍 1 수정
  → [1] agent 구현/수정 (claude -p, Bash·git 권한 없음)
  → [2] 로컬 게이트 실행 (ruff · black · pytest — ci.yml과 동일 계열)
  → [3] 판정:
        · 초록불          → 루프 종료(green)
        · 2회 연속 동일 실패 → 조기 종료(no_progress)              ← 하드닝 1
        · max 5회 소진    → 종료(exhausted)
        · 아니면          → 실패 로그 되먹임 후 [1] 반복
  → [4] green이면: agent 변경을 커밋 (harness가 수행)              ← 구멍 1 수정
  → [5] push + gh pr create --draft   (--open-pr 플래그일 때만)     ← 구멍 1 수정
```

## 반영된 수정

### 구멍 1 — 브랜치·커밋·푸시 (치명적)
`gh pr create`는 base가 아닌 브랜치 + 커밋 + push를 전제한다. 원설계는 이를 빠뜨려 빈 PR/실패를 낳았다. → [0] 브랜치 생성, [4] 커밋, [5] push를 harness가 명시 수행.

### 하드닝 1 — 무진전 감지
게이트 출력이 2회 연속 동일하면(agent가 같은 실패를 반복) 조기 중단. max-iter만으론 못 잡음.

### 하드닝 2 — 깨끗한 트리 강제
시작 시 `git status --porcelain`이 비었는지 확인. 아니면 중단. 기존 미커밋 변경이 agent diff에 섞여 PR이 오염되는 것을 차단. green 이후에도 변경이 없으면(agent가 아무것도 안 고침) PR을 만들지 않는다.

### 하드닝 3 — git 권한은 harness만
agent의 `--allowedTools`는 `Edit·Read·Write·Grep·Glob`만. **Bash·git 미부여.** 커밋·푸시·PR·게이트 실행은 전부 harness가 결정론적으로 수행 → 게이트 우회·자기 PR 생성 원천 차단.

## 파일

- `harness/loop.py` — 루프 오케스트레이터. `harness_loop(task, agent_fn, gate_fn, max_iters)`는 agent·gate를 주입받는 순수 제어 함수(네트워크·LLM 없이 테스트 가능). `main()`이 실제 `claude -p`·git·`gh`를 연결
- `harness/__init__.py` — 패키지 마커
- `harness/README.md` — 실행법 + "게이트가 루프 안으로 이동" 개념
- `test_harness.py` — 루프 제어 테스트(green 정지·no_progress·exhausted·실패 시 non-green·피드백 되먹임·slugify·prompt)

## 안전장치

- max 5회 반복(무한루프 차단) + 무진전 조기 종료
- `--max-iters` 0·음수 거부(argparse.error)
- 기본은 브랜치·커밋까지(로컬 모드), `--open-pr`일 때만 push·PR — "dry-run"이 아님을 메시지에 명시
- draft PR only(자동 머지 아님 = ⑥)
- 게이트 우회 금지: 프롬프트 명시 + `--allowedTools`(Edit/Read/Write/Grep/Glob) + `--disallowedTools "Bash"`로 이중 차단. allowedTools는 whitelist가 아니라 "무프롬프트 허용"이라 disallowedTools가 실제 차단. soft 경계(claude 권한 레이어 의존, 커널 샌드박스 아님)

## codex 검증 반영 (2차)

구현 후 codex(0.144.6)가 실제 코드를 검토해 지적한 것 중 실결함만 반영:

- agent Bash 차단이 soft했음 → `--disallowedTools "Bash"` 추가
- "dry-run"이 실제로 브랜치·커밋을 남김 → "로컬 모드"로 정직하게 재명명
- `--max-iters` 무검증 → 1 이상 강제
- main()의 PR-차단이 미검증 → git·gh 모킹으로 main() 안전성 6개 테스트 추가(실패 시·무변경 시 PR 안 만듦, `--open-pr` 유무별 push/PR, 더러운 트리 중단)
- 게이트가 ci.yml과 불일치(`pytest -q`) → `pytest --cov=app --cov-fail-under=100`으로 일치

넘긴 것(문서화): 로그 정확일치 취약성(best-effort), 3버전 매트릭스(로컬 불가), submodule(이 repo 없음), 게이트 전후 porcelain 비교(.gitignore가 `__pycache__`·`.pytest_cache`·`.coverage`를 이미 무시)

## 범위 밖 (YAGNI)

- stateful 러너·cache(B안), merge queue(A안), 병렬 후보 탐색
- 토큰/비용 상한 — max-iter 캡이 학습 규모엔 충분
- 브랜치 이름 충돌 자동 회피 — 존재 시 git이 실패로 알림(정직)
