"""
API 认证模块

提供 JWT 认证和权限控制功能
包含安全增强：环境变量密钥、密钥轮换、密码强度验证
"""

import os
import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from functools import wraps

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext

logger = logging.getLogger(__name__)


# ==================== 密钥管理 ====================

class KeyManager:
    """
    密钥管理器
    
    功能：
    - 从环境变量读取密钥
    - 支持密钥轮换
    - 自动生成安全密钥
    """
    
    def __init__(self):
        """初始化密钥管理器"""
        # 从环境变量读取主密钥
        self._secret_keys: List[str] = []
        
        # 主密钥
        primary_key = os.getenv("SECRET_KEY")
        if primary_key and primary_key != "your-secret-key-here":
            self._secret_keys.append(primary_key)
        else:
            # 开发环境：自动生成密钥（生产环境必须设置环境变量）
            if os.getenv("ENVIRONMENT", "development") == "production":
                raise ValueError(
                    "生产环境必须设置 SECRET_KEY 环境变量！"
                    "请运行: export SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
                )
            generated_key = secrets.token_urlsafe(32)
            self._secret_keys.append(generated_key)
            logger.warning(
                "⚠️  使用自动生成的密钥（仅限开发环境）。"
                "生产环境请设置 SECRET_KEY 环境变量！"
            )
        
        # 备用密钥（用于密钥轮换）
        for i in range(1, 4):
            backup_key = os.getenv(f"SECRET_KEY_{i}")
            if backup_key:
                self._secret_keys.append(backup_key)
        
        self._current_key_index = 0
    
    def get_current_key(self) -> str:
        """获取当前使用的密钥"""
        return self._secret_keys[0]
    
    def get_all_keys(self) -> List[str]:
        """获取所有有效密钥（用于验证 token）"""
        return self._secret_keys
    
    def rotate_keys(self) -> None:
        """
        密钥轮换
        
        将当前密钥移到备用位置，生成新密钥
        """
        old_key = self._secret_keys[0]
        new_key = secrets.token_urlsafe(32)
        
        # 将旧密钥移到备用位置
        self._secret_keys = [new_key] + self._secret_keys[:3]
        
        logger.warning(
            f"密钥已轮换。旧密钥已保留用于验证现有 token。"
        )
    
    @staticmethod
    def generate_key() -> str:
        """生成安全密钥"""
        return secrets.token_urlsafe(32)


# 全局密钥管理器
key_manager = KeyManager()

# 配置
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# 密码加密上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 方案
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/token")


# ==================== 用户模型 ====================

class User:
    """用户模型"""
    def __init__(self, username: str, hashed_password: str, roles: list = None):
        self.username = username
        self.hashed_password = hashed_password
        self.roles = roles or ["user"]
        self.disabled = False


# 模拟用户数据库（生产环境应使用真实数据库）
USERS_DB = {
    "admin": User(
        username="admin",
        hashed_password=pwd_context.hash("admin123"),
        roles=["admin", "user"]
    ),
    "user": User(
        username="user",
        hashed_password=pwd_context.hash("user123"),
        roles=["user"]
    )
}


# ==================== 密码验证 ====================

