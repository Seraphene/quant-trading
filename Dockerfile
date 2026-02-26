# Stage 1: Builder
FROM python:3.11-alpine as builder

WORKDIR /app

# Install build dependencies for pandas/numpy
RUN apk add --no-cache \
    gcc \
    musl-dev \
    g++ \
    libffi-dev

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-alpine

WORKDIR /app
ENV TZ=UTC
ENV PATH=/root/.local/bin:$PATH

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
COPY . .

RUN mkdir -p data logs models

CMD ["python", "scanner.py", "--symbols", "SGOL", "--timeframe", "1d", "4h", "--use-ml", "--loop"]
