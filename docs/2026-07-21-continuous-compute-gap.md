# 현 상태 진단 — 우리 CI/CD는 "Agent 시대 Continuous Compute"와 얼마나 먼가

작성일: 2026-07-21
대상: `hands-on/` 저장소의 CI/CD 실제 구현
비교 기준: 발표 "CI/CD Is Dead, Agents Need Continuous Compute" (Hugo Santos, Madison Faulkner / Namespace)
소스: https://www.youtube.com/watch?v=VktrqzQgytY

## 문제 정의

발표는 기존 CI/CD가 "인간이 소수 diff를 만들고 PR로 협업"하는 전제 위에 설계됐고, Agent가 브랜치·변경을 대량 병렬 생성하면 PR·CI·merge가 병목이 된다고 주장한다. 해법은 "CI 폐기"가 아니라 build·test·정책검증을 **PR 이후 게이트에서 Agent의 반복 루프(harness) 안으로 옮기는 것** — 즉 control plane이 PR pipeline에서 agent harness로 이동한다는 것이다.

이 문서는 우리 `hands-on/` 구현이 그 모델과 어디가 같고 다른지를 파일 근거로 대조한다.

## 한 줄 결론

우리 CI/CD는 발표가 "낡은 세계"라 부르는 **PR 중심 모델 그대로**이고, 거기에 AI 헬퍼 3개(리뷰·수리·대시보드)를 볼트온한 상태다. 발표가 "agent 규모가 되면 병목이 드러난다"고 지목한 **중간 지대**에 정확히 서 있다.

## 6요소 대조

| 발표 제안 | 우리 구현 | 근거 파일 | 판정 |
|---|---|---|---|
| ① Intent & Plan (사람은 코드 아닌 의도를 명시) | 사람이 코드·PR을 직접 만든다 | — | ❌ 없음 |
| ② Agent harness loop (PR *이전* checkout→build→test 반복) | **`harness/loop.py` 구현(2026-07-24)** — PR 열기 전 agent→gate 반복, 통과분만 draft PR. (기존 `claude-fix-ci`는 PR 사후 수리로 별개 유지) | `harness/loop.py` | ✅ 구현 |
| ③ 내부 검증 상시화 (build/test가 매 iteration의 일부) | **harness가 매 반복마다 ruff·black·pytest(cov100) 게이트 실행(2026-07-24).** ci.yml의 마지막-게이트도 그대로 유지(이중) | `harness/loop.py`, `.github/workflows/ci.yml` | ✅ 구현 |
| ④ Agent 외부 검증 (evaluator가 주 agent에 피드백) | **harness가 게이트 실패 로그를 다음 반복의 프롬프트로 되먹임(2026-07-24)** = 결정론적 evaluator→코딩 agent 피드백. (LLM evaluator는 아님) `claude-review`는 여전히 사람용 | `harness/loop.py`, `.github/workflows/claude-review.yml` | 🔸→✅ 결정론 게이트 되먹임 |
| ⑤ Pre-merge queue (repo 반영 전 충돌·의존성 조정) | 구현 + org 데모에서 직렬화 실물 관찰 완료 (2026-07-24). 단 개인 repo는 org가 아니라 미가동(무해한 no-op) | `.github/workflows/ci.yml`, `docs/2026-07-24-merge-queue-implementation.md` | ✅ 실증 (개인 repo는 org 필요) |
| ⑥ Human approval 재배치 (diff 아닌 "의도+결과" 승인) | `deploy` 잡의 `environment: production` = **PR/커밋 단위 승인** | `.github/workflows/ci.yml` | ❌ 없음 |

## Continuous Compute 4조건 대조

| 조건 | 우리 구현 | 판정 |
|---|---|---|
| build/test가 agent loop에 들 만큼 빠름 | 매트릭스 3버전 + docker build + mutation = gate용 속도 | ❌ |
| stateful·incremental 환경 | `runs-on: ubuntu-latest` 매번 깨끗한 ephemeral 러너지만 **pip 캐시 복원(B안, 2026-07-24)**. 진짜 warm workspace는 아님 | 🔸 캐시 복원 수준 |
| cache가 orchestration 계층 | **`setup-python` `cache: pip`으로 requirements-dev.txt 해시 키 캐시 도입(B안).** 1회 miss→저장, 이후 hit | ✅ (test 잡) |
| 병렬 후보 탐색 수용 | 단일 diff 선형 파이프라인 | ❌ |

