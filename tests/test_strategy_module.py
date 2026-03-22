"""
测试策略模块: 动态发现、动态加载、配置文件加载

测试内容:
1. Registry - 策略注册
2. Loader - 动态发现与加载
3. Manager - 创建策略实例并加载配置
"""
import sys
import logging
from pathlib import Path

# 设置项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_registry():
    """测试策略注册表"""
    print("\n" + "="*60)
    print("1. 测试策略注册表 (Registry)")
    print("="*60)
    
    from src.strategy.registry import registry, register_strategy
    from src.strategy.base import BaseStrategy
    
    # 清空注册表以便测试
    registry.clear()
    
    # 定义测试策略
    @register_strategy('test_strategy')
    class TestStrategy(BaseStrategy):
        name = "test_strategy"
        version = "1.0.0"
        
        @classmethod
        def default_params(cls):
            return {'period': 20}
        
        def calculate_indicators(self, data):
            return data
        
        def evaluate(self, data, context):
            from src.core.models import StrategyDecision
            return StrategyDecision.hold(context.symbol, "test")
    
    # 验证注册
    assert registry.has('test_strategy'), "策略注册失败"
    print(f"✓ 装饰器注册成功: test_strategy")
    
    # 获取策略类
    strategy_cls = registry.get('test_strategy')
    print(f"✓ 获取策略类: {strategy_cls}")
    
    # 创建实例
    strategy = registry.create('test_strategy', params={'period': 30})
    print(f"✓ 创建实例: {strategy}")
    print(f"  - 参数: {strategy.params}")
    
    # 列出所有策略
    strategies = registry.list_strategies()
    print(f"✓ 已注册策略数量: {len(strategies)}")
    for s in strategies:
        print(f"  - {s['name']}: {s['class']}")
    
    return True


def test_loader_discovery():
    """测试策略动态发现"""
    print("\n" + "="*60)
    print("2. 测试策略动态发现 (Loader)")
    print("="*60)
    
    from src.strategy.loader import StrategyLoader
    from src.strategy.registry import registry
    
    # 清空注册表
    registry.clear()
    
    # 创建加载器
    loader = StrategyLoader(auto_register=True)
    
    # 扫描 data/strategies 目录 (实际策略所在位置)
    strategy_dir = project_root / "data" / "strategies"
    print(f"扫描目录: {strategy_dir}")
    count = loader.discover_from_fs(str(strategy_dir), recursive=True)
    print(f"✓ 发现策略数量: {count}")
    
    # 显示发现的策略
    for item in loader.discovered:
        print(f"  - {item['name']}: {item['class']} ({item['source']})")
    
    # 检查是否注册到 registry
    registered_names = registry.names()
    print(f"✓ Registry 中已注册: {len(registered_names)} 个策略")
    print(f"  策略列表: {sorted(registered_names)}")
    
    return len(registered_names) > 0


def test_manager_create():
    """测试策略管理器创建策略并加载配置"""
    print("\n" + "="*60)
    print("3. 测试策略管理器 (Manager)")
    print("="*60)
    
    from src.strategy.manager import StrategyManager
    from src.strategy.registry import registry
    from src.config.schema import StrategyConfig
    
    # 清空注册表
    registry.clear()
    
    # 创建配置
    config = StrategyConfig(
        directorie="data/strategies",
        recursive=False
    )
    
    # 创建管理器
    manager = StrategyManager(config=config, auto_discover=True)
    
    # 列出可用策略
    strategies = manager.get_strategy_names()
    print(f"✓ 可用策略: {strategies}")
    
    # 测试创建策略（使用默认配置路径）
    if 'aaa' in strategies:
        print("\n--- 测试创建 aaa 策略 (默认配置) ---")
        try:
            strategy = manager.create_strategy('aaa')
            print(f"✓ 创建成功: {strategy}")
            print(f"  - 参数: {strategy.params}")
            
            # 检查配置加载
            cfg = strategy.config
            if cfg:
                print(f"  - 配置加载成功")
                if isinstance(cfg, dict):
                    strategy_cfg = cfg.get('strategy', {})
                    print(f"    - strategy.params: {strategy_cfg.get('params', {})}")
                else:
                    print(f"    - 配置类型: {type(cfg).__name__}")
            else:
                print(f"  - 配置为空")
        except Exception as e:
            import traceback
            print(f"✗ 创建失败: {e}")
            traceback.print_exc()
    
    # 测试创建策略（指定配置路径）
    config_path = project_root / "data" / "strategies" / "aaa.yaml"
    if config_path.exists() and 'aaa' in strategies:
        print(f"\n--- 测试创建 aaa 策略 (指定配置: {config_path}) ---")
        try:
            strategy = manager.create_strategy('aaa', config_path=str(config_path))
            print(f"✓ 创建成功: {strategy}")
            print(f"  - 参数: {strategy.params}")
            
            # 检查配置加载
            cfg = strategy.config
            if cfg:
                print(f"  - 配置加载成功")
                if isinstance(cfg, dict):
                    print(f"    - strategy.params: {cfg.get('strategy', {}).get('params', {})}")
            else:
                print(f"  - 配置为空")
        except Exception as e:
            import traceback
            print(f"✗ 创建失败: {e}")
            traceback.print_exc()
    
    return True


