"""
HTTP API 服务模块
提供 RESTful API 接口，支持以服务形式运行
"""
from .server import create_app

__all__ = ['create_app']
