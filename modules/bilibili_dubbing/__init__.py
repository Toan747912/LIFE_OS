"""Module Bilibili Dubbing — tải video Bilibili, lồng tiếng Việt và quản lý thư viện.

Module độc lập: `app.py` chỉ cần `include_router(router)`. Mọi code còn lại
nằm trong thư mục này và không sửa các module Stable của LIFE_OS.
"""
from modules.bilibili_dubbing.api.router import router

__all__ = ["router"]
