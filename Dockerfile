FROM python:3.9-slim

# Install Tesseract OCR and its dependencies
RUN apt-get update && \
    apt-get install -y tesseract-ocr && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Debug: Find where the tesseract binary is installed
RUN echo "Finding tesseract binary:" && find / -type f -name tesseract 2>/dev/null

# Force a symlink: if tesseract is in /usr/local/bin, link it to /usr/bin/tesseract
RUN if [ -f /usr/local/bin/tesseract ]; then ln -sf /usr/local/bin/tesseract /usr/bin/tesseract; fi

WORKDIR /app

# Copy only backend requirements to leverage cache
COPY StudyFlow/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the full project
COPY . /app

# Set environment variable for pytesseract to use
ENV TESSERACT_PATH=/usr/bin/tesseract

EXPOSE 8000

CMD ["python", "-m", "StudyFlow.backend.app"]
