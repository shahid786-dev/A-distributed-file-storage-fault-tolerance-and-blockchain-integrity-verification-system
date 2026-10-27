# Coordinator backend. Build context is the repository root.
FROM python:3.12-slim
WORKDIR /app/backend
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY shared /app/shared
COPY backend /app/backend
ENV DB_PATH=/data/blockstore.db PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
