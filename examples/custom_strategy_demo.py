#!/usr/bin/env python3
"""
自定义策略使用示例

演示如何：
1. 创建自定义策略目录
2. 添加自定义策略
3. 使用自定义策略运行回测
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def main():
    print("=" * 60)
    print("自定义策略使用示例")
    print("=" * 60)
    print()

    # 1. 检查自定义策略目录
    custom_dir = Path("data/strategies")
    if not custom_dir.exists():
        print(f"创建自定义策略目录: {custom_dir}")
        custom_dir.mkdir(parents=True, exist_ok=True)

    # 2. 列出所有策略
    print("\n1. 查看所有可用策略")
    print("-" * 60)

    from src.cli.main import _get_available_strategies
    strategies = _get_available_strategies()

    print(f"共 {len(strategies)} 个策略:")
    for i, name in enumerate(strategies, 1):
        print(f"  {i:2}. {name}")

    # 3. 标注自定义策略
    from src.strategy.registry import registry
    all_strategies = registry.list_strategies()

    print("\n2. 识别自定义策略")
    print("-" * 60)

    for info in all_strategies:
        source = info.get('source', '')
        if 'data/strategies' in source:
            print(f"  ✓ {info['name']} (自定义策略)")
            print(f"    来源: {source}")

    # 4. 使用自定义策略进行分析
    if 'custom_example' in strategies:
        print("\n3. 使用自定义策略分析市场")
        print("-" * 60)

        from src.config.base import load_config
        from src.config.schema import Config
        from src.runner.application import ApplicationRunner

        config = load_config(Config, 'src/strategy/configs/default.yaml')
        config.strategy.name = 'custom_example'

        params = {
            'mode': 'analyze',
            'symbols': ['000001.SZ'],
            'days': 30,
            'source': 'baostock',
            'verbose': False,
        }

        runner = ApplicationRunner(config=config, params=params)
        result = runner.start('analyze')

        if 'error' not in result:
            print(f"\n分析结果:")
            print(f"  股票代码: {result['symbol']}")
            print(f"  当前状态: {result['status']}")
            print(f"  建议操作: {result['action']}")
            print(f"  置信度:   {result['confidence']:.0%}")
            print(f"\n  分析理由:")
            for line in result.get('reason', '').split('\n'):
                print(f"    {line.strip()}")
        else:
            print(f"分析失败: {result['error']}")

    print("\n" + "=" * 60)
    print("示例完成")
    print("=" * 60)
    print()
    print("提示:")
    print("  1. 在 data/strategies 目录中添加你的自定义策略")
    print("  2. 策略文件命名需符合 *_strategy.py 或 strategy_*.py")
    print("  3. 运行 'python -m src.cli.main interactive' 进入交互模式")
    print("  4. 使用 'reload-strategies' 重新加载策略")
    print()


if __name__ == "__main__":
    main()
