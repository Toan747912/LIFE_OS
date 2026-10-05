"""Chuẩn hóa chuỗi cho tìm kiếm và đặt tên."""
from __future__ import annotations

import unicodedata


def fold(text: str) -> str:
    """Bỏ dấu và hoa thường để tìm "lop hoc" ra "Lớp học"."""
    decomposed = unicodedata.normalize("NFD", (text or "").casefold().replace("đ", "d"))
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def clean_name(text: str, max_length: int) -> str:
    """Gộp khoảng trắng, bỏ ký tự điều khiển, cắt độ dài."""
    cleaned = " ".join("".join(ch for ch in (text or "") if unicodedata.category(ch)[0] != "C" or ch == " ").split())
    return cleaned[:max_length].strip()
