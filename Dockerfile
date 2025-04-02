# Use a Python base image with apt support
FROM python:3.9-slim

# Install Tesseract OCR and dependencies
RUN apt-get update && \
    apt-get install -y tesseract-ocr && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Confirm tesseract is there (this shows up in build logs)
RUN /usr/bin/tesseract --version

# Set the working directory
WORKDIR /app

# Copy requirements and install them
COPY StudyFlow/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . /app

# Set the TESSERACT_PATH environment variable
ENV TESSERACT_PATH=/usr/bin/tesseract

# Expose the Flask port
EXPOSE 8000

# Start the backend server
CMD ["python", "-m", "StudyFlow.backend.app"]
