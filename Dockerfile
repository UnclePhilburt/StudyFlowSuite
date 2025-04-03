FROM python:3.9-slim

# Install Tesseract OCR and its dependencies
RUN apt-get update && \
    apt-get install -y tesseract-ocr && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Debug: Find all instances of 'tesseract' in the container and print their paths
RUN echo "Finding Tesseract binary:" && find / -type f -name tesseract 2>/dev/null

# Create a symlink at /usr/bin/tesseract pointing to the found binary.
# This uses 'find' to get the first occurrence and then forces a symlink.
RUN ln -sf $(find / -type f -name tesseract | head -n 1) /usr/bin/tesseract

WORKDIR /app

# Copy backend requirements and install them
COPY StudyFlow/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the full project
COPY . /app

# Set the environment variable for pytesseract to use
ENV TESSERACT_PATH=/usr/bin/tesseract

EXPOSE 8000

CMD ["python", "-m", "StudyFlow.backend.app"]
