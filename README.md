# GitHub Actions 최소 CI 파이프라인 실습

작성일: 2026-07-07

## 실습 목표

CI가 실제로 도는 것을 한 번 본다. 그게 전부다.

- 코드를 푸시하면 GitHub이 자동으로 테스트를 실행하는 것을 눈으로 확인한다.
- 테스트를 일부러 깨뜨려 빨간불(실패)을 본다. 초록불만 보면 CI를 배운 게 아니다.

구성은 의도적으로 최소다: 의존성은 pytest 하나, 워크플로 단계는 4개(checkout → setup-python → pytest 설치 → pytest 실행). 매트릭스 빌드, 캐싱, 배지는 없다.

## 파일 구성

```
hands-on/                      ← 이 폴더가 저장소 루트가 된다
├── README.md                  ← 이 문서
├── app.py                     ← 순수 함수 3개 (add, is_even, slugify)
├── test_app.py                ← pytest 스타일 테스트 3개
├── .gitignore                 ← __pycache__/ 등 생성물 제외
└── .github/
    └── workflows/
        └── ci.yml             ← CI 워크플로 정의
```

## 사전 준비


| 항목          | 확인 방법                                                                                 |
| ----------- | ------------------------------------------------------------------------------------- |
| GitHub 계정   | [https://github.com](https://github.com) 로그인 가능                                       |
| Python 3    | `python3 --version` 출력 확인                                                             |
| git         | `git --version` 출력 확인                                                                 |
| gh CLI (권장) | `gh --version` 출력 후 `gh auth status`로 로그인 확인. 없으면 `brew install gh` 후 `gh auth login` |


gh CLI 없이 웹으로도 가능하다 (단계 2의 대안 참고).

## 중요: 저장소 루트 위치

`**.github/` 디렉터리는 저장소 루트에 있어야 GitHub이 워크플로를 인식한다.**

따라서 상위 폴더(`learning/cicd/`)가 아니라 **이 `hands-on/` 폴더 자체를 저장소 루트로 삼아 `git init` 한다.** 상위 폴더에서 init 하면 워크플로 경로가 `hands-on/.github/workflows/ci.yml`이 되어 CI가 절대 실행되지 않는다.

## 단계 1: 로컬에서 테스트 통과 확인

푸시하기 전에 로컬에서 먼저 돌려본다. pytest 설치 없이 실행된다.

```bash
cd ~/learning/cicd/hands-on
python3 test_app.py
```

기대 출력:

```
OK: 3개 테스트 모두 통과
```

If 위 출력이 나오지 않으면 → 단계 2로 넘어가지 말고 오류를 먼저 해결한다. 로컬에서 깨진 테스트는 CI에서도 깨진다.

## 단계 2: 저장소 생성과 푸시

`hands-on/` 안에서 그대로 실행한다. 단계 1에서 생긴 `__pycache__/`는 `.gitignore`가 걸러주므로 그대로 두면 된다.

```bash
cd ~/learning/cicd/hands-on
git init
git add .
git commit -m "feat: 최소 CI 파이프라인 실습"
gh repo create ci-hands-on --public --source=. --push
```

- `--source=.` : 현재 폴더를 원격 저장소의 소스로 사용
- `--push` : 로컬 커밋을 새 저장소로 즉시 푸시
- `--public` : public으로 만든다. **public 저장소는 GitHub-hosted 러너 사용이 과금 무료라 분(minute) 소모 걱정이 없다** (아래 무료 티어 한도 참고). private으로 하려면 `--private`로 바꾼다.

대안 (gh CLI 없이 웹으로): github.com에서 빈 저장소를 만든 뒤 아래를 실행한다.

```bash
git remote add origin https://github.com/<내계정>/ci-hands-on.git
git branch -M main
git push -u origin main
```

## 단계 3: CI 실행 확인 — 초록불과 빨간불 둘 다 본다

### 3-1. 초록불 확인

푸시 직후 저장소 페이지의 **Actions 탭**을 연다. `CI` 워크플로가 실행 중이거나 완료되어 있다.

```bash
gh run watch
```

주의: 푸시 직후에는 런이 아직 생성되지 않아 `gh run watch`가 못 찾을 수 있다. If "no runs found" → 5~10초 기다렸다가 재시도한다. 목록으로 보려면:

```bash
gh run list
```

워크플로 실행을 클릭해 `test` 잡의 각 단계(checkout → setup-python → Install pytest → Run tests) 로그를 열어본다. `3 passed`가 보이면 성공이다.

### 3-2. 빨간불 확인 (일부러 깨뜨리기)

`app.py`의 `add` 함수를 일부러 틀리게 고친다.

```bash
# add 함수의 return a + b 를 return a - b 로 변경 후:
git add app.py
git commit -m "test: 일부러 테스트 깨뜨리기"
git push
```

Actions 탭에서 빨간 X를 확인하고, 실패 로그에서 `assert add(2, 3) == 5` 가 어떻게 표시되는지 읽어본다. 커밋 목록과 (있다면) PR에도 빨간 X가 붙는 것을 확인한다. **이것이 CI의 존재 이유다: 깨진 코드가 조용히 섞여 들어오는 것을 막는다.**

확인했으면 원복한다.

```bash
# return a - b 를 return a + b 로 되돌린 후:
git add app.py
git commit -m "fix: 테스트 원복"
git push
```

다시 초록불이 되면 실습의 핵심은 끝났다.

## ci.yml 해설

```yaml
on:
  push:
    branches: [main]        # main에 푸시될 때
  pull_request:
    branches: [main]        # main 대상 PR이 열리거나 갱신될 때

permissions:
  contents: read            # 토큰 권한을 읽기로 최소화

jobs:
  test:
    runs-on: ubuntu-latest  # Linux 러너 (private 저장소 기준 가장 저렴: 배수 1배)
    steps:
      - uses: actions/checkout@v7      # 저장소 코드 내려받기 (2026-06-18 GA된 최신 메이저)
      - uses: actions/setup-python@v6  # Python 설치 (최신 메이저, Node 24 기반)
        with:
          python-version: "3.13"
      - name: Install pytest
        run: pip install pytest        # 유일한 의존성
      - name: Run tests
        run: pytest                    # test_*.py의 test_* 함수 자동 수집·실행
```

버전 확인 요령: 공식 문서 예시는 최신 릴리스보다 늦게 갱신되는 경우가 있다 (2026-07 현재 GitHub docs 예시는 checkout@v6/setup-python@v5, 실제 최신 메이저는 v7/v6). If 액션 버전이 궁금하면 → 해당 액션 저장소의 README와 Releases 페이지를 기준으로 판단한다.

## 단계 4 (선택): Claude Code로 AI 코드 리뷰 추가

공식 액션 `anthropics/claude-code-action@v1`을 쓰면 PR/이슈 코멘트에서 `@claude`를 멘션해 리뷰·수정을 요청할 수 있다.

### 준비: 인증 시크릿 (둘 중 하나)


| 방식                | 시크릿 이름                    | 발급 방법                            |
| ----------------- | ------------------------- | -------------------------------- |
| Claude API 직접 사용  | `ANTHROPIC_API_KEY`       | console.anthropic.com에서 API 키 발급 |
| Claude Pro/Max 구독 | `CLAUDE_CODE_OAUTH_TOKEN` | 로컬 터미널에서 `claude setup-token` 실행 |


시크릿 등록:

```bash
gh secret set ANTHROPIC_API_KEY
# 또는
gh secret set CLAUDE_CODE_OAUTH_TOKEN
```

### 가장 쉬운 설치법

Claude Code 터미널에서 아래를 실행하면 GitHub **ㅠ**App 설치, 워크플로 파일 추가, 시크릿 등록을 대화식으로 안내한다 (저장소 admin 권한 필요).

```
/install-github-app
```

### 수동 설치: 최소 워크플로

`.github/workflows/claude.yml`로 저장한다.

```yaml
name: Claude Code

on:
  issue_comment:
    types: [created]
  pull_request_review_comment:
    types: [created]

jobs:
  claude:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
      issues: write
    steps:
      - uses: anthropics/claude-code-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          # Pro/Max 구독이면 위 줄 대신:
          # claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
```

동작 방식: `prompt` 입력을 생략하면 PR/이슈 코멘트의 `@claude` 멘션에 반응하는 인터랙티브 모드, `prompt`를 주면 즉시 실행되는 자동화 모드로 자동 감지된다. 사용해 보려면 PR을 하나 열고 코멘트로 `@claude 이 변경을 리뷰해줘`를 남긴다.

참고: 구 `@beta` 버전과 입력이 다르다 (`mode`/`direct_prompt` → `prompt` 통합, `model`/`max_turns` → `claude_args` CLI 인자). v1 문서 기준으로 작성해야 한다.

## 무료 티어 한도 (2026-07 기준, GitHub 공식 billing 문서)


| 구분                    | 한도                                                                          |
| --------------------- | --------------------------------------------------------------------------- |
| Public 저장소            | 표준 GitHub-hosted 러너 **과금 무료** (분 quota 미적용. 단 작업당 6시간 등 사용 제한은 별도 존재)       |
| Private 저장소 (Free 플랜) | 월 **2,000분** + 아티팩트 스토리지 **500MB** (캐시는 별도 10GB)                            |
| 기본 지출 한도              | **$0** — 무료 한도 초과 시 과금되는 대신 워크플로가 중단된다. 실수로 요금이 나갈 위험이 기본값에서는 없다            |
| 분 배수                  | Linux 1배, Windows 2배, macOS 약 10배. private에서는 `ubuntu-latest`가 가장 오래 쓸 수 있다 |
| 초과분 단가 (참고)           | 2026-01-01부로 인하: Linux 2코어 $0.006/분, Windows $0.010/분, macOS $0.062/분       |


결정 기준: If 학습용 실습이면 → public 저장소로 만든다 (분 소모 0). If private이 필요하면 → 월 2,000분 안에서 Linux 러너만 쓴다. 이 실습의 워크플로는 1회 실행에 약 1분이 걸린다.

## 체크포인트

- `python3 test_app.py` 로컬 통과
- `hands-on/` 폴더 자체에서 `git init` (상위 폴더 아님)
- 푸시 후 Actions 탭에서 초록불 확인
- 일부러 깨뜨려 빨간불 확인 후 원복
- (선택) `@claude` 멘션으로 AI 리뷰 응답 확인

## 확장 실습 기록 (2026-07-08)

기본 실습(테스트만) 위에 얹은 것들. 커밋 히스토리에 green→red→green으로 남아 있다.

### 실습에서 실제로 걸린 함정: 브랜치 이름 불일치
- `gh repo create`가 기본 브랜치를 `master`로 만들었는데 워크플로는 `branches: [main]`만 트리거 → **CI가 조용히 안 도는** 상태(초록불도 빨간불도 안 뜸).
- 해결: `git branch -M main` + `gh repo edit --default-branch main` + 원격 master 삭제.
- **교훈: 워크플로 트리거 브랜치와 실제 기본 브랜치 이름이 반드시 일치해야 한다.**

### 품질 게이트 추가 (lint + format + coverage)
파이프라인 단계: `checkout → setup-python → install deps → [ruff] → [black] → [pytest+coverage]`
- `ruff check .` = lint(코드 스멜), `black --check .` = 포맷 검사, `pytest --cov=app --cov-fail-under=100` = 커버리지 임계값.
- **하나라도 실패하면 잡 전체가 빨간불** = 게이트.

**핵심 시연: 테스트 통과 ≠ 품질 게이트 통과.**
테스트 안 붙인 `shout` 함수를 추가했더니 → `3 passed`(테스트는 통과)인데 `Coverage failure: 88 < 100`으로 **게이트가 차단**. 테스트만 봤다면 초록불로 새 코드가 몰래 들어왔을 것. 해결 = 되돌리기가 아니라 **테스트를 붙이는 것**(게이트가 원하는 대로) → 100% 회복.

### requirements-dev.txt = "설치 선언서"이지 "검사"가 아니다
- `requirements-dev.txt` = 필요한 도구 **목록(선언)**. 그 자체는 아무것도 검사 안 함.
- `pip install -r requirements-dev.txt` = CI 러너(매번 깨끗한 빈 우분투)에 그 목록대로 **환경 준비(설치)**.
- 실제 **검사**는 그 다음 `ruff`/`black`/`pytest` 단계가 한다. 순서 = **준비(설치) → 검사**.
- 두 종류: `requirements.txt`(앱 런타임 의존성, 프로덕션 포함) vs `requirements-dev.txt`(개발·CI 도구, 프로덕션 제외).

### 재현성(reproducibility) — 버전 고정
- 지금 목록은 버전 미고정(`ruff`만) → 최신 설치. **오늘 통과한 CI가 내일 도구 새 버전 때문에 갑자기 깨질 수 있다.**
- 실무: `ruff==0.x.y`처럼 **버전을 못박아(pin)** "매번 정확히 같은 도구" 보장 = lockfile의 존재 이유.

### 장난감이 숨긴 실전 복잡도 (CI가 쉬워 보이는 이유)
개념(커밋마다 자동 테스트)은 쉽고, 어려운 건 **규모에서 빠르게·안정적으로·신뢰성 있게 유지**하기다.
- 테스트 수천~수만 개 → "수 분 내 피드백"이 엔지니어링 문제(분할·병렬·shard·영향받은 것만).
- **플레이키 테스트**(랜덤 실패)로 CI 신뢰 붕괴.
- 캐싱·lockfile·매트릭스 빌드(OS×언어버전)·아티팩트 1회 빌드·service container 통합 테스트·보안 스캔·브랜치 보호.

### 브랜치 보호 + PR 플로우 (CI 초록불을 머지 조건으로 강제)

**목적**: "trunk는 항상 green"을 말이 아니라 **규칙**으로 박는다. CI가 빨간불이면 admin조차 main에 머지 불가.

**적용 방법 (`gh` = GitHub 설정, CI 파일은 안 건드림):**
```bash
cat > /tmp/protection.json <<'JSON'
{
  "required_status_checks": { "strict": true, "contexts": ["test"] },
  "enforce_admins": true,
  "required_pull_request_reviews": { "required_approving_review_count": 0 },
  "restrictions": null
}
JSON
gh api -X PUT repos/<owner>/<repo>/branches/main/protection --input /tmp/protection.json
# 조회: gh api repos/<owner>/<repo>/branches/main/protection
# 해제: gh api -X DELETE repos/<owner>/<repo>/branches/main/protection
```

| 필드 | 뜻 |
|---|---|
| `required_status_checks.contexts: ["test"]` | 통과해야 할 체크 이름(= ci.yml의 잡 이름 `test`) |
| `required_status_checks.strict: true` | 브랜치가 main 최신 상태여야 머지 가능 |
| `enforce_admins: true` | admin도 예외 없음(진짜 차단) |
| `required_pull_request_reviews.required_approving_review_count: 0` | PR은 필수, 승인은 0개(혼자라 데드락 방지) |

**PR 플로우 시연 (green→red→green):**
```bash
git checkout -b feature/multiply
# multiply 함수 추가 + 테스트에 버그(==5) 심기
git push -u origin feature/multiply
gh pr create --base main --head feature/multiply --title "..." --body "..."
```
- CI 빨간불 → PR `state: BLOCKED`, `gh pr merge` 시 "base branch policy prohibits the merge".
- 테스트 버그 수정(==6) 푸시 → CI 초록불 → `state: CLEAN` → `gh pr merge <n> --squash --delete-branch`.

**핵심 구분: CI ≠ 브랜치 보호**
- **CI**(`.github/workflows/ci.yml`, 저장소 안 코드) = *무엇을* 검사하나. git으로 clone하면 따라옴.
- **브랜치 보호**(GitHub 저장소 설정, 파일 아님) = 검사 결과를 *머지 조건으로 강제*하나. **git 히스토리에 없어 clone/fork해도 안 따라옴** → 새 저장소마다 다시 설정(또는 조직 ruleset·IaC로 코드화).
- 둘을 잇는 끈 = 체크 이름 `test` 하나.

**요금 주의**: 브랜치 보호(및 rulesets)는 **public 저장소는 무료**지만 **private + 무료 플랜은 불가**(Pro/Team/Enterprise 필요). 이 실습이 된 건 저장소를 public으로 만들어서다.

**정리 실무**: 머지 후 로컬·원격 feature 브랜치 삭제(`git branch -d`, `git push origin --delete`, `git fetch --prune`). `gh pr merge --delete-branch`가 원격을 못 지우는 경우가 있어 확인 필요.

