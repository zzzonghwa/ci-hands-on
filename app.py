"""CI 실습용 최소 예제. 외부 의존성 없는 순수 함수 3개."""

# itertools.batched는 Python 3.12+ 전용이라, 3.11도 지원하려고 islice로 직접 구현한다.
from itertools import islice


def _batched(iterable, size):
    """iterable을 size 크기 튜플들로 끊어 내보낸다 (전 버전 호환)."""
    it = iter(iterable)
    while group := tuple(islice(it, size)):
        yield group


def chunk(items, size):
    """리스트를 size 크기 조각들로 나눈다. 예: chunk([1,2,3,4,5], 2) -> [[1,2],[3,4],[5]]"""
    return [list(b) for b in _batched(items, size)]


def add(a, b):
    """두 수의 합을 반환한다."""
    return a + b


def is_even(n):
    """n이 짝수면 True, 홀수면 False를 반환한다."""
    return n % 2 == 0


def slugify(text):
    """문자열을 소문자로 바꾸고 공백을 하이픈 1개로 치환한다."""
    return "-".join(text.lower().split())


def shout(text):
    """문자열을 대문자로 바꾸고 느낌표를 붙인다. (일부러 테스트를 안 붙임)"""
    return text.upper() + "!"


def multiply(a, b):
    """두 수의 곱을 반환한다."""
    return a * b
