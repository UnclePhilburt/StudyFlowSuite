# Use an official Python runtime as a base image.
FROM python:3.9-slim

# Set the working directory in the container to /app
WORKDIR /app

# Copy the requirements file from the backend folder into the container.
COPY StudyFlow/backend/requirements.txt /app/requirements.txt

# Install the Python packages.
RUN pip install --no-cache-dir -r /app/requirements.txt

# Update the container and install Tesseract OCR.
RUN apt-get update && apt-get install -y tesseract-ocr && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy all the project files into the container.
COPY . /app

# Expose a port (if your app serves web traffic; adjust if needed).
EXPOSE 8000

# Set the Tesseract path as an environment variable.
ENV TESSERACT_PATH=/usr/bin/tesseract

# Command to run your application.
CMD ["python", "-m", "StudyFlow.main"]
