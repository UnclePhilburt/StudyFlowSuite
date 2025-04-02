# Use slim Python image
FROM python:3.9-slim

# Install system dependencies including Tesseract OCR
RUN apt-get update && \
    apt-get install -y tesseract-ocr && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# ✅ Print Tesseract path and version for debug
RUN echo "📌 Tesseract path is: $(which tesseract)" && \
    tesseract --version

# 🛟 Force symlink to /usr/bin/tesseract (in case it's somewhere else)
RUN ln -sf $(which tesseract) /usr/bin/tesseract

# Set working directory
WORKDIR /app

# Copy only backend requirements first to leverage caching
COPY StudyFlow/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the full project
COPY . /app

# Set environment variable for pytesseract to use
ENV TESSERACT_PATH=/usr/bin/tesseract

# Expose backend port
EXPOSE 8000

# Start the backend service
CMD ["python", "-m", "StudyFlow.backend.app"]
