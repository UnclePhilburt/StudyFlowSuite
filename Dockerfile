FROM python:3.9

# Install Tesseract OCR and its dependencies
RUN apt-get update && \
    apt-get install -y tesseract-ocr && \
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

# Default command for local testing.
# This command will be overridden by Render's startCommand.
CMD ["gunicorn", "StudyFlow.backend.app:app", "-k", "gevent", "--bind", "0.0.0.0:10000", "--workers", "1"]
