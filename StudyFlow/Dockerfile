FROM python:3.9-slim

# Install Tesseract OCR FIRST
RUN apt-get update && \
    apt-get install -y tesseract-ocr && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy requirements and install them
COPY StudyFlow/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Print version to confirm it's installed
RUN /usr/bin/tesseract --version

# Copy the rest of your code
COPY . /app

# Expose the backend port
EXPOSE 8000

# Set environment variable for Tesseract
ENV TESSERACT_PATH=/usr/bin/tesseract

# Run the backend server
CMD ["python", "-m", "StudyFlow.backend.app"]
