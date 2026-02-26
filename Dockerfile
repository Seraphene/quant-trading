# Use a Debian-based slim image for faster builds with binary wheels
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=UTC

# Set the working directory in the container
WORKDIR /app

# Install minimal build dependencies (only if absolutely needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
# Using a Debian-based image allows us to use pre-built binary wheels
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Create necessary directories
RUN mkdir -p data logs models

# Default command: Scan Gold (SGOL) on 1d and 4h timeframes with ML filter
CMD ["python", "scanner.py", "--symbols", "SGOL", "--timeframe", "1d", "4h", "--use-ml", "--loop"]
