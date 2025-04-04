# Use the full Python 3.9 image (Debian-based) instead of slim
FROM python:3.9

# Install Tesseract OCR and its dependencies
RUN apt-get update && \
    apt-get install -y tesseract-ocr && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Debug: Find all Tesseract binaries and print their paths
RUN echo "🔍 Tesseract binaries found:" && find / -type f -name tesseract 2>/dev/null || true

# Safety: Force a symlink at /usr/bin/tesseract (in case it's elsewhere)
RUN TESS_BIN=$(find / -type f -name tesseract | head -n 1) && \
    ln -sf "$TESS_BIN" /usr/bin/tesseract || true

# Set the working directory
WORKDIR /app

# Copy backend requirements and install them
COPY StudyFlow/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the full project
COPY . /app

# Set environment variable so pytesseract can find the binary
ENV TESSERACT_PATH=/usr/bin/tesseract

# Set PYTHONPATH to the directory containing the StudyFlow package
ENV PYTHONPATH=/app

# Expose app port
EXPOSE 8000

# Run the app as a module
CMD ["python", "-m", "StudyFlow.backend.app"]
