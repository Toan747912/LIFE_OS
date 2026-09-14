# fix_vi_sub.ps1
# Tự động vá VI-Sub extension:
#   1. Ưu tiên chọn track tiếng Anh (en) thay vì track đầu tiên
#   2. Bỏ opacity:0 mặc định trên overlay (nếu có)
# Chạy: PowerShell -ExecutionPolicy Bypass -File fix_vi_sub.ps1

$Targets = @()

# 1. Tìm trong thư mục dự án hiện tại (yt-subtitle-extension)
$LocalContentJs = Join-Path $PSScriptRoot "yt-subtitle-extension\content.js"
if (Test-Path $LocalContentJs) {
    $Targets += $LocalContentJs
}

# 2. Tìm trong Chrome WebStore extensions (nếu có)
$ExtId  = "npjplkkfbobjcjmgfjcekdihkogjlhca"
$ExtDir = "$env:LOCALAPPDATA\Google\Chrome\User Data\Default\Extensions\$ExtId"
if (Test-Path $ExtDir) {
    $VerDir = Get-ChildItem $ExtDir -Directory | Sort-Object Name -Descending | Select-Object -First 1
    if ($VerDir) {
        $ChromeContentJs = Join-Path $VerDir.FullName "content.js"
        if (Test-Path $ChromeContentJs) {
            $Targets += $ChromeContentJs
        }
    }
}

if ($Targets.Count -eq 0) {
    Write-Error "Không tìm thấy file content.js của VI-Sub!"
    exit 1
}

foreach ($ContentJs in $Targets) {
    Write-Host "========================================"
    Write-Host "Đang xử lý: $ContentJs"

    # Đọc nội dung file
    $code = Get-Content $ContentJs -Raw -Encoding UTF8

    # ---- Patch 1: Ưu tiên track English ----
    $old1 = 'tracks.find(t => t.kind === "subtitles" || t.kind === "captions")'
    $new1 = '(tracks.find(t => (t.kind === "subtitles" || t.kind === "captions") && (t.language === "en" || t.language?.startsWith("en"))) || tracks.find(t => t.kind === "subtitles" || t.kind === "captions"))'

    if ($code.Contains($old1)) {
        $code = $code.Replace($old1, $new1)
        Write-Host "[OK] Patch 1: Track selection -> Ưu tiên English"
    } else {
        Write-Host "[SKIP] Patch 1: Không tìm thấy đoạn code cũ (đã được vá trước đó hoặc đã được cập nhật)"
    }

    # ---- Patch 2: Bỏ opacity:0 trên overlay (nếu có) ----
    $old2 = "opacity:'0'"
    $new2 = "opacity:'1'"
    if ($code.Contains($old2)) {
        $code = $code.Replace($old2, $new2)
        Write-Host "[OK] Patch 2: Overlay opacity 0 -> 1"
    } else {
        $old2b = 'opacity: "0"'
        $new2b = 'opacity: "1"'
        if ($code.Contains($old2b)) {
            $code = $code.Replace($old2b, $new2b)
            Write-Host "[OK] Patch 2b: Overlay opacity 0 -> 1"
        } else {
            Write-Host "[SKIP] Patch 2: Không tìm thấy opacity:0 (không cần thiết)"
        }
    }

    # Backup rồi ghi lại
    Copy-Item $ContentJs "$ContentJs.bak" -Force
    Set-Content $ContentJs $code -Encoding UTF8 -NoNewline
    Write-Host "[XONG] Ghi nhận thay đổi vào: $ContentJs"
}

Write-Host ""
Write-Host "=== HOÀN TẤT ==="
Write-Host "Bước tiếp theo:"
Write-Host "  1. Mở Chrome -> chrome://extensions"
Write-Host "  2. Bật 'Developer mode' (Chế độ dành cho nhà phát triển)"
Write-Host "  3. Bấm 'Reload' (Tải lại) trên VI-Sub Extension"
Write-Host "  4. Mở video (YouTube, Coursera, v.v.), bấm nút VI để dịch"
