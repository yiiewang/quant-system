"""
类型注解辅助模块测试
"""
import pytest
from datetime import datetime
import pandas as pd

from src.utils.type_hints import (
    Result,
    check_type,
    validate_dataframe,
    enforce_types,
    DataProvider,
    Strategy
)


class TestResult:
    """Result 类型测试"""
    
    def test_success_result(self):
        """测试成功结果"""
        result = Result.success(42)
        
        assert result.is_success()
        assert not result.is_error()
        assert result.value == 42
    
    def test_error_result(self):
        """测试错误结果"""
        result = Result[int].error("除数不能为 0")
        
        assert not result.is_success()
        assert result.is_error()
        assert result.error == "除数不能为 0"
    
    def test_value_on_error(self):
        """测试失败结果访问值"""
        result = Result.error("错误")
        
        with pytest.raises(ValueError, match="无法获取失败结果的值"):
            _ = result.value
    
    def test_error_on_success(self):
        """测试成功结果访问错误"""
        result = Result.success(42)
        
        with pytest.raises(ValueError, match="无法获取成功结果的错误信息"):
            _ = result.error
    
    def test_unwrap_success(self):
        """测试 unwrap 成功"""
        result = Result.success(42)
        
        assert result.unwrap() == 42
        assert result.unwrap(default=0) == 42
    
    def test_unwrap_error(self):
        """测试 unwrap 失败"""
        result = Result[int].error("错误")
        
        assert result.unwrap() is None
        assert result.unwrap(default=100) == 100
    
    def test_divide_function(self):
        """测试除法函数示例"""
        def divide(a: float, b: float) -> Result[float]:
            if b == 0:
                return Result.error("除数不能为 0")
            return Result.success(a / b)
        
        # 成功情况
        result1 = divide(10, 2)
        assert result1.is_success()
        assert result1.value == 5.0
        
        # 失败情况
        result2 = divide(10, 0)
        assert result2.is_error()
        assert result2.error == "除数不能为 0"


class TestCheckType:
    """类型检查测试"""
    
    def test_basic_types(self):
        """测试基本类型"""
        assert check_type(42, int)
        assert check_type(3.14, float)
        assert check_type("hello", str)
        assert check_type(True, bool)
    
    def test_list_type(self):
        """测试列表类型"""
        assert check_type([1, 2, 3], list)
        assert check_type([1, 2, 3], list)
        assert not check_type([1, 2, 3], int)
    
    def test_dict_type(self):
        """测试字典类型"""
        assert check_type({'a': 1}, dict)
        assert check_type({'a': 1}, dict)
        assert not check_type({'a': 1}, list)
    
    def test_union_type(self):
        """测试 Union 类型"""
        from typing import Union
        
        assert check_type(42, Union[int, str])
        assert check_type("hello", Union[int, str])
        assert not check_type([1, 2], Union[int, str])
    
    def test_optional_type(self):
        """测试 Optional 类型"""
        from typing import Optional
        
        assert check_type(42, Optional[int])
        assert check_type(None, Optional[int])
        assert not check_type("hello", Optional[int])


class TestValidateDataFrame:
    """DataFrame 验证测试"""
    
    def test_validate_basic(self):
        """测试基本验证"""
        df = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
        
        assert validate_dataframe(df)
        assert not validate_dataframe(None)
        assert not validate_dataframe(pd.DataFrame())
    
    def test_validate_required_columns(self):
        """测试必需列验证"""
        df = pd.DataFrame({'a': [1, 2], 'b': [3, 4], 'c': [5, 6]})
        
        assert validate_dataframe(df, required_columns=['a', 'b'])
        assert not validate_dataframe(df, required_columns=['a', 'd'])
    
    def test_validate_column_types(self):
        """测试列类型验证"""
        df = pd.DataFrame({
            'symbol': ['AAPL', 'GOOGL'],
            'price': [100.0, 200.0],
            'volume': [1000, 2000]
        })
        
        assert validate_dataframe(
            df,
            column_types={'symbol': str, 'price': float}
        )
        
        # 类型不匹配
        assert not validate_dataframe(
            df,
            column_types={'symbol': int}
        )


class TestEnforceTypes:
    """类型强制装饰器测试"""
    
    def test_correct_types(self):
        """测试正确类型"""
        @enforce_types
        def add(a: int, b: int) -> int:
            return a + b
        
        assert add(1, 2) == 3
    
    def test_wrong_argument_type(self):
        """测试参数类型错误"""
        @enforce_types
        def process(name: str, value: int) -> str:
            return f"{name}: {value}"
        
        # 正确
        assert process("test", 42) == "test: 42"
        
        # 错误
        with pytest.raises(TypeError, match="参数 'value' 类型错误"):
            process("test", "not an int")
    
    def test_wrong_return_type(self):
        """测试返回值类型错误"""
        @enforce_types
        def wrong_return() -> int:
            return "not an int"
        
        with pytest.raises(TypeError, match="返回值类型错误"):
            wrong_return()
    
    def test_optional_parameter(self):
        """测试可选参数"""
        from typing import Optional
        
        @enforce_types
        def process(value: Optional[int] = None) -> str:
            return str(value)
        
        assert process(42) == "42"
        assert process(None) == "None"
        assert process() == "None"


class TestProtocols:
    """协议测试"""
    
    def test_data_provider_protocol(self):
        """测试数据提供者协议"""
        class MyDataProvider:
            def fetch(
                self,
                symbol: str,
                start_date: datetime,
                end_date: datetime
            ) -> pd.DataFrame:
                return pd.DataFrame({'price': [100, 200]})
        
        provider = MyDataProvider()
        assert isinstance(provider, DataProvider)
    
    def test_strategy_protocol(self):
        """测试策略协议"""
        class MyStrategy:
            def on_bar(self, bar: dict) -> dict:
                return {'signal': 'buy'}
            
            def on_tick(self, tick: dict) -> dict:
                return None
        
        strategy = MyStrategy()
        assert isinstance(strategy, Strategy)
