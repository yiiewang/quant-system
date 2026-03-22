"""
日志配置模块
实现系统日志和策略日志的分离输出

支持的日志分类：
- 系统日志：logs/system.log.YYYYMMDD - 所有非策略日志（启动、配置、引擎、数据等）
- 策略日志：logs/{策略名称}.log.YYYYMMDD - 策略相关的日志（策略加载、信号生成等）
"""
import os
import logging
from pathlib import Path
from typing import Optional, Dict
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime


# 日志级别映射
LOG_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}


# 日志格式
DETAILED_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
CONSOLE_FORMAT = '%(levelname)s - %(message)s'


class LogConfig:
    """日志配置"""

    def __init__(
        self,
        log_dir: str = 'logs',
        level: str = 'INFO',
        console_output: bool = True,
        backup_count: int = 30
    ):
        """
        初始化日志配置

        Args:
            log_dir: 日志目录
            level: 日志级别
            console_output: 是否输出到控制台
            backup_count: 保留的备份文件数量（天数）
        """
        self.log_dir = Path(log_dir)
        self.level = level
        self.console_output = console_output
        self.backup_count = backup_count

        # 创建日志目录
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def get_system_log_path(self, date: Optional[str] = None) -> Path:
        """
        获取系统日志文件路径

        Args:
            date: 日期字符串 YYYYMMDD，不指定则使用当前日期

        Returns:
            日志文件完整路径
        """
        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        return self.log_dir / f"system.log.{date}"

    def get_strategy_log_path(self, strategy_name: str, date: Optional[str] = None) -> Path:
        """
        获取策略日志文件路径

        Args:
            strategy_name: 策略名称
            date: 日期字符串 YYYYMMDD，不指定则使用当前日期

        Returns:
            日志文件完整路径
        """
        if date is None:
            date = datetime.now().strftime('%Y%m%d')
        return self.log_dir / f"{strategy_name}.log.{date}"

    def create_file_handler(
        self,
        log_path: str,
        level: Optional[str] = None
    ) -> logging.Handler:
        """
        创建文件处理器

        Args:
            log_path: 日志文件路径（包含日期后缀），如 "logs/system.log.20260319"
            level: 日志级别

        Returns:
            文件处理器
        """
        from logging.handlers import RotatingFileHandler

        handler = RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        handler.setLevel(LOG_LEVELS.get(level or self.level, logging.INFO))
        handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
        return handler

    def create_console_handler(self, level: Optional[str] = None) -> logging.StreamHandler:
        """
        创建控制台处理器
        
        Args:
            level: 日志级别
            
        Returns:
            控制台处理器
        """
        handler = logging.StreamHandler()
        handler.setLevel(LOG_LEVELS.get(level or self.level, logging.INFO))
        # 控制台也用详细格式，方便调试
        handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
        return handler


def setup_logging(
    log_dir: str = 'logs',
    level: str = 'INFO',
    console_output: bool = True,
    backup_count: int = 30
) -> None:
    """
    设置日志系统，实现系统日志和策略日志的分离

    日志文件格式：
    - 系统日志：logs/system.log.YYYYMMDD
    - 策略日志：logs/{策略名称}.log.YYYYMMDD

    Args:
        log_dir: 日志目录
        level: 日志级别
        console_output: 是否输出到控制台
        backup_count: 保留的备份文件数量（天数）
    """
    config = LogConfig(log_dir, level, console_output, backup_count)

    # 清除所有已存在的处理器（避免重复添加）
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    # 设置根日志级别
    root_logger.setLevel(LOG_LEVELS.get(level, logging.INFO))

    # 添加控制台处理器
    if console_output:
        root_logger.addHandler(config.create_console_handler(level))

    # ===== 系统日志处理器 =====
    # 所有非策略日志都输出到系统日志
    system_handler = config.create_file_handler(
        str(config.get_system_log_path()),
        level
    )
    system_handler.addFilter(_is_system_log_filter)
    root_logger.addHandler(system_handler)

    # 记录日志系统启动
    logger = logging.getLogger('system')
    logger.info(f"日志系统已初始化 (level={level}, log_dir={log_dir})")
    logger.info(f"系统日志: logs/system.log.YYYYMMDD")
    logger.info(f"策略日志: logs/{{策略名称}}.log.YYYYMMDD")


def _is_strategy_log(record: logging.LogRecord) -> bool:
    """
    判断是否为策略相关的日志

    Args:
        record: 日志记录

    Returns:
        True 如果是策略日志
    """
    # 通过 logger 名称判断
    module_name = record.name
    return (
        module_name.startswith('src.strategy') or
        'strategy' in module_name.lower()
    )


def _is_system_log_filter(record: logging.LogRecord) -> bool:
    """
    系统日志过滤器 - 只让非策略日志通过

    Args:
        record: 日志记录

    Returns:
        True 如果是系统日志
    """
    return not _is_strategy_log(record)


def get_strategy_logger(strategy_name: str) -> logging.Logger:
    """
    获取策略专用日志记录器

    策略日志会单独输出到 logs/{strategy_name}.log.YYYYMMDD 文件

    Args:
        strategy_name: 策略名称

    Returns:
        日志记录器
    """
    logger = logging.getLogger(f'src.strategy.{strategy_name}')

    # 为策略 logger 添加专用的文件处理器
    # 只在第一次调用时添加（避免重复）
    if not logger.handlers:
        from src.config.base import load_config
        from src.config.schema import Config

        try:
            sys_config = load_config(Config)
            log_dir = sys_config.log.dir
            level = sys_config.log.level.value if hasattr(sys_config.log.level, 'value') else str(sys_config.log.level)
            backup_count = sys_config.log.backup_count
        except:
            # 配置加载失败时使用默认值
            log_dir = 'logs'
            level = 'INFO'
            backup_count = 30

        # 获取 console_output 设置（从 root logger 判断）
        root_logger = logging.getLogger()
        has_console = any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) 
                         for h in root_logger.handlers)
        
        config = LogConfig(log_dir, level, console_output=has_console, backup_count=backup_count)

        # 添加策略日志文件处理器
        strategy_handler = config.create_file_handler(
            str(config.get_strategy_log_path(strategy_name)),
            level
        )
        strategy_handler.addFilter(lambda record: record.name == f'src.strategy.{strategy_name}')
        logger.addHandler(strategy_handler)

        # 如果 root logger 有控制台处理器，策略日志也输出到控制台
        if has_console:
            console_handler = config.create_console_handler(level)
            console_handler.addFilter(lambda record: record.name == f'src.strategy.{strategy_name}')
            logger.addHandler(console_handler)

        logger.setLevel(LOG_LEVELS.get(level, logging.INFO))

        # 不传播到 root logger（避免重复输出）
        # 策略日志已经有自己的文件和控制台 handler
        logger.propagate = False

    return logger
