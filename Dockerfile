FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# ภาพ mcr.microsoft.com/playwright/python:v1.40.0 มี playwright และ chromium ตรงเวอร์ชันติดตั้งไว้แล้ว
# ติดตั้งเฉพาะ library เสริมเพื่อไม่ให้เวอร์ชันชนกัน
RUN pip install --no-cache-dir playwright-stealth requests

COPY . .

EXPOSE 10000

CMD ["python", "app.py"]
