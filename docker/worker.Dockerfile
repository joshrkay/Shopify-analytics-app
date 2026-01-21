FROM python:3.11-slim

WORKDIR /app
COPY backend /app
RUN pip install -r requirements.txt

CMD ["python", "-m", "jobs.worker"]