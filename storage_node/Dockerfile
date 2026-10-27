# One image, run five times with different NODE_ID / volume / port (see docker-compose.yml).
# Build context is the repository root so the shared blockchain module can be copied in.
FROM python:3.12-slim
WORKDIR /app
COPY storage_node/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY shared /app/shared
COPY storage_node /app/storage_node
ENV NODE_DATA_DIR=/data PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "storage_node.node_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
