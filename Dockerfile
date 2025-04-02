# Use slim Python image
FROM python:3.9-slim

# Install Tesseract OCR
RUN apt-get update && \
    apt-get install -y tesseract-ocr && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# ✅ Print where Tesseract is actually installed
RUN echo "🧠 Tesseract is installed at:" && which tesseract

# Set working directory
WORKDIR /app

# Copy only backend requirements first
COPY StudyFlow/backend/requirements.txt /app/requirements.txt

# ✅ FIXED: this was missing /app/
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy full app
COPY . /app

# Set ENV path — we’ll change this later once we confirm actual path
ENV TESSERACT_PATH=/usr/bin/tesseract

EXPOSE 8000

CMD ["python", "-m", "StudyFlow.backend.app"]
