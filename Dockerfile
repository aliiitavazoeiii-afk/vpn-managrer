FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates gzip coreutils && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY packed ./packed
COPY patches ./patches
COPY app/static/app.js ./app/static/app.js
COPY seed ./seed
RUN mkdir -p app/static \
 && cat packed/main.* | base64 -d | gzip -d > app/main.py \
 && cat packed/css.* | base64 -d | gzip -d > app/static/app.css \
 && touch app/__init__.py \
 && printf '\n# Ensure SessionMiddleware wraps auth middleware.\napp.user_middleware.sort(key=lambda m: 0 if m.cls is SessionMiddleware else 1)\n' >> app/main.py \
 && cat patches/v3.py >> app/main.py \
 && cat patches/v4.py >> app/main.py \
 && cat patches/v3.css >> app/static/app.css \
 && cat patches/v4.css >> app/static/app.css \
 && python -m py_compile app/main.py \
 && rm -rf packed patches
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--proxy-headers","--forwarded-allow-ips=*"]
