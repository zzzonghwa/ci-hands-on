# CI 운영 가시성 설계 — 대시보드 + Gmail 알림 + 비용 추적

작성일: 2026-07-21
상태: 승인됨
참고: FastCampus "실리콘밸리 바이브코딩" Project 4의 4단계(실패 분석 → 수정 → PR 생성 → 운영 추적) 중 이 저장소에 없던 마지막 단계 "운영 추적"을 구현한다. 노트 08(배포 후 검증·파이프라인 관찰)의 실습에 해당한다.

## 문제 정의

self-healing CI(`claude-fix-ci.yml`)와 AI 리뷰(`claude-review.yml`)는 이미 돌고 있지만, "에이전트가 실제로 얼마나 잘 고치는지, 파이프라인이 얼마나 자주 깨지는지, 비용이 얼마나 드는지"를 볼 수 있는 곳이 없다.

## 원칙

1. **관찰자는 개입하지 않는다** — 기존 워크플로 3개(`ci.yml`, `claude-fix-ci.yml`, `claude-review.yml`)는 한 줄도 수정하지 않는다.
2. **외부 인프라 0원** — GitHub 안에서 전부 해결. 대시보드는 저장소에 커밋되는 마크다운.
3. **알림은 사람 개입이 필요한 경우에만** — 에이전트가 처리하는 영역은 대시보드에만 기록.

## 아키텍처

```
hands-on/
├── .github/workflows/
│   ├── dashboard.yml        ← [신규] cron 매일 1회 + workflow_dispatch
│   └── notify.yml           ← [신규] main CI 실패·Claude Fix CI 실패 시 Gmail 알림
├── scripts/
│   └── ci_dashboard.py      ← [신규] gh CLI로 run 데이터 집계 → dashboard.md 생성
├── test_ci_dashboard.py     ← [신규] 집계 로직 최소 테스트
└── dashboard.md             ← [생성물] 커밋되는 대시보드
```

## 컴포넌트

### 1. `scripts/ci_dashboard.py`

입력: `gh run list --json` (최근 30일). 출력: `dashboard.md`.

| 지표 | 산출 방법 |
|---|---|
| 워크플로별 성공/실패율 | CI·Claude Review·Claude Fix CI·CodeQL 각각 성공 수/전체 수 |
| 평균 실행 시간 | run별 duration 평균 |
| 최근 실패 목록 | 최근 실패 10건 — 브랜치·커밋·로그 링크 |
| 에이전트 수리 성공률 | Claude Fix CI 실행 후 같은 브랜치의 다음 CI run이 성공했는지 추적. "self-healing이 실제로 작동하는가"를 숫자로 보는 핵심 학습 지표 |
| 비용 ① | Actions 소요 시간 합계 (public repo라 무료지만 추세 확인) |
| 비용 ② | Claude 토큰 비용 — `gh run view --log`에서 claude-code-action의 cost 라인 파싱. 파싱 실패 시 "N/A" (best-effort, 게이트 아님) |

에러 처리: gh API 호출 실패 시 기존 `dashboard.md`를 덮어쓰지 않고 비-zero exit로 종료한다.

### 2. `dashboard.yml`

- 트리거: `schedule` (매일 1회, UTC 21:00 = KST 06:00) + `workflow_dispatch`
- 권한: `contents: write` (dashboard.md 커밋), `actions: read` (run 데이터 조회)
- 단계: checkout → `python scripts/ci_dashboard.py` → 변경 있으면 `[skip ci]` 커밋·푸시 (CI 재귀 트리거 차단)

### 3. `notify.yml`

- 트리거: `workflow_run` (CI, Claude Fix CI의 `completed`)
- 알림 조건 (If/Then):

| 조건 | 행동 | 이유 |
|---|---|---|
| main 브랜치 CI 실패 | Gmail 알림 | 에이전트가 안 도는 영역(안전장치) = 사람이 즉시 알아야 함 |
| Claude Fix CI 자체가 실패 | Gmail 알림 | "수리공이 고장" = self-healing 루프 중단 |
| PR 브랜치 CI 실패 | 알림 없음 | 에이전트 처리 영역, 알림 피로 방지 |

- 전송: `dawidd6/action-send-mail` 액션 1스텝, Gmail SMTP(smtp.gmail.com:465) 경유. 제목에 워크플로명·브랜치, 본문에 실패 run 링크.
- 왜 GitHub 내장 이메일 알림이 아닌가: 내장 알림은 본인이 트리거한 run의 실패만 메일을 보낸다. 핵심 알림 대상인 "Claude Fix CI 자체 실패"는 에이전트가 트리거하므로 내장 알림이 닿지 않는다.
- 준비물: Google 계정 2단계 인증 → 앱 비밀번호(16자리) 발급 → 저장소 시크릿 `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` 등록. 수신자 = 발신자(본인 Gmail).
- 시크릿 미설정 시: 알림 단계는 경고만 출력하고 성공 종료 (대시보드는 알림 없이도 동작해야 함).

## 테스트

- `test_ci_dashboard.py`: 가짜 run JSON을 입력해 성공률·수리 성공률 계산을 검증하는 최소 테스트. 기존 CI 게이트(pytest·ruff·black)를 그대로 통과해야 한다.
- notify.yml은 조건 분기가 워크플로 `if:`에 있으므로 별도 테스트 없음. main에 일부러 실패를 만들지 않고, `workflow_dispatch`로 대시보드만 수동 검증한다.

## 범위 밖 (YAGNI)

- 외부 대시보드(Grafana/Datadog) — 학습 저장소에 과설계
- PR 브랜치 실패 알림 — 에이전트 영역
- main 실패 자동 수리(Phase C — 수리 브랜치 생성 → draft PR) — 별도 스펙으로 분리
