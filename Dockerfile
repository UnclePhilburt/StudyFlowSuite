# Use a Debian image with Python pre-installed
FROM python:3.9

# Install Tesseract OCR and dependencies
RUN apt-get update && \
    apt-get install -y tesseract-ocr && \
    echo "🔍 Checking tesseract location:" && \
    which tesseract && \
    tesseract --version && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set workdir
WORKDIR /app

# Install Python dependencies
COPY StudyFlow/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the rest of the app
COPY . /app

# Set env var so pytesseract knows where to look
ENV TESSERACT_PATH=/usr/bin/tesseract

EXPOSE 8000

CMD ["python", "-m", "StudyFlow.backend.app"]
