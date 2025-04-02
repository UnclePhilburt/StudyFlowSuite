# Use slim Python image
FROM python:3.9-slim

# Install system dependencies including Tesseract OCR
RUN apt-get update && \
    apt-get install -y tesseract-ocr && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# ✅ Print Tesseract path to verify in logs
RUN echo "🧠 Tesseract is at: $(which tesseract)"

# Set working directory
WORKDIR /app

# Copy only backend requirements first to leverage caching
COPY StudyFlow/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the full project
COPY . /app

# ⛳ We'll update this if logs show a different path!
ENV TESSERACT_PATH=/usr/bin/tesseract

# Expose backend port
EXPOSE 8000

# Run the backend
CMD ["python", "-m", "StudyFlow.backend.app"]
