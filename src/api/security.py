"""
API 安全模块

提供输入验证、请求签名、防重放攻击等安全功能
"""
import hashlib
import hmac
import time
import re
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, validator, Field
from fastapi import Request, HTTPException, status

logger = logging.getLogger(__name__)


# ==================== 输入验证模型 ====================

class BacktestRequest(BaseModel):
    """回测请求验证"""
    symbols: List[str] = Field(..., min_items=1, max_items=50)
    start_date: str
    end_date: str
    strategy: str
    initial_capital: float = Field(100000.0, gt=0)
    
    @validator('symbols')
    def validate_symbols(cls, v):
        """验证股票代码"""
        for symbol in v:
            if not re.match(r'^[A-Za-z0-9]{6,10}$', symbol):
                raise ValueError(f'无效的股票代码格式: {symbol}')
        return v
    
    @validator('start_date', 'end_date')
    def validate_date(cls, v):
        """验证日期格式"""
        try:
            datetime.strptime(v, '%Y-%m-%d')
        except ValueError:
            raise ValueError('日期格式必须为 YYYY-MM-DD')
        return v
    
    @validator('end_date')
    def validate_date_range(cls, v, values):
        """验证日期范围"""
        if 'start_date' in values:
            start = datetime.strptime(values['start_date'], '%Y-%m-%d')
            end = datetime.strptime(v, '%Y-%m-%d')
            
            if end < start:
                raise ValueError('结束日期不能早于开始日期')
            
            # 限制最大日期范围（避免过大的回测请求）
            if (end - start).days > 365 * 5:
                raise ValueError('日期范围不能超过 5 年')
        
        return v


class StrategyRequest(BaseModel):
    """策略请求验证"""
    name: str = Field(..., min_length=1, max_length=100)
    config: Dict[str, Any]
    enabled: bool = True
    
    @validator('name')
    def validate_name(cls, v):
        """验证策略名称"""
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('策略名称只能包含字母、数字、下划线和连字符')
        return v


class OrderRequest(BaseModel):
    """订单请求验证"""
    symbol: str
    side: str  # buy/sell
    quantity: float = Field(..., gt=0)
    price: Optional[float] = Field(None, gt=0)
    order_type: str = 'market'  # market/limit
    
    @validator('symbol')
    def validate_symbol(cls, v):
        """验证股票代码"""
        if not re.match(r'^[A-Za-z0-9]{6,10}$', v):
            raise ValueError(f'无效的股票代码: {v}')
        return v
    
    @validator('side')
    def validate_side(cls, v):
        """验证交易方向"""
        if v.lower() not in ['buy', 'sell']:
            raise ValueError('交易方向必须是 buy 或 sell')
        return v.lower()
    
    @validator('order_type')
    def validate_order_type(cls, v):
        """验证订单类型"""
        if v.lower() not in ['market', 'limit']:
            raise ValueError('订单类型必须是 market 或 limit')
        return v.lower()
    
    @validator('price')
    def validate_price(cls, v, values):
        """验证价格"""
        if values.get('order_type') == 'limit' and v is None:
            raise ValueError('限价单必须指定价格')
        return v


class DataFetchRequest(BaseModel):
    """数据获取请求验证"""
    symbols: List[str] = Field(..., min_items=1, max_items=100)
    start_date: str
    end_date: str
    frequency: str = 'daily'
    
    @validator('symbols')
    def validate_symbols(cls, v):
        """验证股票代码"""
        for symbol in v:
            if not re.match(r'^[A-Za-z0-9]{6,10}$', symbol):
                raise ValueError(f'无效的股票代码: {symbol}')
        return v
    
    @validator('frequency')
    def validate_frequency(cls, v):
        """验证频率"""
        valid_frequencies = ['daily', 'weekly', 'monthly', '1min', '5min', '15min', '30min', '60min']
        if v.lower() not in valid_frequencies:
            raise ValueError(f'频率必须是: {", ".join(valid_frequencies)}')
        return v.lower()


class UserCreateRequest(BaseModel):
    """用户创建请求验证"""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=12)
    roles: List[str] = ['user']
    
    @validator('username')
    def validate_username(cls, v):
        """验证用户名"""
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('用户名只能包含字母、数字、下划线和连字符')
        return v
    
    @validator('password')
    def validate_password(cls, v):
        """验证密码强度"""
        if len(v) < 12:
            raise ValueError('密码长度至少 12 位')
        
        if not re.search(r"[A-Z]", v):
            raise ValueError('密码必须包含大写字母')
        
        if not re.search(r"[a-z]", v):
            raise ValueError('密码必须包含小写字母')
        
        if not re.search(r"\d", v):
            raise ValueError('密码必须包含数字')
        
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError('密码必须包含特殊字符')
        
        return v


# ==================== 请求签名验证 ====================

