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

### 4. 저장소 설정 — merge queue 활성화 (⚠️ 이 저장소에선 불가)

> **플랫폼 제약 (2026-07-24 공식 문서 확인):** merge queue는 **조직(org) 소유 저장소에서만** 제공된다.
> 원문: "Pull request merge queues are available in any **public repository owned by an organization**, or in private repositories owned by organizations using GitHub Enterprise Cloud."
> 출처: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue
>
> 이 저장소 `zzzonghwa/ci-hands-on`은 **개인 계정 소유**라 merge queue를 켤 수 없다. 그래서 classic 브랜치 보호에 "Require merge queue" 체크박스가 아예 나타나지 않는다(ruleset 경로도 org 조건은 동일). 조직으로 이전/신규 생성해야 활성화 가능하다.

org 소유 저장소라면 활성화 절차:
1. GitHub → **Settings → Branches → 대상 브랜치 규칙 Edit** → **Require merge queue** 체크 → Save, 또는
2. **Ruleset**으로: `POST /repos/{org}/{repo}/rulesets`에 `merge_queue` 룰(필수 파라미터 7개: check_response_timeout_minutes, grouping_strategy, max_entries_to_build/merge, merge_method, min_entries_to_merge, min_entries_to_merge_wait_minutes) 추가.

**이 저장소에서 현재 상태:** `merge_group` 트리거는 발동하지 않는 **무해한 no-op**(향후 org 이전 시 즉시 작동). `concurrency` 블록은 org 여부와 무관하게 **지금 작동**한다.

## 기존 게이트와의 정합성 (깨지지 않음 확인)

| 잡 | merge_group 이벤트에서 | 판정 |
|---|---|---|
| `dependency-review` (`if: pull_request`) | skip | ✅ `ci-success`가 skipped 허용 처리 이미 있음 (`ci.yml`) |
| `ci-success` (`if: always()`, 이벤트 가드 없음) | 실행됨 | ✅ required check 재현 → 큐 안 멈춤 |
| `deploy` (`if: event_name == 'push' && ref == main`) | 실행 안 됨 | ✅ 큐 merge 후 main push에서만 배포 |

## 직렬화 실물 관찰 (org 데모, 2026-07-24)

개인 계정 repo에선 merge queue를 못 켜므로, 무료 org `hongjonghwa`에 일회용 데모 repo(`merge-queue-demo`)를 만들어 관찰했다. ruleset API로 `merge_queue` 룰 + 필수체크(`check`)를 활성화하고, 90초짜리 CI로 큐를 눈에 보이게 했다.

서로 다른 파일을 건드리는 PR 2개를 큐에 넣었을 때(`min_entries_to_merge: 2`로 그룹화 강제), 두 임시 브랜치가 동시에 존재하며 적층됐다:

| 큐 임시 브랜치 | 포함 파일 | = |
|---|---|---|
| `gh-readonly-queue/main/pr-3-…` | `alpha.txt` | main + A |
| `gh-readonly-queue/main/pr-4-…` | `alpha.txt`, `beta.txt` | main + A + **B** |

→ 뒤 항목(B)의 큐 브랜치가 앞 항목(A)의 파일을 포함 = **pre-merge 직렬화 확인.** 둘 다 merge_group CI 통과 후 함께 머지.

부수 관찰: 같은 파일 끝줄을 각각 고친 PR 2개는, 앞 PR 머지 직후 뒤 PR이 `CONFLICTING`으로 큐에서 자동 탈락 = "조정 실패 시 머지 전 차단" 동작.

## 핵심 포인트 요약

- ✅ 코드 구현 완료: `merge_group` 트리거(ci·codeql) + `concurrency`(ci·review) 2개.
- ✅ `concurrency`는 지금 작동 → "CI 큐/리뷰 병목" 절반 실현.
- ⛔ `merge_group`(pre-merge 직렬화)은 **org 소유 저장소에서만** 활성화 가능. 이 개인 계정 repo에선 무해한 no-op → 직렬화 실물 관찰은 별도 org 데모 repo에서 수행(2026-07-24).
- 취소(concurrency)와 직렬화(merge queue)는 다른 병목을 침 — 둘 다 유지.
