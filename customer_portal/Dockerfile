FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .
COPY v2.py .
COPY v2.css .
COPY v2_polish.css .
COPY login_v2.html .
COPY dashboard_v2.html .
COPY safari_required.html .
COPY billing_sync.py .
COPY billing_migration.py .
RUN printf '\nexec(compile(open("/srv/v2.py", "r", encoding="utf-8").read(), "/srv/v2.py", "exec"))\nexec(compile(open("/srv/billing_sync.py", "r", encoding="utf-8").read(), "/srv/billing_sync.py", "exec"))\n' >> server.py \
 && python -m py_compile server.py billing_migration.py
EXPOSE 8091
CMD ["uvicorn","server:app","--host","0.0.0.0","--port","8091","--proxy-headers","--forwarded-allow-ips=*"]
