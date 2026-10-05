"""Kiểm tra trực tuyến xem cookie đã lưu còn đăng nhập được không (chỉ đọc thông tin tài khoản, không đổi gì)."""
from __future__ import annotations

import json
import urllib.request
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any, Callable, Dict, Optional

NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
# (url, file cookie, thời gian chờ) -> nội dung JSON đã giải mã
FetchFn = Callable[[str, Path, int], Dict[str, Any]]


def http_fetch(url: str, cookie_path: Path, timeout_s: int) -> Dict[str, Any]:
    jar = MozillaCookieJar(str(cookie_path))
    jar.load(ignore_discard=True, ignore_expires=True)
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
        "Referer": "https://www.bilibili.com/",
    })
    with opener.open(request, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


class CookieChecker:
    def __init__(self, cookie_path: Path, fetch: Optional[FetchFn] = None, timeout_s: int = 10):
        self._cookie_path = Path(cookie_path)
        self._fetch = fetch or http_fetch
        self._timeout_s = timeout_s

    def _has_cookies_for(self, site: str) -> bool:
        try:
            lines = self._cookie_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return False
        return any(line.split("\t")[0].lstrip(".").lower().endswith(site)
                   for line in lines if line and not line.startswith("#"))

    def check(self) -> Dict[str, Any]:
        """Kết quả luôn có `checked` (đã hỏi được máy chủ chưa), `logged_in` (None nếu không biết) và `message`."""
        if not self._cookie_path.is_file():
            return {"checked": False, "logged_in": None, "message": "Chưa lưu cookie nào."}
        if not self._has_cookies_for("bilibili.com"):
            return {"checked": False, "logged_in": None, "message":
                    "Cookie đã lưu là của bilibili.tv. Module chỉ kiểm tra trực tuyến được bilibili.com; "
                    "với bilibili.tv, hãy quét thử một link cần đăng nhập để biết cookie còn dùng được không."}
        try:
            payload = self._fetch(NAV_URL, self._cookie_path, self._timeout_s)
        except Exception as exc:  # noqa: BLE001 - mất mạng, bị chặn, phản hồi không phải JSON
            return {"checked": False, "logged_in": None,
                    "message": f"Không hỏi được máy chủ Bilibili ({type(exc).__name__}). Kiểm tra mạng rồi thử lại."}
        data = payload.get("data") or {}
        if payload.get("code") == 0 and data.get("isLogin"):
            vip = bool(data.get("vipStatus"))
            return {"checked": True, "logged_in": True, "username": data.get("uname"), "vip": vip,
                    "message": f"Cookie còn hiệu lực, đang đăng nhập tài khoản {data.get('uname') or ''}"
                               f"{' (có VIP)' if vip else ''}.".replace("  ", " ")}
        return {"checked": True, "logged_in": False,
                "message": "Cookie đã hết hạn hoặc không hợp lệ. Hãy đăng nhập lại trên trình duyệt và lấy cookie mới."}