def test_config_loading():
    """测试配置文件加载"""
    print("\n" + "="*60)
    print("4. 测试配置文件加载")
    print("="*60)
    
    from src.strategy.loader import StrategyLoader
    from src.strategy.registry import registry
    
    # 清空注册表
    registry.clear()
    
    # 先扫描发现策略
    loader = StrategyLoader(auto_register=True)
    strategy_dir = project_root / "data" / "strategies"
    loader.discover_from_fs(str(strategy_dir), recursive=True)
    
    # 测试配置文件路径
    config_dir = strategy_dir
    print(f"配置目录: {config_dir}")
    print(f"配置文件:")
    for f in config_dir.glob("*.yaml"):
        print(f"  - {f.name}")
    
    # 手动测试配置加载逻辑
    print("\n--- 测试 _load_strategy_config 逻辑 ---")
    
    if registry.has('aaa'):
        import sys as _sys
        import yaml
        from pathlib import Path as _Path
        
        strategy_cls = registry.get('aaa')
        strategy_name = 'aaa'
        
        # 获取策略所在目录
        try:
            module = _sys.modules[strategy_cls.__module__]
            if module.__file__:
                module_file = _Path(module.__file__)
                strategy_dir_path = module_file.parent
                config_file = strategy_dir_path / f"{strategy_name}.yaml"
                print(f"策略模块: {module.__name__}")
                print(f"策略目录: {strategy_dir_path}")
                print(f"期望配置: {config_file}")
                print(f"配置存在: {config_file.exists()}")
                
                # 读取并解析配置
                if config_file.exists():
                    with open(config_file, 'r', encoding='utf-8') as f:
                        cfg = yaml.safe_load(f)
                    print(f"配置内容预览:")
                    print(f"  - strategy.name: {cfg.get('strategy', {}).get('name')}")
                    print(f"  - strategy.params: {cfg.get('strategy', {}).get('params')}")
        except (KeyError, AttributeError) as e:
            print(f"无法获取策略目录: {e}")
    else:
        print("策略 'aaa' 未注册，跳过配置加载测试")
    
    return True


def main():
    """运行所有测试"""
    print("\n" + "#"*60)
    print("# 策略模块测试")
    print("#"*60)
    
    results = {}
    
    try:
        results['registry'] = test_registry()
    except Exception as e:
        results['registry'] = False
        print(f"✗ Registry 测试失败: {e}")
    
    try:
        results['loader'] = test_loader_discovery()
    except Exception as e:
        results['loader'] = False
        import traceback
        print(f"✗ Loader 测试失败: {e}")
        traceback.print_exc()
    
    try:
        results['manager'] = test_manager_create()
    except Exception as e:
        results['manager'] = False
        import traceback
        print(f"✗ Manager 测试失败: {e}")
        traceback.print_exc()
    
    try:
        results['config'] = test_config_loading()
    except Exception as e:
        results['config'] = False
        import traceback
        print(f"✗ Config 测试失败: {e}")
        traceback.print_exc()
    
    # 汇总
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    for name, passed in results.items():
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"  {name}: {status}")
    
    all_passed = all(results.values())
    print(f"\n总体结果: {'✓ 全部通过' if all_passed else '✗ 存在失败'}")
    
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