class RequestSignatureVerifier:
    """
    请求签名验证器
    
    功能：
    - HMAC-SHA256 签名验证
    - 时间戳防重放攻击
    - 请求完整性验证
    
    Usage:
        verifier = RequestSignatureVerifier(secret_key)
        
        # 验证请求
        if not verifier.verify(request):
            raise HTTPException(401, "签名验证失败")
    """
    
    def __init__(
        self,
        secret_key: str,
        timestamp_tolerance: int = 300  # 5 分钟
    ):
        """
        初始化签名验证器
        
        Args:
            secret_key: 密钥
            timestamp_tolerance: 时间戳容差（秒）
        """
        self.secret_key = secret_key.encode()
        self.timestamp_tolerance = timestamp_tolerance
    
    def generate_signature(
        self,
        method: str,
        path: str,
        timestamp: str,
        body: bytes = b''
    ) -> str:
        """
        生成签名
        
        Args:
            method: HTTP 方法
            path: 请求路径
            timestamp: 时间戳
            body: 请求体
        
        Returns:
            str: 签名
        """
        # 构造签名字符串
        string_to_sign = f"{method.upper()}\n{path}\n{timestamp}\n"
        
        if body:
            # 计算请求体哈希
            body_hash = hashlib.sha256(body).hexdigest()
            string_to_sign += body_hash
        
        # 计算签名
        signature = hmac.new(
            self.secret_key,
            string_to_sign.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    def verify(self, request: Request) -> bool:
        """
        验证请求签名
        
        Args:
            request: FastAPI 请求对象
        
        Returns:
            bool: 是否验证通过
        """
        # 获取签名相关头部
        signature = request.headers.get("X-Signature")
        timestamp = request.headers.get("X-Timestamp")
        
        if not signature or not timestamp:
            logger.warning("请求缺少签名或时间戳")
            return False
        
        try:
            timestamp_float = float(timestamp)
        except ValueError:
            logger.warning(f"无效的时间戳格式: {timestamp}")
            return False
        
        # 检查时间戳（防重放攻击）
        current_time = time.time()
        if abs(current_time - timestamp_float) > self.timestamp_tolerance:
            logger.warning(
                f"请求时间戳过期: {timestamp_float}, "
                f"当前时间: {current_time}, "
                f"容差: {self.timestamp_tolerance}s"
            )
            return False
        
        # 获取请求体（需要缓存）
        # 注意：FastAPI 的请求体只能读取一次，需要在中间件中缓存
        body = getattr(request, '_body', b'')
        
        # 计算预期签名
        expected_signature = self.generate_signature(
            method=request.method,
            path=request.url.path,
            timestamp=timestamp,
            body=body
        )
        
        # 比较签名（使用恒定时间比较，防止时序攻击）
        if not hmac.compare_digest(signature, expected_signature):
            logger.warning(
                f"签名不匹配: expected={expected_signature[:16]}..., "
                f"actual={signature[:16]}..."
            )
            return False
        
        return True
    
    def verify_or_raise(self, request: Request) -> None:
        """
        验证请求签名，失败时抛出异常
        
        Args:
            request: FastAPI 请求对象
        
        Raises:
            HTTPException: 签名验证失败
        """
        if not self.verify(request):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="签名验证失败"
            )


# ==================== IP 白名单 ====================

class IPWhitelist:
    """
    IP 白名单管理
    
    用于限制特定 IP 访问敏感 API
    """
    
    def __init__(self, allowed_ips: List[str] = None):
        """
        初始化 IP 白名单
        
        Args:
            allowed_ips: 允许的 IP 列表
        """
        self.allowed_ips = set(allowed_ips or [])
    
    def is_allowed(self, ip: str) -> bool:
        """
        检查 IP 是否在白名单中
        
        Args:
            ip: IP 地址
        
        Returns:
            bool: 是否允许
        """
        # 如果白名单为空，允许所有 IP
        if not self.allowed_ips:
            return True
        
        return ip in self.allowed_ips
    
    def add_ip(self, ip: str) -> None:
        """添加 IP 到白名单"""
        self.allowed_ips.add(ip)
        logger.info(f"添加 IP 到白名单: {ip}")
    
    def remove_ip(self, ip: str) -> None:
        """从白名单移除 IP"""
        self.allowed_ips.discard(ip)
        logger.info(f"从白名单移除 IP: {ip}")


# ==================== 速率限制 ====================

class RateLimiter:
    """
    简单的速率限制器
    
    使用滑动窗口算法
    """
    
    def __init__(
        self,
        max_requests: int = 100,
        window_seconds: int = 60
    ):
        """
        初始化速率限制器
        
        Args:
            max_requests: 时间窗口内最大请求数
            window_seconds: 时间窗口（秒）
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, List[float]] = {}
    
    def is_allowed(self, key: str) -> bool:
        """
        检查是否允许请求
        
        Args:
            key: 限流键（通常是 IP 或用户 ID）
        
        Returns:
            bool: 是否允许
        """
        current_time = time.time()
        
        # 获取该键的请求历史
        if key not in self._requests:
            self._requests[key] = []
        
        requests = self._requests[key]
        
        # 移除过期的请求记录
        cutoff_time = current_time - self.window_seconds
        while requests and requests[0] < cutoff_time:
            requests.pop(0)
        
        # 检查是否超过限制
        if len(requests) >= self.max_requests:
            return False
        
        # 记录本次请求
        requests.append(current_time)
        return True
    
    def get_remaining(self, key: str) -> int:
        """
        获取剩余配额
        
        Args:
            key: 限流键
        
        Returns:
            int: 剩余请求数
        """
        current_time = time.time()
        
        if key not in self._requests:
            return self.max_requests
        
        requests = self._requests[key]
        cutoff_time = current_time - self.window_seconds
        
        # 统计有效请求数
        valid_requests = sum(1 for t in requests if t >= cutoff_time)
        
        return max(0, self.max_requests - valid_requests)
