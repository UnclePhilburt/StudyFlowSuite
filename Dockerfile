FROM python:3.9-slim

# Install Tesseract OCR and its development libraries (for extra compatibility)
RUN apt-get update && \
    apt-get install -y tesseract-ocr libtesseract-dev libleptonica-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# For debugging: search the entire container for the tesseract binary and print its path
RUN find / -type f -name tesseract

# Create a symlink to the tesseract binary at /usr/bin/tesseract.
# This takes the first result of the find command.
RUN ln -sf $(find / -type f -name tesseract | head -n 1) /usr/bin/tesseract

WORKDIR /app

# Copy backend requirements and install them
COPY StudyFlow/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the full project
COPY . /app

# Set environment variable for pytesseract
ENV TESSERACT_PATH=/usr/bin/tesseract

EXPOSE 8000

CMD ["python", "-m", "StudyFlow.backend.app"]
