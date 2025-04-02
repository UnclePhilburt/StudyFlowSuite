FROM python:3.9-slim

RUN apt-get update && \
    apt-get install -y tesseract-ocr && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN /usr/bin/tesseract --version

WORKDIR /app

# Copy the backend requirements
COPY StudyFlow/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the full app
COPY StudyFlow /app/StudyFlow

# Set env var so pytesseract knows where to find the binary
ENV TESSERACT_PATH=/usr/bin/tesseract

EXPOSE 8000

CMD ["python", "-m", "StudyFlow.backend.app"]
