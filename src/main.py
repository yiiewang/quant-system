#!/usr/bin/env python3
"""
MACD 量化交易系统 - 主入口

使用方式:
    python -m src.main run --config data/strategies/aaa.yaml
    python -m src.main backtest --start 2024-01-01 --end 2024-12-31
    python -m src.main data sync --symbols 000001.SZ,000002.SZ
"""

# 加载 .env 环境变量（必须在最开始加载）
from dotenv import load_dotenv
_ = load_dotenv()  # 返回值表示是否找到 .env 文件，此处有意忽略

from src.cli.main import cli

if __name__ == "__main__":
    cli()
