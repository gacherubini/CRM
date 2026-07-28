FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY pytest.ini .
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 9010 --proxy-headers --forwarded-allow-ips=*"]