## 우리가 서 있는 위치

발표 프레임으로 요약하면: **human-centric PR 파이프라인 + AI 헬퍼 볼트온.** 이미 노트 02·03이 방향의 씨앗("CI 러너가 agent 실행 환경이 된다", "agent 산출물도 파이프라인에 거주")을 담고 있고, `claude-fix-ci`가 ②④의 초기 형태다. 그러나 핵심(harness가 control plane)은 아직 없다.

## 균형추 (과신 금지)

- 발표는 **Namespace CEO의 포지션 토크**다. 그들은 stateful compute를 판다. "CI/CD의 종말"을 업계 합의로 읽으면 안 된다.
- 우리 저장소는 **학습용**이고, agent가 수천 브랜치를 병렬 생성하는 규모가 아니다. 그 규모가 아니면 발표 구조 전체 이식은 과설계다.
- 따라서 목표는 "발표대로 재건축"이 아니라 **발표의 핵심 문제의식을 학습 규모에서 체험**하는 것이다.

## 격차 해소 로드맵 (비용·학습가치 순)

세 후보. 셋 다 외부 인프라 0원, GitHub·gh CLI 안에서 해결.

### A. merge queue 켜기 — ⑤ pre-merge 체험

- 방법: `merge_group` 트리거를 `ci.yml`에 추가 + 저장소 설정에서 merge queue 활성화
- 비용: 낮음 (트리거 1줄 + 설정)
- 학습가치: 중. 발표의 "변경을 단일 ledger에 직렬화" 개념의 네이티브 관문 버전을 눈으로 봄
- 한계: 규모가 없으면 큐가 실제로 붐비는 걸 체감하긴 어려움

### B. actions/cache 얹기 — Continuous Compute의 stateful 첫걸음

- 방법: `ci.yml` test 잡에 pip 캐시 + pytest 캐시 추가
- 비용: 낮음
- 학습가치: 중상. "매번 clean" → "이전 상태 재사용"으로 바뀌는 걸 실행 시간 감소로 체감. 발표의 D조건 입문
- 한계: 진짜 stateful 러너(warm workspace)까지는 아님. 캐시 복원 수준

### C. pre-PR harness inner loop — ②③ 발표 핵심 체험

- 방법: PR 열기 *전에* 로컬/러너에서 agent가 build→test→수정을 반복하고, 통과한 결과만 PR로 올리는 스크립트/워크플로. 지금의 "PR 실패 후 수리"를 "PR 이전 반복"으로 이동
- 비용: 중 (새 harness 스크립트 + 루프 종료조건 설계)
- 학습가치: 상. 발표의 control plane 이동을 직접 구현. 강의 Project 4의 자연스러운 다음 확장
- 한계: 가장 큰 작업. 무한루프·비용 상한 등 안전장치 필요

## If/Then 권장 순서

- If 가장 싸게 발표 개념 하나를 관문으로 켜보고 싶다 → Then **A(merge queue)** 부터. 반나절
- If "매번 clean vs 상태 재사용"의 체감을 먼저 얻고 싶다 → Then **B(cache)**. 실행 시간 before/after 비교가 학습 포인트
- If 발표의 진짜 핵심(harness가 control plane)을 구현해보고 싶다 → Then **C(pre-PR loop)**. 앞 둘을 건너뛰어도 됨

## 핵심 포인트 요약

1. 현재는 PR 중심 + AI 볼트온 = 발표가 지목한 병목 중간 지대.
2. 6요소 중 ②④만 씨앗 수준, ①③⑤⑥은 없음. Continuous Compute 4조건은 전부 미충족.
3. 발표는 포지션 토크·학습 규모 아님 → 전체 이식이 아니라 핵심 개념 체험이 목표.
4. 다음 한 걸음: A(싸게 관문) / B(체감) / C(핵심) 중 택1.
