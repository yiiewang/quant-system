"""
异常处理测试
"""
import pytest

from src.core.exceptions import (
    QuantSystemException,
    DataFetchError,
    DataValidationError,
    DataNotFoundError,
    StrategyExecutionError,
    RiskCheckError,
    AuthenticationError,
    ValidationError
)


class TestQuantSystemException:
    """基础异常测试"""
    
    def test_create_exception(self):
        """测试创建异常"""
        exc = QuantSystemException(
            message="测试异常",
            error_code="TEST_ERROR",
            details={'key': 'value'}
        )
        
        assert exc.message == "测试异常"
        assert exc.error_code == "TEST_ERROR"
        assert exc.details == {'key': 'value'}
    
    def test_to_dict(self):
        """测试转换为字典"""
        exc = QuantSystemException(
            message="测试异常",
            error_code="TEST_ERROR",
            details={'key': 'value'}
        )
        
        result = exc.to_dict()
        
        assert result['error'] == "TEST_ERROR"
        assert result['message'] == "测试异常"
        assert result['details'] == {'key': 'value'}
    
    def test_str_representation(self):
        """测试字符串表示"""
        exc = QuantSystemException(
            message="测试异常",
            error_code="TEST_ERROR"
        )
        
        assert str(exc) == "[TEST_ERROR] 测试异常"
        
        exc_with_details = QuantSystemException(
            message="测试异常",
            error_code="TEST_ERROR",
            details={'key': 'value'}
        )
        
        assert "key" in str(exc_with_details)
        assert "value" in str(exc_with_details)


class TestDataErrors:
    """数据相关异常测试"""
    
    def test_data_fetch_error(self):
        """测试数据获取异常"""
        exc = DataFetchError(
            message="获取数据失败",
            symbol="AAPL",
            source="baostock"
        )
        
        assert exc.error_code == "DATA_FETCH_ERROR"
        assert exc.details['symbol'] == "AAPL"
        assert exc.details['source'] == "baostock"
    
    def test_data_validation_error(self):
        """测试数据验证异常"""
        exc = DataValidationError(
            message="字段验证失败",
            field="price",
            value=-100
        )
        
        assert exc.error_code == "DATA_VALIDATION_ERROR"
        assert exc.details['field'] == "price"
        assert exc.details['value'] == "-100"
    
    def test_data_not_found_error(self):
        """测试数据不存在异常"""
        exc = DataNotFoundError(
            message="数据不存在",
            symbol="AAPL",
            date="2024-01-01"
        )
        
        assert exc.error_code == "DATA_NOT_FOUND"
        assert exc.details['symbol'] == "AAPL"
        assert exc.details['date'] == "2024-01-01"


class TestStrategyErrors:
    """策略相关异常测试"""
    
    def test_strategy_execution_error(self):
        """测试策略执行异常"""
        exc = StrategyExecutionError(
            message="策略执行失败",
            strategy_name="my_strategy",
            phase="backtest"
        )
        
        assert exc.error_code == "STRATEGY_EXECUTION_ERROR"
        assert exc.details['strategy_name'] == "my_strategy"
        assert exc.details['phase'] == "backtest"


class TestRiskErrors:
    """风控相关异常测试"""
    
    def test_risk_check_error(self):
        """测试风控检查异常"""
        exc = RiskCheckError(
            message="超过持仓限制",
            risk_type="position_limit",
            limit=10000,
            actual=15000
        )
        
        assert exc.error_code == "RISK_CHECK_FAILED"
        assert exc.details['risk_type'] == "position_limit"
        assert exc.details['limit'] == 10000
        assert exc.details['actual'] == 15000


class TestAPIErrors:
    """API 相关异常测试"""
    
    def test_authentication_error(self):
        """测试认证异常"""
        exc = AuthenticationError(message="认证失败")
        
        assert exc.error_code == "AUTHENTICATION_ERROR"
        assert exc.message == "认证失败"
    
    def test_validation_error(self):
        """测试输入验证异常"""
        exc = ValidationError(
            message="输入验证失败",
            field="symbol",
            constraint="^[A-Z]{6,10}$"
        )
        
        assert exc.error_code == "VALIDATION_ERROR"
        assert exc.details['field'] == "symbol"
        assert exc.details['constraint'] == "^[A-Z]{6,10}$"


class TestExceptionHandling:
    """异常处理测试"""
    
    def test_catch_base_exception(self):
        """测试捕获基础异常"""
        try:
            raise DataFetchError("数据获取失败")
        except QuantSystemException as e:
            assert isinstance(e, DataFetchError)
            assert e.message == "数据获取失败"
    
    def test_exception_chain(self):
        """测试异常链"""
        try:
            try:
                raise ValueError("原始错误")
            except ValueError as e:
                raise DataFetchError("数据获取失败") from e
        except DataFetchError as e:
            assert e.__cause__ is not None
            assert isinstance(e.__cause__, ValueError)
    
    def test_exception_in_function(self):
        """测试函数中的异常"""
        def fetch_data(symbol: str):
            if not symbol:
                raise DataValidationError(
                    message="股票代码不能为空",
                    field="symbol"
                )
            return f"data for {symbol}"
        
        # 正常情况
        result = fetch_data("AAPL")
        assert result == "data for AAPL"
        
        # 异常情况
        with pytest.raises(DataValidationError) as exc_info:
            fetch_data("")
        
        assert exc_info.value.details['field'] == "symbol"
