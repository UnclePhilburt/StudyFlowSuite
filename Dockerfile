FROM python:3.9

# Install Tesseract OCR and its dependencies
RUN apt-get update && \
    apt-get install -y tesseract-ocr sqlite3 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN echo "🔍 Tesseract binaries found:" && find / -type f -name tesseract 2>/dev/null || true

RUN TESS_BIN=$(find / -type f -name tesseract | head -n 1) && \
    ln -sf "$TESS_BIN" /usr/bin/tesseract || true

WORKDIR /app

COPY StudyFlow/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

ENV TESSERACT_PATH=/usr/bin/tesseract
ENV PYTHONPATH=/app

# Use a conditional CMD:
# - If ROLE is "worker", run the Celery worker.
# - If ROLE is "flower", run Flower.
# - Otherwise (or if ROLE is not set), run the web server.
CMD if [ "$ROLE" = "worker" ]; then \
      celery --app StudyFlow.backend.tasks worker --loglevel info --concurrency 4; \
    elif [ "$ROLE" = "flower" ]; then \
      celery flower --app StudyFlow.backend.tasks --loglevel info; \
    else \
      gunicorn StudyFlow.backend.app:app -k gevent --bind 0.0.0.0:10000 --workers 1; \
    fi
