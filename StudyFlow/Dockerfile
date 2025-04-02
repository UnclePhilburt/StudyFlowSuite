# Use a Python base image with apt-get support
FROM python:3.9-slim

# Install system dependencies including Tesseract
RUN apt-get update && \
    apt-get install -y tesseract-ocr && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Show tesseract version (you should see this in build logs)
RUN /usr/bin/tesseract --version

# Set working directory
WORKDIR /app

# Copy only requirements first to leverage Docker cache
COPY StudyFlow/backend/requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project
COPY . /app

# Set environment variable for tesseract
ENV TESSERACT_PATH=/usr/bin/tesseract

# Expose port
EXPOSE 8000

# Start the backend service
CMD ["python", "-m", "StudyFlow.backend.app"]
