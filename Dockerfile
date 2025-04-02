FROM python:3.9-slim

# Install Tesseract and other system tools
RUN apt-get update && \
    apt-get install -y tesseract-ocr && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 👇 Print path AND version to confirm installation
RUN echo "🧠 Tesseract is at:" && which tesseract && tesseract --version

WORKDIR /app

COPY StudyFlow/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

# 🚨 TEMPORARILY remove this until we confirm the correct path!
# ENV TESSERACT_PATH=/usr/bin/tesseract

EXPOSE 8000

CMD ["python", "-m", "StudyFlow.backend.app"]
