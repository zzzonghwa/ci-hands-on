"""mutmut run 출력에서 mutation score를 계산해 80% 미만이면 실패시키는 게이트.

사용: python mutation_gate.py mutmut.log
mutmut 3의 진행 표시줄 마지막 집계를 파싱한다:
🎉 killed / 🫥 no tests / ⏰ timeout / 🤔 suspicious / 🙁 survived / 🔇 skipped
score = killed / (전체 - skipped). 커버리지 100%와 달리 "테스트가 버그를 실제로 잡는가"를 잰다.
"""

import re
import sys

THRESHOLD = 80.0

log = open(sys.argv[1], encoding="utf-8").read()
counts = re.findall(
    r"🎉 (\d+).*?🫥 (\d+).*?⏰ (\d+).*?🤔 (\d+).*?🙁 (\d+).*?🔇 (\d+)", log
)
if not counts:
    sys.exit("mutmut 집계 라인을 찾지 못함 — 출력 형식을 확인하라")

killed, no_tests, timeout, suspicious, survived, skipped = map(int, counts[-1])
denom = killed + no_tests + timeout + suspicious + survived  # skip만 분모 제외
score = 100.0 * killed / denom if denom else 0.0
print(f"mutation score: {score:.1f}% (killed {killed} / {denom})")
if score < THRESHOLD:
    sys.exit(f"게이트 실패: score {score:.1f}% < {THRESHOLD}%")
print("게이트 통과")
