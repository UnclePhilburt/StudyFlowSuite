FROM python:3.9-slim

# Install Tesseract OCR
RUN apt-get update && \
    apt-get install -y tesseract-ocr && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ✅ Confirm it's installed (should show up in Render logs)
RUN /usr/bin/tesseract --version

# Set the working directory
WORKDIR /app

# Copy requirements and install Python packages
COPY StudyFlow/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ✅ Copy entire app code to /app (not /app/StudyFlow)
COPY . /app

# Let pytesseract know where to find Tesseract
ENV TESSERACT_PATH=/usr/bin/tesseract

# Expose port (optional)
EXPOSE 8000

# Start the app
CMD ["python", "-m", "StudyFlow.backend.app"]
