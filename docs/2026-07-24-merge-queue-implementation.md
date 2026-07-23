# 구현 기록 — pre-merge 직렬화(merge queue) + CI 큐 병목 완화

작성일: 2026-07-24
대상: `hands-on/.github/workflows/ci.yml`, `claude-review.yml`
비교 기준: 발표 "CI/CD Is Dead, Agents Need Continuous Compute" (Hugo Santos, Madison Faulkner / Namespace)
소스: https://www.youtube.com/watch?v=VktrqzQgytY
선행 진단: `docs/2026-07-21-continuous-compute-gap.md` (⑤ Pre-merge queue = ❌ 없음 → Option A로 지목)

## 문제 정의

발표 논지: Agent가 변경을 대량 병렬 생성하면 병목은 사라지지 않고 **CI 큐와 사람 리뷰로 이동**한다. 처방 중 GitHub 네이티브로 구현 가능한 것은 **병렬 변경의 pre-merge 직렬화** = merge queue다. 이 문서는 그것을 실제로 어떻게 구현했는지 파일·설정 근거로 남긴다.

## 핵심 원리 (구현이 근거로 삼은 것)

1. **취소 ≠ 직렬화.** `concurrency: cancel-in-progress`는 같은 PR의 낡은 실행을 버려 큐 낭비를 줄인다. merge queue는 서로 다른 PR을 순서 매겨 하나씩 검증한다. 둘은 다른 병목을 친다 — 둘 다 필요.
2. **merge queue는 "main + 앞선 큐 항목" 합본에서 CI를 돌린다.** 그래서 A가 통과했어도 B가 A와 합쳐지면 깨지는 경우를 merge 전에 잡는다 = pre-merge reconciliation.
3. **필수 체크 "전부"가 merge_group에서 돌아야 한다.** 이 저장소의 required check는 `ci-success`(ci.yml)와 `CodeQL`(codeql.yml) **둘**이다. 하나라도 merge_group 트리거가 없으면 그 체크가 큐 항목에서 영원히 pending → **큐 영구 정지.** (GitHub 문서: merge queue를 쓰는 required check은 반드시 merge_group 이벤트로 트리거되도록 워크플로를 갱신해야 한다.)
4. **main(배포 경로)은 취소하면 안 된다.** 배포 중 커밋이 취소되면 릴리스가 깨진다.

### 검증으로 바로잡은 오해 (2026-07-24)

- ❌ (초기 오판) "merge_group은 default branch(main)의 워크플로 파일을 읽으므로 트리거를 main에 먼저 머지해야 발동한다."
- ✅ (문서 확인) merge_group은 **머지 그룹 ref**(`gh-readonly-queue/{base}/...` = base + 앞선 PR들 + 해당 PR)에서 실행된다. PR이 ci.yml에 추가한 merge_group 트리거는 그 머지 그룹 커밋에 포함되므로 **선행 머지 없이도 발동**한다. (초기 오판은 `pull_request_target`의 "default branch에서 실행" 동작을 혼동한 것.)
  - 출처: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#merge_group (GITHUB_REF="Ref of the merge group", merge_group엔 "default branch" 제약 문구 없음)
- 다만 **실무 권장은 트리거를 main에 먼저 두는 것**이다. 이유는 "발동 조건" 때문이 아니라, ①앞으로 열리는 모든 PR의 ci.yml·codeql.yml이 트리거를 자동 포함하고 ②required check이 매 머지 그룹에서 확실히 재현되기 때문이다.

## 실행 방법 (실제 변경 내역)

### 1. `merge_group` 트리거 추가 — `ci.yml`

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  merge_group: # merge queue가 만든 임시 브랜치(main+앞선 PR들 합본)에서 CI를 돌린다 = pre-merge 직렬화.
    branches: [main]
```

효과: merge queue가 큐 항목마다 `gh-readonly-queue/main/pr-<N>-<sha>` 임시 브랜치를 만들고 `merge_group` 이벤트를 발생 → `ci-success`까지 전 게이트가 그 합본에서 재실행된다.

### 1b. `merge_group` 트리거 추가 — `codeql.yml` (필수 체크라 반드시 필요)

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  merge_group: # CodeQL은 필수 체크다. merge queue 항목의 merge_group에서도 돌지 않으면 큐가 영구 정지한다.
    branches: [main]
```

이유: 브랜치 보호의 required check = `ci-success` + **`CodeQL`**. CodeQL이 merge_group에서 안 돌면 큐가 CodeQL을 영원히 기다린다. (원리 3)

### 2. `concurrency` 블록 추가 — `ci.yml` (CI 큐 병목)

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}
```

- PR 커밋 연타(synchronize) 시 같은 ref의 낡은 실행을 취소 → 큐 적체 방지.
- `github.ref != 'refs/heads/main'` 가드: main push(=배포)는 취소 안 함.
- merge_group 실행은 큐 항목마다 ref가 고유(`gh-readonly-queue/...`)라 서로 취소하지 않음 → **직렬화가 보존됨.**

### 3. `concurrency` 블록 추가 — `claude-review.yml` (리뷰 병목)

```yaml
concurrency:
  group: claude-review-${{ github.event.pull_request.number }}
  cancel-in-progress: true
```

효과: 커밋 연타 시 낡은 커밋에 대한 AI 리뷰를 취소하고 최신 것만 남긴다. "리뷰로 이동한 병목"의 낭비분 제거.

### 4. 저장소 설정 — merge queue 활성화 (UI, 1회)

> ⚠️ 이 저장소는 **classic branch protection**(required checks: `ci-success`, `CodeQL`)을 쓴다. merge queue는 classic 규칙에선 REST API로 켤 수 없고 UI 체크박스로만 켠다. (rulesets를 새로 만드는 방법도 있으나 classic과 겹쳐 동작이 혼란스러워지므로 채택 안 함.)

절차:
1. GitHub → **Settings → Branches → `main` 규칙 Edit**
2. **Require merge queue** 체크
3. Merge method / build concurrency 등은 기본값 유지
4. Save

If 이 체크를 안 하면 → Then `merge_group` 트리거는 영원히 발생하지 않고 워크플로 변경은 무해한 no-op으로 남는다 (기존 PR CI는 그대로 동작).

## 기존 게이트와의 정합성 (깨지지 않음 확인)

| 잡 | merge_group 이벤트에서 | 판정 |
|---|---|---|
| `dependency-review` (`if: pull_request`) | skip | ✅ `ci-success`가 skipped 허용 처리 이미 있음 (`ci.yml`) |
| `ci-success` (`if: always()`, 이벤트 가드 없음) | 실행됨 | ✅ required check 재현 → 큐 안 멈춤 |
| `deploy` (`if: event_name == 'push' && ref == main`) | 실행 안 됨 | ✅ 큐 merge 후 main push에서만 배포 |

## 핵심 포인트 요약

- ✅ 구현 완료(코드): `merge_group` 트리거 + `concurrency` 2개. → `docs/2026-07-21-continuous-compute-gap.md`의 ⑤ 갭을 닫음.
- ☐ 남은 1단계(사람): Settings에서 **Require merge queue** 체크. 이걸 켜야 실제 작동.
- 취소(concurrency)와 직렬화(merge queue)는 다른 병목을 침 — 둘 다 유지.
- 학습 한계: 규모가 없으면 큐가 붐비는 걸 체감하긴 어렵다. 개념·관문의 동작 확인이 목적.
