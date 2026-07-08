"""컨테이너 엔트리포인트. app의 함수들을 간단히 시연한다."""

from app import add, is_even, slugify, shout, multiply, chunk


def main():
    print("add(2, 3)              =", add(2, 3))
    print("is_even(4)             =", is_even(4))
    print("slugify('Hello World') =", slugify("Hello World"))
    print("shout('ci')            =", shout("ci"))
    print("multiply(6, 7)         =", multiply(6, 7))
    print("chunk([1,2,3,4,5], 2)  =", chunk([1, 2, 3, 4, 5], 2))


if __name__ == "__main__":
    main()
