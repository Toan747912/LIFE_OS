import os
import subprocess

def mix_audio_to_video(video_path, audio_map, output_video_path):
    """Trộn tất cả 139 câu vào video bằng cú pháp amix gọn gàng và an toàn tuyệt đối"""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Không tìm thấy video tại: {video_path}")

    input_args = ["-i", video_path]
    filter_complex_parts = []
    
    for i, item in enumerate(audio_map):
        input_args.extend(["-i", item["audio_path"]])
        start_ms = int(item["start"].total_seconds() * 1000)
        # Gắn độ trễ thời gian và tăng âm lượng rõ ràng cho từng file audio lẻ
        filter_complex_parts.append(f"[{i+1}:a]volume=4.0,adelay={start_ms}|{start_ms}[a{i}]")

    # Gom toàn bộ các luồng [a0], [a1], ... vào lệnh amix chung
    mix_inputs = "".join([f"[a{i}]" for i in range(len(audio_map))])
    
    # Ép normalize=0 để không bị bóp nghẹt âm lượng tổng
    filter_complex_parts.append(f"{mix_inputs}amix=inputs={len(audio_map)}:duration=longest:normalize=0[outa]")

    filter_complex_str = ";".join(filter_complex_parts)

    cmd = [
        "ffmpeg",
        "-y",
        *input_args,
        "-filter_complex", filter_complex_str,
        "-map", "0:v:0",      # Giữ nguyên video gốc không render lại hình
        "-map", "[outa]",     # Luồng âm thanh đã đồng bộ đầy đủ từ đầu đến cuối
        "-c:v", "copy",       
        "-c:a", "aac",        
        "-b:a", "192k",       
        output_video_path
    ]

    print("Đang tiến hành trộn âm thanh hoàn chỉnh vào video...")
    subprocess.run(cmd, check=True)
    print(f"Xuất video hoàn tất tại: {output_video_path}")
