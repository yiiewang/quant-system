# 量化交易系统 Docker 镜像
# 构建: docker build -t quant-system .
# 运行: docker run -p 8000:8000 quant-system

FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY src/ ./src/
COPY config/ ./config/
COPY data/ ./data/
COPY docs/ ./docs/
COPY examples/ ./examples/
COPY scripts/ ./scripts/
COPY *.md ./
COPY *.py ./

# 创建数据目录和日志目录
RUN mkdir -p data logs output

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/api/health')" || exit 1

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["python", "-m", "src.cli.main", "serve", "--host", "0.0.0.0", "--port", "8000"]
