"""
Runner 模块
负责策略的不同运行模式: 分析(analyze)、监控(monitor)、回测(backtest)、交易(run)

Runner 是框架层的执行器，职责:
1. 从 Config (静态) + RunParams (动态) 组装执行环境
2. 通过 StrategyRegistry 创建策略实例
3. 初始化数据服务、通知服务等框架组件
4. 驱动策略执行并输出结果
"""
from .application import ApplicationRunner

__all__ = [
    'ApplicationRunner',
]
