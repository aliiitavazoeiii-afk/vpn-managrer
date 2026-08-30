FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates gzip coreutils && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY packed ./packed
COPY patches/v3.py ./patches/v3.py
COPY patches/v3.css ./patches/v3.css
COPY patches/date_edit.py ./patches/date_edit.py
COPY patches/user_manage.py ./patches/user_manage.py
COPY patches/phone_edit.py ./patches/phone_edit.py
COPY patches/followup.py ./patches/followup.py
COPY patches/followup_phone.py ./patches/followup_phone.py
COPY patches/group_pay.py ./patches/group_pay.py
COPY patches/payment_undo.py ./patches/payment_undo.py
COPY patches/followup.css ./patches/followup.css
COPY app/static/app.js ./app/static/app.js
COPY seed ./seed
RUN mkdir -p app/static \
 && cat packed/main.* | base64 -d | gzip -d > app/main.py \
 && cat packed/css.* | base64 -d | gzip -d > app/static/app.css \
 && touch app/__init__.py \
 && printf '\n# Ensure SessionMiddleware wraps auth middleware.\napp.user_middleware.sort(key=lambda m: 0 if m.cls is SessionMiddleware else 1)\n' >> app/main.py \
 && cat patches/v3.py >> app/main.py \
 && cat patches/date_edit.py >> app/main.py \
 && cat patches/user_manage.py >> app/main.py \
 && cat patches/phone_edit.py >> app/main.py \
 && cat patches/followup.py >> app/main.py \
 && cat patches/followup_phone.py >> app/main.py \
 && cat patches/group_pay.py >> app/main.py \
 && cat patches/payment_undo.py >> app/main.py \
 && cat patches/v3.css >> app/static/app.css \
 && cat patches/followup.css >> app/static/app.css \
 && python -m py_compile app/main.py \
 && rm -rf packed patches
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--proxy-headers","--forwarded-allow-ips=*"]
