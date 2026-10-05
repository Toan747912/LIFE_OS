"""Lưu cookie đăng nhập Bilibili vào file cookies.txt (định dạng Netscape mà yt-dlp đọc trực tiếp).

Cookie là thông tin đăng nhập: file chỉ nằm trên máy người dùng, được gitignore,
và giá trị cookie không bao giờ được trả ngược về trình duyệt qua API.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.bilibili_dubbing.domain.errors import InvalidRequest

_HEADER = "# Netscape HTTP Cookie File\n# Do module bilibili_dubbing tạo. Không chia sẻ file này.\n\n"
_ALLOWED_DOMAINS = ("bilibili.com", "bilibili.tv", "biliintl.com")
_SITES = {"bilibili.com": ".bilibili.com", "bilibili.tv": ".bilibili.tv"}
_LOGIN_COOKIE = "SESSDATA"
_DEFAULT_LIFETIME_S = 180 * 24 * 3600
_MAX_TEXT_LENGTH = 200_000


@dataclass(frozen=True)
class Cookie:
    domain: str
    name: str
    value: str
    path: str = "/"
    secure: bool = False
    expires: int = 0   # 0 = cookie phiên, không có hạn

    def to_line(self) -> str:
        return "\t".join([
            self.domain,
            "TRUE" if self.domain.startswith(".") else "FALSE",
            self.path or "/",
            "TRUE" if self.secure else "FALSE",
            str(self.expires),
            self.name,
            self.value,
        ])


class CookieStore:
    def __init__(self, path: Path):
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    # ── Ghi ───────────────────────────────────────────────────────────────────
    def save_from_text(self, raw: str, site: str = "bilibili.com") -> Dict[str, Any]:
        """Nhận nội dung người dùng dán vào, tự nhận dạng định dạng, chỉ giữ cookie của Bilibili."""
        text = (raw or "").strip()
        if not text:
            raise InvalidRequest("Chưa dán nội dung cookie.")
        if len(text) > _MAX_TEXT_LENGTH:
            raise InvalidRequest("Nội dung cookie quá dài.")
        if site not in _SITES:
            raise InvalidRequest("Trang không hợp lệ. Chọn bilibili.com hoặc bilibili.tv.")

        cookies = self.parse(text, _SITES[site])
        cookies = [c for c in cookies if self._is_bilibili_domain(c.domain) and self._is_clean(c)]
        if not cookies:
            raise InvalidRequest("Không tìm thấy cookie nào của Bilibili trong nội dung đã dán.")

        unique = {(c.domain, c.path, c.name): c for c in cookies}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._path.with_suffix(".tmp")
        temp.write_text(_HEADER + "\n".join(c.to_line() for c in unique.values()) + "\n", encoding="utf-8")
        try:
            os.chmod(temp, 0o600)
        except OSError:
            pass
        os.replace(temp, self._path)
        return self.status()

    def clear(self) -> Dict[str, Any]:
        if self._path.is_file():
            self._path.unlink()
        return self.status()

    # ── Đọc trạng thái (không trả giá trị cookie) ─────────────────────────────
    def status(self) -> Dict[str, Any]:
        cookies = self._load()
        now = int(time.time())
        login = [c for c in cookies if c.name == _LOGIN_COOKIE]
        dated = [c.expires for c in (login or cookies) if c.expires > 0]
        expires_at: Optional[int] = min(dated) if dated else None
        return {
            "configured": bool(cookies),
            "cookie_count": len(cookies),
            "sites": sorted({self._site_of(c.domain) for c in cookies}),
            "has_login_cookie": bool(login),
            "expires_at": expires_at,
            "expired": bool(expires_at and expires_at < now),
        }

    def _load(self) -> List[Cookie]:
        if not self._path.is_file():
            return []
        try:
            return self._parse_netscape(self._path.read_text(encoding="utf-8"))
        except OSError:
            return []

    # ── Nhận dạng định dạng ───────────────────────────────────────────────────
    @classmethod
    def parse(cls, text: str, default_domain: str) -> List[Cookie]:
        """Hỗ trợ 4 dạng: file cookies.txt, JSON của extension, chuỗi header `a=b; c=d`, giá trị SESSDATA."""
        if text.lstrip().startswith(("[", "{")):
            return cls._parse_json(text)
        if "\t" in text:
            return cls._parse_netscape(text)
        expires = int(time.time()) + _DEFAULT_LIFETIME_S
        if text.lower().startswith("cookie:"):
            text = text[7:].strip()
        if "=" in text:
            cookies = []
            for part in text.split(";"):
                name, sep, value = part.strip().partition("=")
                if sep and name.strip():
                    cookies.append(Cookie(default_domain, name.strip(), value.strip(), secure=True, expires=expires))
            return cookies
        if any(ch.isspace() for ch in text):
            raise InvalidRequest("Không nhận dạng được định dạng cookie.")
        return [Cookie(default_domain, _LOGIN_COOKIE, text, secure=True, expires=expires)]

    @staticmethod
    def _parse_netscape(text: str) -> List[Cookie]:
        cookies = []
        for line in text.splitlines():
            line = line.strip("\r\n")
            if line.startswith("#HttpOnly_"):
                line = line[len("#HttpOnly_"):]
            elif not line.strip() or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) < 7:
                continue
            domain, _flag, path, secure, expires, name, value = fields[:7]
            cookies.append(Cookie(
                domain=domain.strip(), name=name.strip(), value=value.strip(), path=path.strip() or "/",
                secure=secure.strip().upper() == "TRUE", expires=_to_int(expires),
            ))
        return cookies

    @staticmethod
    def _parse_json(text: str) -> List[Cookie]:
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise InvalidRequest("Nội dung JSON cookie không hợp lệ.") from exc
        if isinstance(data, dict):
            data = data.get("cookies", [])
        cookies = []
        for item in data if isinstance(data, list) else []:
            if not isinstance(item, dict) or not item.get("name") or not item.get("domain"):
                continue
            cookies.append(Cookie(
                domain=str(item["domain"]).strip(), name=str(item["name"]).strip(),
                value=str(item.get("value", "")).strip(), path=str(item.get("path") or "/"),
                secure=bool(item.get("secure")),
                expires=_to_int(item.get("expirationDate") or item.get("expires") or 0),
            ))
        return cookies

    # ── Kiểm tra ──────────────────────────────────────────────────────────────
    @staticmethod
    def _is_bilibili_domain(domain: str) -> bool:
        host = domain.lstrip(".").lower()
        return any(host == d or host.endswith("." + d) for d in _ALLOWED_DOMAINS)

    @staticmethod
    def _is_clean(cookie: Cookie) -> bool:
        joined = cookie.domain + cookie.path + cookie.name + cookie.value
        return bool(cookie.name) and not any(ch in joined for ch in "\t\r\n")

    @staticmethod
    def _site_of(domain: str) -> str:
        host = domain.lstrip(".").lower()
        return next((d for d in _ALLOWED_DOMAINS if host == d or host.endswith("." + d)), host)


def _to_int(value: Any) -> int:
    try:
        return max(int(float(value)), 0)
    except (TypeError, ValueError):
        return 0
