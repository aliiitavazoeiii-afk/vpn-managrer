FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates gzip coreutils && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY packed ./packed
COPY app/static/app.js ./app/static/app.js
COPY seed ./seed
RUN mkdir -p app/static \
 && cat packed/main.* | base64 -d | gzip -d > app/main.py \
 && cat packed/css.* | base64 -d | gzip -d > app/static/app.css \
 && touch app/__init__.py \
 && python -m py_compile app/main.py \
 && rm -rf packed
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--proxy-headers","--forwarded-allow-ips=*"]
