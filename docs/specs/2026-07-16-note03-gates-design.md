# 노트 03 게이트 실적용 설계 (ci-hands-on)

작성: 2026-07-16. 근거: `../../notes/03-ai-code-quality-gates.md`의 6계층 게이트와 도입 순서.

## 목표

노트 03의 6계층 게이트 전부 + provenance 검증을 ci-hands-on 저장소에 실제로 붙인다. 계층 5(AI 리뷰)·6(리스크 티어링 보조)는 claude-code-action 에이전트로 구현하고, 노트 02의 self-healing CI까지 포함한다.

동일 모델 자기검증 문제(원리 3): 코드 생성도 Claude, 리뷰도 Claude → 같은 모델 패밀리. 노트 03 If/Then대로 **결정론적 게이트(SAST·mutation)를 블로킹 조건으로 승격**하는 것으로 대응 — PR B·D가 그 역할. AI 리뷰는 1차 필터, 최종 차단은 결정론적 게이트가 담당한다.

## 진행 방식

계층 1개 = PR 1개. 각 PR은 3단계로 검증한다:

1. 게이트 추가 후 초록불 확인
2. 위반 커밋을 일부러 넣어 빨간불 확인
3. 위반 제거(복구) 후 초록불 → 머지

머지 후 hands-on/README.md에 실습 기록을 docs 커밋으로 남긴다 (기존 #2·#5·#7·#9 패턴).

## PR 목록 (노트 03 도입 순서)

### PR A — 계층 1: 시크릿 (1주차 항목)

- 저장소 설정: GitHub secret scanning + push protection 활성화 (`gh api`)
- CI: gitleaks 잡 추가 (`gitleaks/gitleaks-action`), `ci-success`의 needs에 편입
- 빨간불 시연: 가짜 AWS 액세스 키(`AKIA...` 패턴) 커밋 → gitleaks 실패 확인 → 제거
- 노트 근거: "pre-commit + push protection 이중화. 가장 저비용·고효과"



### PR B — 계층 3: SAST (2~3주차 항목)

- 별도 워크플로 `codeql.yml` (GitHub 권장 구조), PR 트리거
- 브랜치 보호 필수 체크에 CodeQL 분석 추가 (블로킹 승격)
- 빨간불 시연: `eval()` 기반 인젝션 코드 추가 → code scanning 체크 실패 → 제거



### PR C — 계층 2: 의존성 (4~6주차 항목)

- `actions/dependency-review-action` 잡 (PR diff의 신규/취약 의존성 차단)
- `pip-audit` 잡 (알려진 CVE 검사), `ci-success` needs 편입
- 빨간불 시연 2종: (a) 알려진 CVE 있는 옛 버전 패키지 추가, (b) 존재하지 않는 패키지명(slopsquatting 시뮬레이션) 추가 → 설치 실패
- 버린 것: 사설 레지스트리·평판 API — 개인 실습 규모 과잉



### PR D — 계층 4: mutation score (2개월+ 항목)

- mutmut을 CI 잡으로 추가, mutation score 80% 미만이면 실패 (동등 뮤턴트 여지를 두되 노트 03의 예시 임계값 60%보다 엄격하게 — 코드가 작으므로)
- 빨간불 시연: assert 없는 "실행만 하는 테스트"로 기존 assert를 약화 → 커버리지 100%는 통과하는데 mutation 게이트만 빨간불 (노트 03 원리 5 증명)



### PR E — provenance attestation (2개월+ 항목)

- docker-build 잡에 `actions/attest-build-provenance` 추가 (이미지 서명)
- deploy 잡에 `gh attestation verify` 단계 추가 — 검증 실패 시 배포 차단
- 빨간불 시연: attestation 없는 기존 이미지에 verify 실행 → 실패 확인



### PR F — 계층 5+6: AI 리뷰 에이전트 + 리스크 티어링

- `claude-review.yml`: PR이 열리면 claude-code-action이 자동 리뷰 코멘트 작성
- 리뷰 프롬프트에 리스크 티어링 포함: 인증·인가·인프라 권한 변경 = 티어 1(인간 리뷰 필수 표시), 문서·설정만 = 티어 3(자동 통과 가능 표시) — 노트 03 If/Then 그대로
- 인증: Claude 구독 OAuth 토큰(`claude setup-token` → 저장소 시크릿 `CLAUDE_CODE_OAUTH_TOKEN`)
- AI 리뷰는 논블로킹(1차 필터). 차단은 결정론적 게이트(B·D) 담당 — 원리 3 대응
- 시연: 티어 1 성격 변경(예: 권한 관련 코드)과 티어 3 변경(문서)을 각각 PR로 열어 티어 판정 차이 확인

### PR G — self-healing CI (노트 02)

- `claude-fix-ci.yml`: main이 아닌 브랜치에서 CI 실패 시 claude-code-action이 실패 로그를 읽고 수정 커밋을 같은 PR 브랜치에 푸시(또는 수정 제안 코멘트)
- 안전장치: main 직접 푸시 금지, 에이전트 커밋도 동일 게이트 전부 통과해야 머지 — 노트 02의 "에이전트 산출물도 파이프라인 거주" 원리
- 시연: 일부러 lint 오류 커밋 → CI 빨간불 → 에이전트가 수리 커밋 → 초록불



## 아키텍처 결정

- 기존 `ci.yml`의 집계 게이트(`ci-success`) 패턴 재사용: 새 잡은 needs에만 추가, 브랜치 보호 규칙은 CodeQL 외에는 변경 없음.
- 모든 도구는 public 저장소 무료 범위 (GitHub native + OSS 액션).
- 워크플로 주석은 기존 스타일(각 단계 "왜"를 한글로) 유지.



## 성공 기준

- PR A~E 각각에서 초록→빨강→초록 사이클을 Actions 실행 링크로 확인
- PR F: AI 리뷰 코멘트 + 티어 판정이 실제 PR에 달리는 것 확인
- PR G: 일부러 깨뜨린 CI를 에이전트가 수리해 초록불로 복구하는 것 확인
- 최종 파이프라인이 노트 03 6계층 전부 + provenance를 커버
- README에 계층↔노트 매핑 기록

