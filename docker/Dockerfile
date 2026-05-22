FROM python:3.11-slim

# Metadata
LABEL maintainer="AI Sprint Assistant"
LABEL description="Trợ lý quản lý Sprint với Google Chat"

# Cài đặt system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Thiết lập timezone Việt Nam
ENV TZ=Asia/Ho_Chi_Minh
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Working directory
WORKDIR /app

# Copy requirements và cài đặt dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Tạo thư mục cần thiết
RUN mkdir -p logs data credentials

# Expose webhook server port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Chạy bot
CMD ["python", "main.py"]
