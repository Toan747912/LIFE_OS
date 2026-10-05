"""Phát file video có hỗ trợ tua (HTTP Range), không phụ thuộc phiên bản Starlette."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, Optional

from fastapi.responses import Response, StreamingResponse

_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
_CHUNK = 1024 * 1024


def _read(path: Path, start: int, length: int) -> Iterator[bytes]:
    """Mở file cho từng khối rồi đóng ngay. Trình duyệt hay giữ kết nối video rất lâu (khi tạm dừng),
    nếu giữ file mở suốt thời gian đó thì trên Windows không thể chuyển hay xóa file."""
    position, remaining = start, length
    while remaining > 0:
        try:
            with open(path, "rb") as handle:
                handle.seek(position)
                chunk = handle.read(min(_CHUNK, remaining))
        except OSError:
            return          # file đã được chuyển đi hoặc xóa trong lúc đang phát
        if not chunk:
            return
        position += len(chunk)
        remaining -= len(chunk)
        yield chunk


def range_response(path: Path, range_header: Optional[str], media_type: str) -> Response:
    size = path.stat().st_size
    headers = {"Accept-Ranges": "bytes"}
    match = _RANGE.match((range_header or "").strip())
    if not match or not (match.group(1) or match.group(2)):
        headers["Content-Length"] = str(size)
        return StreamingResponse(_read(path, 0, size), media_type=media_type, headers=headers)

    first, last = match.group(1), match.group(2)
    if first:
        start = int(first)
        end = min(int(last), size - 1) if last else size - 1
    else:                                   # dạng "bytes=-N": N byte cuối
        start = max(size - int(last), 0)
        end = size - 1
    if start >= size or start > end:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    length = end - start + 1
    headers.update({"Content-Range": f"bytes {start}-{end}/{size}", "Content-Length": str(length)})
    return StreamingResponse(_read(path, start, length), status_code=206, media_type=media_type, headers=headers)
