# fix_vi_sub_v2.ps1
# Kích hoạt Backend TTS (gTTS) thay vì Web Speech API của Windows
# Chạy: PowerShell -ExecutionPolicy Bypass -File fix_vi_sub_v2.ps1

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ContentJs = Join-Path $ScriptDir "yt-subtitle-extension\content.js"

if (-not (Test-Path $ContentJs)) {
    Write-Error "Khong tim thay: $ContentJs"
    Write-Error "Hay chay script nay tu thu muc LIFE_OS"
    exit 1
}

Write-Host "Dang va: $ContentJs"

$code = Get-Content $ContentJs -Raw -Encoding UTF8

# ──────────────────────────────────────────────────────────────
# Patch 1: Bat flag USE_BACKEND_TTS len true
# ──────────────────────────────────────────────────────────────
$old1 = 'USE_BACKEND_TTS:    false'
$new1 = 'USE_BACKEND_TTS:    true '

if ($code.Contains($old1)) {
    $code = $code.Replace($old1, $new1)
    Write-Host "[OK] Patch 1: USE_BACKEND_TTS false -> true"
} else {
    if ($code.Contains('USE_BACKEND_TTS:    true')) {
        Write-Host "[SKIP] Patch 1: Da la true roi, bo qua"
    } else {
        Write-Host "[WARN] Patch 1: Khong tim thay USE_BACKEND_TTS"
    }
}

# ──────────────────────────────────────────────────────────────
# Patch 2: Them nhanh Backend TTS vao ham speak()
# Tim dong log trong speak(), chen them code backend truoc speechSynthesis.cancel()
# ──────────────────────────────────────────────────────────────

# Doan nay xuat hien duy nhat trong ham speak()
$old2 = @'
    console.log(`[VI-Sub] Đang thử phát âm thanh: "${text}"`);
    window.speechSynthesis.cancel();
'@

$new2 = @'
    console.log(`[VI-Sub] Đang thử phát âm thanh: "${text}"`);
    if (CONFIG.USE_BACKEND_TTS) {
      window.speechSynthesis.cancel();
      const _ttsUrl = CONFIG.API_TTS + '?text=' + encodeURIComponent(text);
      const _ttsAudio = new Audio(_ttsUrl);
      AudioDucker.duck();
      _ttsAudio.onended = () => AudioDucker.unduck();
      _ttsAudio.onerror = () => { AudioDucker.unduck(); console.warn('[VI-Sub TTS] server error'); };
      _ttsAudio.play().catch(e => { AudioDucker.unduck(); console.warn('[VI-Sub TTS] play error:', e); });
      return;
    }
    window.speechSynthesis.cancel();
'@

if ($code.Contains($old2)) {
    $code = $code.Replace($old2, $new2)
    Write-Host "[OK] Patch 2: Them nhanh Backend TTS vao speak()"
} else {
    Write-Host "[SKIP] Patch 2: Khong tim thay doan speak() (co the da duoc va)"
}

# ──────────────────────────────────────────────────────────────
# Backup va ghi file
# ──────────────────────────────────────────────────────────────
Copy-Item $ContentJs "$ContentJs.bak2" -Force
Set-Content $ContentJs $code -Encoding UTF8 -NoNewline

Write-Host ""
Write-Host "=== XONG! ==="
Write-Host "Backup luu tai: $ContentJs.bak2"
Write-Host ""
Write-Host "Buoc tiep theo:"
Write-Host "  1. Ctrl+C server cu, roi chay:"
Write-Host "       pip install gTTS"
Write-Host "       python vi_sub_server.py"
Write-Host "  2. Vao Chrome -> chrome://extensions -> Reload extension VI-Sub"
Write-Host "  3. Vao Coursera, bat VI, thu nghe"