def validate_password_strength(password: str) -> bool:
    """
    验证密码强度
    
    要求：
    - 至少 12 位
    - 包含大写字母
    - 包含小写字母
    - 包含数字
    - 包含特殊字符
    
    Args:
        password: 待验证的密码
    
    Returns:
        bool: 是否符合强度要求
    
    Raises:
        ValueError: 密码不符合要求
    """
    import re
    
    if len(password) < 12:
        raise ValueError("密码长度至少 12 位")
    
    if not re.search(r"[A-Z]", password):
        raise ValueError("密码必须包含大写字母")
    
    if not re.search(r"[a-z]", password):
        raise ValueError("密码必须包含小写字母")
    
    if not re.search(r"\d", password):
        raise ValueError("密码必须包含数字")
    
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        raise ValueError("密码必须包含特殊字符 (!@#$%^&*等)")
    
    return True


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    获取密码哈希
    
    自动验证密码强度
    """
    # 验证密码强度
    validate_password_strength(password)
    return pwd_context.hash(password)


# ==================== 用户认证 ====================

def get_user(username: str) -> Optional[User]:
    """获取用户信息"""
    return USERS_DB.get(username)


def authenticate_user(username: str, password: str) -> Optional[User]:
    """认证用户"""
    user = get_user(username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


# ==================== Token 管理 ====================

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    创建访问令牌
    
    Args:
        data: 要编码的数据
        expires_delta: 过期时间增量
    
    Returns:
        str: JWT token
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),  # 签发时间
    })
    
    # 使用当前密钥签名
    encoded_jwt = jwt.encode(
        to_encode,
        key_manager.get_current_key(),
        algorithm=ALGORITHM
    )
    
    return encoded_jwt


def decode_token(token: str) -> Dict[str, Any]:
    """
    解码 token（支持密钥轮换）
    
    尝试使用所有有效密钥解码
    """
    # 尝试使用所有有效密钥解码
    for key in key_manager.get_all_keys():
        try:
            payload = jwt.decode(token, key, algorithms=[ALGORITHM])
            return payload
        except JWTError:
            continue
    
    # 所有密钥都验证失败
    raise JWTError("无法验证 token")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """获取当前用户"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = decode_token(token)
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = get_user(username)
    if user is None:
        raise credentials_exception
    
    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """获取当前活跃用户"""
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="用户已禁用")
    return current_user


# ==================== 权限控制 ====================

def require_roles(roles: list):
    """角色权限装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, current_user: User = Depends(get_current_active_user), **kwargs):
            if not any(role in current_user.roles for role in roles):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="权限不足"
                )
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator


# 便捷权限检查函数
require_admin = require_roles(["admin"])
require_user = require_roles(["user", "admin"])


# ==================== 会话管理 ====================

class SessionManager:
    """
    会话管理器
    
    功能：
    - 跟踪活跃会话
    - 限制并发会话数
    - 支持会话撤销
    """
    
    def __init__(self, max_sessions_per_user: int = 5):
        """
        初始化会话管理器
        
        Args:
            max_sessions_per_user: 每个用户的最大会话数
        """
        self.max_sessions_per_user = max_sessions_per_user
        self._sessions: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = asyncio.Lock() if 'asyncio' in dir() else None
    
    def create_session(self, user: User, token: str, request: Request = None) -> str:
        """
        创建会话
        
        Args:
            user: 用户对象
            token: JWT token
            request: HTTP 请求对象
        
        Returns:
            str: 会话 ID
        """
        session_id = secrets.token_urlsafe(16)
        
        session_info = {
            "session_id": session_id,
            "token": token,
            "created_at": datetime.utcnow(),
            "ip_address": request.client.host if request else None,
            "user_agent": request.headers.get("user-agent") if request else None,
        }
        
        # 添加到用户会话列表
        if user.username not in self._sessions:
            self._sessions[user.username] = []
        
        # 检查会话数量限制
        if len(self._sessions[user.username]) >= self.max_sessions_per_user:
            # 移除最旧的会话
            self._sessions[user.username].pop(0)
            logger.info(f"用户 {user.username} 达到最大会话数，移除最旧会话")
        
        self._sessions[user.username].append(session_info)
        
        logger.info(f"创建会话: user={user.username}, session_id={session_id}")
        return session_id
    
    def revoke_session(self, username: str, session_id: str) -> bool:
        """
        撤销会话
        
        Args:
            username: 用户名
            session_id: 会话 ID
        
        Returns:
            bool: 是否成功撤销
        """
        if username not in self._sessions:
            return False
        
        sessions = self._sessions[username]
        for i, session in enumerate(sessions):
            if session["session_id"] == session_id:
                sessions.pop(i)
                logger.info(f"撤销会话: user={username}, session_id={session_id}")
                return True
        
        return False
    
    def revoke_all_sessions(self, username: str) -> int:
        """
        撤销用户所有会话
        
        Args:
            username: 用户名
        
        Returns:
            int: 撤销的会话数
        """
        if username not in self._sessions:
            return 0
        
        count = len(self._sessions[username])
        self._sessions[username] = []
        
        logger.info(f"撤销用户 {username} 的所有会话: {count} 个")
        return count
    
    def get_active_sessions(self, username: str) -> List[Dict[str, Any]]:
        """获取用户的活跃会话列表"""
        return self._sessions.get(username, [])


# 全局会话管理器
session_manager = SessionManager()
