"""pytest 스타일 테스트.

- CI에서는 `pytest`가 test_ 접두사 함수를 자동 수집해 실행한다.
- 로컬에서는 pytest 없이 `python3 test_app.py`로도 실행된다 (__main__ 블록).
"""

from app import add, is_even, slugify


def test_add():
    assert add(2, 3) == 5
    assert add(-1, 1) == 0


def test_is_even():
    assert is_even(4) is True
    assert is_even(7) is False


def test_slugify():
    assert slugify("Hello World") == "hello-world"
    assert slugify("  GitHub   Actions  ") == "github-actions"


if __name__ == "__main__":
    test_add()
    test_is_even()
    test_slugify()
    print("OK: 3개 테스트 모두 통과")
