import sys
import os

# Thêm thư mục hiện tại vào đường dẫn tìm kiếm module của Python
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


from modules.video_dubbing.main import main as run_video_dubbing

def show_menu():
    """Hiển thị giao diện menu chính của Live OS"""
    print("\n" + "="*30)
    print("      CHÀO MỪNG ĐẾN VỚI LIVE OS")
    print("="*30)
    print("1. Ứng dụng Lồng tiếng Song ngữ Video")
    print("0. Thoát hệ thống")
    print("="*30)

def main():
    """Vòng lặp điều phối chính của toàn hệ thống"""
    while True:
        show_menu()
        choice = input("Nhập lựa chọn của bạn: ").strip()
        
        if choice == "1":
            print("\n--- Đang khởi động: Lồng tiếng Video ---")
            try:
                run_video_dubbing()
            except Exception as e:
                print(f"[Lỗi hệ thống]: Đã xảy ra sự cố trong module lồng tiếng: {e}")
        elif choice == "0":
            print("Đang tắt Live OS. Hẹn gặp lại bạn!")
            break
        else:
            print("Lựa chọn không hợp lệ! Vui lòng nhập lại số trên menu.")

if __name__ == "__main__":
    main()
