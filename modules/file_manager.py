import os
import shutil

UPLOAD_DIR = "core/input"

def ensure_upload_dir():
    """Kiểm tra và tạo thư mục core/input/ nếu chưa có."""
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR, exist_ok=True)

def get_unique_filename(filename: str) -> str:
    """
    Tách extension, kiểm tra nếu file đã tồn tại trên ổ cứng
    thì tự động thêm hậu tố _1, _2...
    """
    ensure_upload_dir()
    safe_name = os.path.basename(filename)
    base, ext = os.path.splitext(safe_name)
    counter = 1
    new_filename = safe_name
    while os.path.exists(os.path.join(UPLOAD_DIR, new_filename)):
        new_filename = f"{base}_{counter}{ext}"
        counter += 1
    return new_filename

def list_files():
    """
    Trả về danh sách mảng JSON chứa: name (tên file) và size_mb (dung lượng làm tròn 2 chữ số thập phân).
    """
    ensure_upload_dir()
    files = []
    for f in os.listdir(UPLOAD_DIR):
        path = os.path.join(UPLOAD_DIR, f)
        if os.path.isfile(path):
            size_mb = round(os.path.getsize(path) / (1024 * 1024), 2)
            files.append({
                "name": f,
                "size_mb": size_mb
            })
    return files

def rename_file(old_name: str, new_name: str):
    """
    Kiểm tra old_name có tồn tại không.
    Kiểm tra new_name đã bị trùng chưa (nếu trùng trả về false).
    Dùng os.rename để cập nhật.
    """
    ensure_upload_dir()
    safe_old = os.path.basename(old_name)
    safe_new = os.path.basename(new_name)
    
    old_path = os.path.join(UPLOAD_DIR, safe_old)
    new_path = os.path.join(UPLOAD_DIR, safe_new)
    
    if not os.path.exists(old_path):
        return {"success": False, "message": "File gốc không tồn tại!"}
    
    if os.path.exists(new_path):
        return {"success": False, "message": "Tên file mới bị trùng, vui lòng chọn tên khác!"}
    
    os.rename(old_path, new_path)
    return {"success": True, "message": "Đổi tên file thành công!"}

def delete_file_from_disk(filename: str):
    """
    Kiểm tra file tồn tại và gọi os.remove() để xóa vật lý.
    """
    ensure_upload_dir()
    safe_name = os.path.basename(filename)
    path = os.path.join(UPLOAD_DIR, safe_name)
    
    if os.path.exists(path):
        os.remove(path)
        return {"success": True, "message": f"Đã xóa vĩnh viễn file {safe_name} khỏi máy!"}
    return {"success": False, "message": "Không tìm thấy file để xóa!"}