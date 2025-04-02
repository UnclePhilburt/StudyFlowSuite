FROM python:3.9-slim

# Install Tesseract OCR
RUN apt-get update && \
    apt-get install -y tesseract-ocr && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Show Tesseract version (will print in build logs)
RUN /usr/bin/tesseract --version

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY StudyFlow/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy rest of the code
COPY . /app

# Set Tesseract path
ENV TESSERACT_PATH=/usr/bin/tesseract

# Expose port for the backend
EXPOSE 8000

# Run your backend
CMD ["python", "-m", "StudyFlow.backend.app"]
