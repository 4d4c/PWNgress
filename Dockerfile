FROM python:3.11

WORKDIR /app

COPY src/ /app

VOLUME /app/logs
VOLUME /app/database

RUN pip install --no-cache-dir -r /app/requirements.txt

CMD ["python3", "-u", "PWNgress.py"]
