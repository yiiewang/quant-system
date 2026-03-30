"""
日期工具函数
"""
from datetime import datetime, timedelta
from typing import Optional, Tuple


def calculate_date_range(
    days: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    date_format: str = "%Y-%m-%d"
) -> Tuple[str, str]:
    """
    计算日期范围

    如果未提供 start_date 或 end_date，则根据 days 参数自动计算。
    - end_date 默认为当前日期
    - start_date 默认为 end_date 往前推 days 天

    Args:
        days: 历史数据天数
        start_date: 开始日期字符串（可选）
        end_date: 结束日期字符串（可选）
        date_format: 日期格式（默认 YYYY-MM-DD）

    Returns:
        Tuple[str, str]: (start_date, end_date) 格式化后的日期字符串

    Example:
        >>> calculate_date_range(days=30)
        ('2026-03-01', '2026-03-31')
        >>> calculate_date_range(days=30, start_date='2024-01-01')
        ('2024-01-01', '2026-03-31')
        >>> calculate_date_range(days=30, end_date='2024-12-31')
        ('2024-12-01', '2024-12-31')
    """
    # 计算结束日期
    if end_date:
        end_dt = datetime.strptime(end_date, date_format)
    else:
        end_dt = datetime.now()
        end_date = end_dt.strftime(date_format)

    # 计算开始日期
    if start_date:
        start_dt = datetime.strptime(start_date, date_format)
        start_date = start_dt.strftime(date_format)
    else:
        start_dt = end_dt - timedelta(days=days)
        start_date = start_dt.strftime(date_format)

    return start_date, end_date


__all__ = ["calculate_date_range"]
