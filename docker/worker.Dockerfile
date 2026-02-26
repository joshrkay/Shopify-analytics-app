FROM python:3.11-slim

WORKDIR /app

# Copy the dbt analytics project so dbt can find models and profiles at /analytics.
# BackfillService and dbt_runner both resolve the analytics dir as
# Path(__file__).parent^4 / "analytics" which maps to /analytics in this container.
COPY analytics /analytics
RUN cp /analytics/profiles.yml.example /analytics/profiles.yml

COPY backend /app
RUN pip install -r requirements.txt dbt-postgres

CMD ["python", "-m", "src.workers.sync_executor"]