# Use the full Python 3.9 image (Debian-based) instead of slim
FROM python:3.9

# Install Tesseract OCR and its dependencies
RUN apt-get update && \
    apt-get install -y tesseract-ocr && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Debug: Find all Tesseract binaries and print their paths
RUN echo "🔍 Tesseract binaries found:" && find / -type f -name tesseract 2>/dev/null

# Safety: Force a symlink at /usr/bin/tesseract (if not already there)
RUN ln -sf $(find / -type f -name tesseract | head -n 1) /usr/bin/tesseract

WORKDIR /app

# Copy backend requirements and install them
COPY StudyFlow/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the full project
COPY . /app

# Set environment variable so pytesseract can find the binary
ENV TESSERACT_PATH=/usr/bin/tesseract

EXPOSE 8000

CMD ["python", "-m", "StudyFlow.backend.app"]
