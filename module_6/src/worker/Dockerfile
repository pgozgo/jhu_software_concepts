FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app
COPY src/worker/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
COPY --chown=app:app src/worker /app/src/worker
COPY --chown=app:app src/db /app/src/db
COPY --chown=app:app src/task_queue.py /app/src/task_queue.py
USER app

CMD ["python", "-m", "worker.consumer"]
