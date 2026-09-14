import tkinter as tk
from tkinter import messagebox

def open_volume_controller(on_submit_callback):
    """Mở bảng điều khiển thanh trượt và đảm bảo ép hiển thị cửa sổ đồ họa"""
    root = tk.Tk()
    root.title("Tùy chỉnh Âm lượng Lồng tiếng - Live OS")
    root.geometry("420x260")
    root.resizable(False, False)

    # Ép cửa sổ hiện nổi lên trên màn hình
    root.attributes('-topmost', True)
    root.lift()
    root.focus_force()

    tk.Label(root, text="ĐIỀU CHỈNH ÂM LƯỢNG LỒNG TIẾNG", font=("Arial", 11, "bold"), fg="#2196F3").pack(pady=10)

    tk.Label(root, text="Âm lượng Video Gốc (Nền nhỏ):").pack(anchor="w", padx=30)
    orig_slider = tk.Scale(root, from_=0.0, to=1.0, resolution=0.05, orient=tk.HORIZONTAL, length=360)
    orig_slider.set(0.15)
    orig_slider.pack(padx=30)

    tk.Label(root, text="Âm lượng Tiếng Việt (To rõ):").pack(anchor="w", padx=30, pady=(10, 0))
    dub_slider = tk.Scale(root, from_=0.5, to=3.0, resolution=0.1, orient=tk.HORIZONTAL, length=360)
    dub_slider.set(1.0)
    dub_slider.pack(padx=30)

    def on_confirm():
        orig_val = orig_slider.get()
        dub_val = dub_slider.get()
        root.destroy()
        try:
            on_submit_callback(orig_val, dub_val)
            messagebox.showinfo("Thành công", "Đã xuất video hoàn tất!")
        except Exception as e:
            messagebox.showerror("Lỗi FFmpeg", f"Đã xảy ra lỗi khi trộn video:\n{e}")

    tk.Button(root, text="Xác nhận & Xuất Video", bg="#4CAF50", fg="white", font=("Arial", 10, "bold"), command=on_confirm).pack(pady=15)

    root.mainloop()