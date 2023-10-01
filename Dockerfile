FROM python:3.11-alpine

WORKDIR /app/src

COPY src/ /app/src

VOLUME /app/logs
VOLUME /app/database
VOLUME /app/images

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python3", "-u", "PWNgress.py"]