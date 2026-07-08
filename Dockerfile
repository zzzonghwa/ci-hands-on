# 최소 런타임 이미지. 앱 코드만 담아 main.py를 실행한다.
# slim = 데비안 최소 이미지(용량 작음). 런타임 의존성이 없어 pip install도 없다.
FROM python:3.13-slim

WORKDIR /app
COPY app.py main.py ./

# 컨테이너가 뜨면 이 명령을 실행한다.
ENTRYPOINT ["python", "main.py"]
