FROM python:3.11-slim

WORKDIR /app

# OpenCV headless 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p uploads

# Railway/Render는 PORT 환경변수를 주입함
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
