/**
 * VI Subtitle Extension — sites/phim.js
 *
 * PhimAdapter: adapter riêng cho phim.nguonc.com
 *
 * Yêu cầu: core.js phải được load trước.
 *
 * TODO: Inspect trang phim.nguonc.com → F12 → Elements
 *       Tìm element chứa phụ đề → điền selector vào SUBTITLE_SELECTOR
 */

// ── Cấu hình riêng cho phim.nguonc.com ──────────────────────────
const PHIM_CONFIG = {
  // TODO: thay bằng selector thật sau khi inspect trang
  // Ví dụ: ".subtitle", ".sub-text", "[class*='subtitle']"
  SUBTITLE_SELECTOR: null,

  // Ngôn ngữ gốc của phim (để log, sau này có thể dùng nếu API hỗ trợ)
  SOURCE_LANG: "zh",  // Phim Trung Quốc → tiếng Anh/Việt

  DEBOUNCE_MS: 300,
};


// ── PhimAdapter ──────────────────────────────────────────────────
class PhimAdapter extends SubtitleAdapter {

  constructor() {
    super();
    this._subtitleObserver = null;
  }

  /**
   * detect(): tìm subtitle element trên phim.nguonc.com
   * Trả về true nếu đã attach MutationObserver thành công.
   */
  async detect() {
    const video = document.querySelector("video");
    if (!video) {
      console.log("[VI-Sub/Phim] Chưa thấy video element");
      return false;
    }

    // ── Bước 1: thử selector đã cấu hình ─────────────────────
    if (PHIM_CONFIG.SUBTITLE_SELECTOR) {
      const el = document.querySelector(PHIM_CONFIG.SUBTITLE_SELECTOR);
      if (el) {
        console.log("[VI-Sub/Phim] Subtitle element found:", PHIM_CONFIG.SUBTITLE_SELECTOR);
        this._attachObserver(video, el);
        return true;
      }
    }

    // ── Bước 2: thử auto-detect (tìm element thay đổi gần video) ─
    const found = this._autoDetect(video);
    if (found) return true;

    console.log("[VI-Sub/Phim] Chưa tìm được subtitle. Cần thêm selector vào PHIM_CONFIG.");
    return false;
  }

  /**
   * Tự động tìm element subtitle gần video nhất.
   * Tìm element có text ngắn, thay đổi thường xuyên gần player.
   */
  _autoDetect(video) {
    // Tìm các element candidate gần video
    const vr = video.getBoundingClientRect();
    const candidates = [];

    document.querySelectorAll("div, span, p").forEach(el => {
      if (el.id === "vi-sub-overlay" || el.id === "vi-sub-widget") return;
      const text = el.innerText?.trim();
      if (!text || text.length < 3 || text.length > 300) return;
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) return;

      // Trong vùng ±300px xung quanh video
      const nearVideo = (
        r.top >= vr.top - 300 && r.bottom <= vr.bottom + 300 &&
        r.left >= vr.left - 100 && r.right <= vr.right + 100
      );
      if (nearVideo) candidates.push(el);
    });

    if (!candidates.length) return false;

    // Dùng element gần giữa-dưới video nhất (subtitle thường ở đó)
    const center = { x: vr.left + vr.width / 2, y: vr.bottom };
    candidates.sort((a, b) => {
      const ar = a.getBoundingClientRect(), br = b.getBoundingClientRect();
      const da = Math.hypot(ar.left + ar.width/2 - center.x, ar.top - center.y);
      const db = Math.hypot(br.left + br.width/2 - center.x, br.top - center.y);
      return da - db;
    });

    const el = candidates[0];
    console.log("[VI-Sub/Phim] Auto-detect candidate:", el);
    this._attachObserver(video, el);
    return true;
  }

  /** Gắn MutationObserver lên subtitle element */
  _attachObserver(video, el) {
    if (this._subtitleObserver) {
      this._subtitleObserver.disconnect();
      this._subtitleObserver = null;
    }

    UI.createOverlay(video);
    UI.setLabel("🔊 VI • BẬT");

    let lastText = "", debounce = null;
    this._subtitleObserver = new MutationObserver(() => {
      clearTimeout(debounce);
      debounce = setTimeout(async () => {
        const text = el.innerText?.trim();
        if (!text || text === lastText) return;
        lastText = text;

        const vid = document.querySelector('video');
        if (vid && vid.paused) return;

        try {
          const vi = await translate(text);
          if (vi && this._isEnabled) {
            UI.showSub(vi, text);
            TTSEngine.speak(vi);
          }
        } catch (e) {
          console.warn("[VI-Sub/Phim] Translate error:", e.message);
        }
      }, PHIM_CONFIG.DEBOUNCE_MS);
    });

    this._subtitleObserver.observe(el, {
      childList: true, subtree: true, characterData: true,
    });

    console.log("[VI-Sub/Phim] Observer attached to:", el);
  }

  /** Dọn observer khi stop */
  _stopAll() {
    if (this._subtitleObserver) {
      this._subtitleObserver.disconnect();
      this._subtitleObserver = null;
    }
    super._stopAll();
  }
}


// ── Auto-init ────────────────────────────────────────────────────
const _phimAdapter = new PhimAdapter();
_phimAdapter.init();

console.log("[VI-Sub] sites/phim.js loaded | url:", location.hostname);
