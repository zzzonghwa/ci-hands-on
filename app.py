"""CI 실습용 최소 예제. 외부 의존성 없는 순수 함수 3개."""


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
