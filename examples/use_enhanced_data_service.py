#!/usr/bin/env python3
"""
增强版数据服务使用示例

展示如何从原始版本平滑升级到增强版本
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime, timedelta
import time

# 导入数据模块
from src.data import (
    # 原始版本（保持兼容）
    MarketDataService,
    DataSource,
    Frequency,
    
    # 增强版本（新功能）
    EnhancedMarketDataService,
    create_default_data_service,
    get_global_config,
)


def demo_original_usage():
    """原始版本使用演示"""
    print("=== 原始版本使用方式 ===")
    
    # 原始用法（完全兼容）
    service = MarketDataService(
        source=DataSource.TUSHARE,
        db_path="data/market.db",
        config={'tushare_token': os.environ.get('TUSHARE_TOKEN', '')}
    )
    
    try:
        # 获取最新数据
        end_date = datetime.now()
        start_date = end_date - timedelta(days=10)
        
        # 注意：这里实际运行会调用API，需要有有效的token
        # data = service.get_latest('000001.SZ')
        # print(f"获取到 {len(data)} 条数据")
        
        service.close()
        print("原始版本使用演示完成 ✓")
    except Exception as e:
        print(f"原始版本演示失败（需要配置API token）: {e}")


def demo_enhanced_usage():
    """增强版本使用演示"""
    print("\n=== 增强版本使用方式 ===")
    
    # 方式1：直接创建增强版
    enhanced_service = EnhancedMarketDataService(
        source=DataSource.TUSHARE,
        fallback_sources=[DataSource.AKSHARE, DataSource.BAOSTOCK],
        parallel_fetch=True,
        enable_health_monitor=True
    )
    
    # 方式2：通过工厂函数创建（推荐）
    service = create_default_data_service()
    
    # 新增功能演示
    print("1. 健康监控报告:")
    health_report = service.get_health_report()
    for source, info in health_report.items():
        print(f"  {source}: {info['status']} (可用: {info['available']})")
    
    print("\n2. 活跃数据源:")
    active_sources = service.get_active_sources()
    print(f"  活跃数据源: {active_sources}")
    
    print("\n3. 配置查看:")
    config = get_global_config()
    primary = config.get('data_sources.primary')
    fallbacks = config.get('data_sources.fallbacks', [])
    print(f"  主数据源: {primary}")
    print(f"  备选数据源: {fallbacks}")
    
    # 模拟多数据源降级场景
    print("\n4. 模拟降级场景:")
    print("  - 主数据源失败时自动切换到备选数据源")
    print("  - 并行请求时取最快返回的结果")
    print("  - 健康监控自动标记故障源并跳过")
    
    service.close()
    print("增强版本使用演示完成 ✓")


def demo_smooth_upgrade():
    """平滑升级演示"""
    print("\n=== 平滑升级演示 ===")
    
    # 在生产环境中，可以通过配置文件控制使用哪个版本
    
    # 方案A：完全替换（简单粗暴）
    # 将所有 MarketDataService() 调用替换为 create_default_data_service()
    
    # 方案B：条件切换（平滑过渡）
    use_enhanced = os.environ.get('USE_ENHANCED_DATA_SERVICE', 'false').lower() == 'true'
    
    if use_enhanced:
        print("启用增强版数据服务")
        service = create_default_data_service()
    else:
        print("使用原始版数据服务")
        service = MarketDataService(
            source=DataSource.LOCAL,
            db_path="data/market.db"
        )
    
    # 业务代码不需要修改
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=5)
        
        # 同样的调用接口
        # data = service.get_latest('000001.SZ')
        
        service.close()
        print("平滑升级演示完成 ✓")
    except Exception as e:
        print(f"演示失败: {e}")


def demo_config_management():
    """配置管理演示"""
    print("\n=== 配置管理演示 ===")
    
    # 加载配置
    config = get_global_config()
    
    print("当前配置:")
    print(f"  主数据源: {config.get('data_sources.primary')}")
    print(f"  备选数据源: {config.get('data_sources.fallbacks')}")
    print(f"  并行请求: {config.get('data_sources.parallel_fetch')}")
    print(f"  超时时间: {config.get('data_sources.timeout_per_source')}秒")
    print(f"  健康监控: {config.get('data_sources.enable_health_monitor')}")
    
    # 修改配置示例
    print("\n配置修改方式:")
    print("  1. 编辑 config/data_sources.yaml")
    print("  2. 设置环境变量: export QUANT_DATA_CONFIG=my_config.yaml")
    print("  3. 代码中动态更新")
    
    print("配置管理演示完成 ✓")


if __name__ == '__main__':
    print("增强版数据服务使用演示")
    print("=" * 60)
    
    demo_original_usage()
    demo_enhanced_usage()
    demo_smooth_upgrade()
    demo_config_management()
    
    print("\n" + "=" * 60)
    print("演示完成！")
    print("\n使用建议:")
    print("1. 先在测试环境启用增强版: export USE_ENHANCED_DATA_SERVICE=true")
    print("2. 监控健康报告确保多数据源工作正常")
    print("3. 生产环境完全切换后，可移除原始MarketDataService调用")
    print("4. 定期检查配置和日志，优化数据源优先级")

