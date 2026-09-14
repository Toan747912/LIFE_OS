/**
 * VI Subtitle Translator & TTS — v3.1
 *
 * Fixes v3.1:
 *   - EN subtitle (gốc) được highlight word-by-word, VI là phụ bên dưới
 *   - Backend TTS điều chỉnh playbackRate để khớp với cue duration
 *   - Pause video → dừng hẳn audio + hủy pending timeouts; Resume → tiếp tục đúng cách
 *   - Settings panel có toggle Hiện phụ đề VI + Hiện phụ đề gốc (default ON)
 */

// ══════════════════════════════════════════════════════════════════
// CONFIG — chỉnh tất cả tham số ở đây
// ══════════════════════════════════════════════════════════════════
const CONFIG = {
  API_TRANSLATE:      "http://127.0.0.1:8000/api/translate",
  API_TTS:            "http://127.0.0.1:8000/api/tts",
  USE_BACKEND_TTS:    true,

  CACHE_MAX:          500,
  CACHE_TTL_MS:       3_600_000,

  PREFETCH_BATCH:     5,
  PREFETCH_DELAY_MS:  250,

  LOOKAHEAD_SEC:      1.5,
  TTS_EARLY_MS:       180,
  DEBOUNCE_MS:        300,

  DUCK_VOLUME:        0.30,
  DUCK_FADE_IN_S:     0.20,
  DUCK_FADE_OUT_S:    0.50,

  TTS_CHARS_PER_SEC:  3.5,
  TTS_RATE_MIN:       0.75,
  TTS_RATE_MAX:       1.90,
};

// Âm lượng có thể thay đổi live qua panel
const VOL = { tts: 1.0, vid: 1.0 };

// ══════════════════════════════════════════════════════════════════
// SETTINGS — người dùng có thể toggle trong panel cài đặt
// ══════════════════════════════════════════════════════════════════
const SETTINGS = {
  showSubtitleVI:  true,   // Hiện phụ đề tiếng Việt (bản dịch)
  showSubtitleOrig: true,  // Hiện phụ đề gốc (EN) — nổi bật, có word highlight
};


// ══════════════════════════════════════════════════════════════════
// CACHE — LRU với TTL
// ══════════════════════════════════════════════════════════════════
const Cache = (() => {
  const _map = new Map();

  function get(key) {
    const entry = _map.get(key);
    if (!entry) return null;
    if (Date.now() - entry.ts > CONFIG.CACHE_TTL_MS) { _map.delete(key); return null; }
    _map.delete(key); _map.set(key, entry);
    return entry.value;
  }

  function set(key, value) {
    if (_map.has(key)) _map.delete(key);
    _map.set(key, { value, ts: Date.now() });
    if (_map.size > CONFIG.CACHE_MAX)
      _map.delete(_map.keys().next().value);
  }

  return { get, set, has: k => get(k) !== null };
})();


// ══════════════════════════════════════════════════════════════════
// TRANSLATION API
// ══════════════════════════════════════════════════════════════════
async function translate(text) {
  const clean = text.trim();
  if (!clean) return "";

  const cached = Cache.get(clean);
  if (cached !== null) return cached;

  const fd = new FormData();
  fd.append("text", clean);
  const res = await fetch(CONFIG.API_TRANSLATE, { method: "POST", body: fd });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);

  const { translation } = await res.json();
  const vi = translation || "";
  Cache.set(clean, vi);
  return vi;
}


// ══════════════════════════════════════════════════════════════════
// AUDIO DUCKER
// ══════════════════════════════════════════════════════════════════
const AudioDucker = (() => {
  let ctx = null, gainNode = null, bound = null;

  function setup(videoEl) {
    if (bound === videoEl) return true;
    try {
      ctx      = new (window.AudioContext || window.webkitAudioContext)();
      gainNode = ctx.createGain();
      gainNode.gain.value = 1.0;
      ctx.createMediaElementSource(videoEl).connect(gainNode);
      gainNode.connect(ctx.destination);
      bound = videoEl;
      return true;
    } catch (e) {
      console.warn("[VI-Sub] AudioDucker:", e.message);
      return false;
    }
  }

  function duck() {
    if (!gainNode) return;
    gainNode.gain.setTargetAtTime(CONFIG.DUCK_VOLUME, ctx.currentTime, CONFIG.DUCK_FADE_IN_S / 3);
  }

  function unduck() {
    if (!gainNode) return;
    gainNode.gain.setTargetAtTime(1.0, ctx.currentTime, CONFIG.DUCK_FADE_OUT_S / 3);
  }

  function reset() { if (gainNode) gainNode.gain.value = 1.0; }

  return { setup, duck, unduck, reset };
})();


// ══════════════════════════════════════════════════════════════════
// TTS ENGINE
// ══════════════════════════════════════════════════════════════════
const TTSEngine = (() => {
  let viVoice = null;
  const _audioCache = new Map();
  let _currentAudio = null;

  function loadVoice() {
    const vs = window.speechSynthesis.getVoices();
    viVoice = vs.find(v => v.lang === "vi-VN" && v.name.includes("HoaiMy"))
           || vs.find(v => v.lang === "vi-VN" && v.name.includes("NamMinh"))
           || vs.find(v => v.lang === "vi-VN")
           || vs.find(v => v.lang.startsWith("vi"))
           || null;
  }
  window.speechSynthesis.onvoiceschanged = loadVoice;
  loadVoice();

  function warmup() {
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(" ");
      u.volume = 0; u.lang = "vi-VN";
      if (viVoice) u.voice = viVoice;
      window.speechSynthesis.speak(u);
    } catch (_) {}
  }

  function prefetch(text) {
    if (!CONFIG.USE_BACKEND_TTS || !text || _audioCache.has(text)) return;
    const url = CONFIG.API_TTS + '?text=' + encodeURIComponent(text);
    const audio = new Audio(url);
    audio.preload = 'auto';
    _audioCache.set(text, audio);
  }

  function speak(text, durationMs = 0) {
    if (!text) return;

    if (CONFIG.USE_BACKEND_TTS) {
      window.speechSynthesis.cancel();
      if (_currentAudio && !_currentAudio.paused) {
        _currentAudio.pause();
        _currentAudio = null;
      }
      const _audio = _audioCache.get(text) || new Audio(CONFIG.API_TTS + '?text=' + encodeURIComponent(text));
      _audioCache.delete(text);
      _audio.volume = VOL.tts;

      // ── FIX: Điều chỉnh playbackRate để khớp với cue duration ──
      const applyRate = () => {
        if (durationMs > 0 && _audio.duration > 0) {
          const targetS = durationMs / 1000;
          // Tốc độ = duration_tts / duration_cue, giới hạn 0.7x – 2.0x
          const rate = _audio.duration / targetS;
          _audio.playbackRate = Math.min(2.0, Math.max(0.7, rate));
          console.log(`[VI-Sub TTS] playbackRate=${_audio.playbackRate.toFixed(2)} (audio=${_audio.duration.toFixed(2)}s, cue=${targetS.toFixed(2)}s)`);
        }
      };
      if (_audio.readyState >= 1) {
        applyRate();
      } else {
        _audio.addEventListener('loadedmetadata', applyRate, { once: true });
      }

      _audio.onended = () => { if (_currentAudio === _audio) _currentAudio = null; };
      _audio.onerror = (e) => {
        if (_currentAudio === _audio) _currentAudio = null;
        console.warn('[VI-Sub TTS] error:', e);
      };
      _currentAudio = _audio;
      _audio.play().catch(e => console.warn('[VI-Sub TTS] play blocked:', e));
      return;
    }

    // Web Speech API fallback
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = "vi-VN";
    if (viVoice) utter.voice = viVoice;
    if (durationMs > 0) {
      const naturalMs = (text.length / CONFIG.TTS_CHARS_PER_SEC) * 1000;
      const rate = naturalMs / durationMs;
      utter.rate = Math.min(CONFIG.TTS_RATE_MAX, Math.max(CONFIG.TTS_RATE_MIN, rate));
    } else {
      utter.rate = 1.0;
    }
    utter.onstart = () => AudioDucker.duck();
    utter.onend   = () => AudioDucker.unduck();
    utter.onerror = (e) => { console.error("[VI-Sub] TTS error:", e); AudioDucker.unduck(); };
    window.speechSynthesis.speak(utter);
  }

  // ── FIX: Dừng hẳn audio khi pause (không resume mid-sentence) ──
  function pauseAudio() {
    if (_currentAudio && !_currentAudio.paused) _currentAudio.pause();
    window.speechSynthesis.pause();
  }

  // Resume audio từ chỗ đang dừng khi video play tiếp
  function resumeAudio() {
    if (_currentAudio && _currentAudio.paused) {
      _currentAudio.play().catch(() => {});
    }
    window.speechSynthesis.resume();
  }

  function stop() {
    if (_currentAudio) { _currentAudio.pause(); _currentAudio = null; }
    _audioCache.clear();
    window.speechSynthesis.cancel();
    AudioDucker.unduck();
  }

  return { warmup, speak, stop, pauseAudio, resumeAudio, prefetch };
})();


// ══════════════════════════════════════════════════════════════════
// UI — Floating button + subtitle overlay + settings panel
// ══════════════════════════════════════════════════════════════════
const UI = (() => {
  let _btn = null, _overlay = null, _panel = null, _gearBtn = null;
  let _hlTimers = [];

  // ── Volume & Settings Panel ───────────────────────────────────
  function createVolumePanel() {
    if (document.getElementById("vi-vol-panel")) {
      _panel = document.getElementById("vi-vol-panel");
      return;
    }
    _panel = document.createElement("div");
    _panel.id = "vi-vol-panel";
    _panel.style.cssText = `
      position:fixed; bottom:76px; right:24px; z-index:2147483647;
      background:rgba(10,10,28,0.96); border:1.5px solid rgba(251,191,36,.55);
      border-radius:16px; padding:14px 16px;
      font-family:system-ui,sans-serif; color:#fbbf24;
      font-size:13px; width:220px;
      box-shadow:0 8px 32px rgba(0,0,0,.7),0 0 0 1px rgba(251,191,36,.08);
      display:none; user-select:none;
    `;

    _panel.innerHTML = `
      <div style="font-weight:700;margin-bottom:13px;text-align:center;
                  letter-spacing:.6px;font-size:12px;opacity:.75;text-transform:uppercase">
        ⚙ Cài đặt
      </div>

      <!-- Âm lượng video gốc -->
      <div style="margin-bottom:14px">
        <div style="display:flex;justify-content:space-between;margin-bottom:7px;font-size:12px">
          <span style="opacity:.8">🎬 Video gốc</span>
          <span id="vi-vid-val" style="font-weight:700">100%</span>
        </div>
        <input type="range" id="vi-vol-vid" min="0" max="100" value="100"
          style="width:100%;accent-color:#fbbf24;cursor:pointer;height:4px">
      </div>

      <!-- Âm lượng lồng tiếng -->
      <div style="margin-bottom:14px">
        <div style="display:flex;justify-content:space-between;margin-bottom:7px;font-size:12px">
          <span style="opacity:.8">🔊 Lồng tiếng VI</span>
          <span id="vi-tts-val" style="font-weight:700">100%</span>
        </div>
        <input type="range" id="vi-vol-tts" min="0" max="100" value="100"
          style="width:100%;accent-color:#fbbf24;cursor:pointer;height:4px">
      </div>

      <!-- Divider -->
      <div style="border-top:1px solid rgba(251,191,36,.2);margin-bottom:12px"></div>

      <!-- Toggle: Hiện phụ đề gốc (EN) -->
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <span style="font-size:12px;opacity:.8">🌐 Phụ đề gốc</span>
        <label id="vi-toggle-orig-label" style="position:relative;display:inline-block;width:36px;height:20px;cursor:pointer">
          <input type="checkbox" id="vi-show-orig" checked
            style="opacity:0;width:0;height:0;position:absolute">
          <span id="vi-slider-orig" style="
            position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;
            background:#444;border-radius:20px;transition:.3s;
          "></span>
          <span id="vi-knob-orig" style="
            position:absolute;content:'';height:14px;width:14px;left:3px;bottom:3px;
            background:#fff;border-radius:50%;transition:.3s;
            transform:translateX(0);
          "></span>
        </label>
      </div>

      <!-- Toggle: Hiện phụ đề VI -->
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span style="font-size:12px;opacity:.8">🇻🇳 Phụ đề VI</span>
        <label id="vi-toggle-vi-label" style="position:relative;display:inline-block;width:36px;height:20px;cursor:pointer">
          <input type="checkbox" id="vi-show-vi" checked
            style="opacity:0;width:0;height:0;position:absolute">
          <span id="vi-slider-vi" style="
            position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;
            background:#444;border-radius:20px;transition:.3s;
          "></span>
          <span id="vi-knob-vi" style="
            position:absolute;content:'';height:14px;width:14px;left:3px;bottom:3px;
            background:#fff;border-radius:50%;transition:.3s;
            transform:translateX(0);
          "></span>
        </label>
      </div>
    `;
    document.body.appendChild(_panel);

    // Helper toggle UI
    function updateToggleUI(sliderEl, knobEl, isOn) {
      sliderEl.style.background = isOn ? '#fbbf24' : '#444';
      knobEl.style.transform = isOn ? 'translateX(16px)' : 'translateX(0)';
      knobEl.style.background = isOn ? '#1a1a2e' : '#fff';
    }

    // Init toggle states (both ON by default)
    const sliderOrig = _panel.querySelector('#vi-slider-orig');
    const knobOrig   = _panel.querySelector('#vi-knob-orig');
    const sliderVI   = _panel.querySelector('#vi-slider-vi');
    const knobVI     = _panel.querySelector('#vi-knob-vi');
    updateToggleUI(sliderOrig, knobOrig, true);
    updateToggleUI(sliderVI,   knobVI,   true);

    // Toggle: phụ đề gốc (EN)
    _panel.querySelector('#vi-show-orig').addEventListener('change', (e) => {
      SETTINGS.showSubtitleOrig = e.target.checked;
      updateToggleUI(sliderOrig, knobOrig, e.target.checked);
    });

    // Toggle: phụ đề VI
    _panel.querySelector('#vi-show-vi').addEventListener('change', (e) => {
      SETTINGS.showSubtitleVI = e.target.checked;
      updateToggleUI(sliderVI, knobVI, e.target.checked);
    });

    // Video volume slider
    _panel.querySelector("#vi-vol-vid").addEventListener("input", (e) => {
      const pct = parseInt(e.target.value);
      VOL.vid = pct / 100;
      _panel.querySelector("#vi-vid-val").textContent = pct + "%";
      const vid = document.querySelector("video");
      if (vid) vid.volume = VOL.vid;
    });

    // TTS volume slider
    _panel.querySelector("#vi-vol-tts").addEventListener("input", (e) => {
      const pct = parseInt(e.target.value);
      VOL.tts = pct / 100;
      _panel.querySelector("#vi-tts-val").textContent = pct + "%";
    });
  }

  function createButton(onToggle) {
    if (document.getElementById("vi-sub-widget")) return;

    const widget = document.createElement("div");
    widget.id = "vi-sub-widget";
    widget.style.cssText = `
      position:fixed; bottom:24px; right:24px; z-index:2147483647;
      display:flex; align-items:stretch;
      background:rgba(10,10,28,0.88); border:1.5px solid rgba(251,191,36,.65);
      border-radius:50px; overflow:hidden;
      box-shadow:0 4px 20px rgba(0,0,0,.65);
      font-family:system-ui,sans-serif; user-select:none;
    `;

    _gearBtn = document.createElement("button");
    _gearBtn.id = "vi-gear-btn";
    _gearBtn.title = "Cài đặt";
    _gearBtn.style.cssText = `
      background:transparent; color:rgba(251,191,36,.6); border:none;
      border-right:1px solid rgba(251,191,36,.2);
      padding:9px 13px; font-size:14px; cursor:pointer;
      transition:background .15s,color .15s; line-height:1; flex-shrink:0;
    `;
    _gearBtn.textContent = "⚙";
    _gearBtn.addEventListener("mouseenter", () => {
      _gearBtn.style.background = "rgba(251,191,36,.1)";
      _gearBtn.style.color = "#fbbf24";
    });
    _gearBtn.addEventListener("mouseleave", () => {
      const panelOpen = _panel && _panel.style.display !== "none";
      _gearBtn.style.background = panelOpen ? "rgba(251,191,36,.15)" : "transparent";
      _gearBtn.style.color = panelOpen ? "#fbbf24" : "rgba(251,191,36,.6)";
    });
    _gearBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!_panel) return;
      const showing = _panel.style.display !== "none";
      _panel.style.display = showing ? "none" : "block";
      _gearBtn.style.background = showing ? "transparent" : "rgba(251,191,36,.15)";
      _gearBtn.style.color      = showing ? "rgba(251,191,36,.6)" : "#fbbf24";
    });

    _btn = document.createElement("button");
    _btn.id    = "vi-sub-btn";
    _btn.title = "Bật/tắt phụ đề tiếng Việt";
    _btn.style.cssText = `
      background:transparent; color:#fbbf24; border:none;
      padding:9px 18px 9px 14px; font-size:13px; font-weight:700; cursor:pointer;
      transition:background .15s,color .15s; white-space:nowrap;
      line-height:1; letter-spacing:.4px;
    `;
    _btn.textContent = "🔊 VI";
    _btn.addEventListener("mouseenter", () => {
      if (!_btn._active) _btn.style.background = "rgba(251,191,36,.08)";
    });
    _btn.addEventListener("mouseleave", () => {
      if (!_btn._active) _btn.style.background = "transparent";
    });
    _btn.addEventListener("click", onToggle);

    widget.appendChild(_gearBtn);
    widget.appendChild(_btn);
    document.body.appendChild(widget);
    createVolumePanel();
  }

  function setActive(active) {
    if (!_btn) return;
    _btn._active = active;
    const widget = document.getElementById("vi-sub-widget");
    if (active) {
      _btn.style.background = "#fbbf24";
      _btn.style.color      = "#1a1a2e";
      if (widget) widget.style.boxShadow = "0 4px 20px rgba(0,0,0,.65),0 0 14px rgba(251,191,36,.3)";
    } else {
      _btn.style.background = "transparent";
      _btn.style.color      = "#fbbf24";
      if (widget) widget.style.boxShadow = "0 4px 20px rgba(0,0,0,.65)";
      if (_panel) _panel.style.display = "none";
      if (_gearBtn) {
        _gearBtn.style.background = "transparent";
        _gearBtn.style.color = "rgba(251,191,36,.6)";
      }
    }
  }

  function setLabel(text) { if (_btn) _btn.textContent = text; }

  function createOverlay(videoEl) {
    const existing = document.getElementById("vi-sub-overlay");
    if (existing) { _overlay = existing; return; }

    _overlay = document.createElement("div");
    _overlay.id = "vi-sub-overlay";
    _overlay.style.cssText = `
      display:none; position:absolute; bottom:12%; left:50%;
      transform:translateX(-50%); z-index:99999; pointer-events:none;
      width:84%; text-align:center;
      font-family:system-ui,sans-serif;
      transition:opacity .15s ease;
    `;
    const wrapper = videoEl.parentElement || document.body;
    if (wrapper !== document.body) wrapper.style.position ||= "relative";
    wrapper.appendChild(_overlay);
  }

  /**
   * ── FIX: EN (gốc) nổi bật + word highlight; VI là phụ bên dưới ──
   * @param {string} viText    — bản dịch tiếng Việt
   * @param {string} enText    — phụ đề gốc (EN) — highlight word-by-word
   * @param {number} durationMs
   */
  function showSub(viText, enText = '', durationMs = 0) {
    if (!_overlay) return;

    // Nếu cả hai đều tắt → ẩn overlay
    if (!SETTINGS.showSubtitleOrig && !SETTINGS.showSubtitleVI) {
      hideSub();
      return;
    }

    _hlTimers.forEach(t => clearTimeout(t));
    _hlTimers = [];

    let html = '';

    // ── Phụ đề GỐCGỐC (EN) — to, sáng, word-by-word highlight ──
    if (enText && SETTINGS.showSubtitleOrig) {
      const words = enText.split(' ');
      const wordSpans = words
        .map((w, i) => `<span id="vi-en-w${i}" style="
          color:#ffffff;
          text-shadow:0 0 5px #000,0 0 5px #000;
          font-weight:600;
          transition:color .1s,text-shadow .1s;
        ">${w}</span>`)
        .join(' ');

      html += `<div id="vi-en-row" style="
        font-size:1.12em;
        line-height:1.4;
        margin-bottom:${SETTINGS.showSubtitleVI && viText ? '6px' : '0'};
        letter-spacing:.01em;
      ">${wordSpans}</div>`;

      // Word highlight theo thứ tự
      if (durationMs > 0 && words.length > 0) {
        const msPerWord = durationMs / words.length;
        words.forEach((_, i) => {
          const t = setTimeout(() => {
            // Bỏ highlight từ trước
            if (i > 0) {
              const prev = _overlay.querySelector(`#vi-en-w${i - 1}`);
              if (prev) {
                prev.style.color      = '#ccc';
                prev.style.textShadow = '0 0 4px #000';
                prev.style.fontWeight = '500';
              }
            }
            // Highlight từ hiện tại — màu vàng gold nổi bật
            const curr = _overlay.querySelector(`#vi-en-w${i}`);
            if (curr) {
              curr.style.color      = '#fbbf24';
              curr.style.textShadow = '0 0 12px #fbbf24, 0 0 6px #fbbf24, 0 0 4px #000';
              curr.style.fontWeight = '800';
            }
          }, i * msPerWord);
          _hlTimers.push(t);
        });
      }
    }

    // ── Phụ đề VI (bản dịch) — nhỏ hơn, phía dưới ──
    if (viText && SETTINGS.showSubtitleVI) {
      html += `<div style="
        font-size:.86em;
        color:#fde68a;
        text-shadow:0 0 5px #000,0 0 5px #000;
        font-weight:500;
        opacity:.92;
        line-height:1.4;
      ">${viText}</div>`;
    }

    // Nếu không có EN (chỉ có VI) thì VI hiển thị to hơn như trước
    if ((!enText || !SETTINGS.showSubtitleOrig) && viText && SETTINGS.showSubtitleVI) {
      html = `<div style="
        font-size:1.1em;
        color:#fbbf24;
        text-shadow:0 0 5px #000,0 0 5px #000;
        font-weight:600;
        line-height:1.4;
      ">${viText}</div>`;
    }

    _overlay.innerHTML = html;
    _overlay.style.display = "block";
    _overlay.style.opacity = "1";
  }

  // ── FIX: Hủy word highlight timers (dùng khi pause) ──
  function clearHighlightTimers() {
    _hlTimers.forEach(t => clearTimeout(t));
    _hlTimers = [];
  }

  function hideSub() {
    if (!_overlay) return;
    _hlTimers.forEach(t => clearTimeout(t));
    _hlTimers = [];
    _overlay.style.opacity = "0";
    setTimeout(() => { if (_overlay) _overlay.style.display = "none"; }, 160);
  }

  function destroyOverlay() {
    const el = document.getElementById("vi-sub-overlay");
    if (el) el.remove();
    _overlay = null;
  }

  return { createButton, setActive, setLabel, createOverlay, showSub, hideSub, destroyOverlay, createVolumePanel, clearHighlightTimers };
})();


// ══════════════════════════════════════════════════════════════════
// PRE-FETCHER
// ══════════════════════════════════════════════════════════════════
const PreFetcher = (() => {
  let _active = false;

  async function run(cues) {
    _active = true;
    console.log(`[VI-Sub] Pre-fetching ${cues.length} cues in background...`);

    for (let i = 0; i < cues.length; i += CONFIG.PREFETCH_BATCH) {
      if (!_active) break;

      const batch = cues.slice(i, i + CONFIG.PREFETCH_BATCH);
      await Promise.allSettled(batch.map(async cue => {
        const text = cue.text.replace(/<[^>]+>/g, "").trim();
        if (!text || Cache.has(text)) return;
        try {
          const vi = await translate(text);
          if (vi) TTSEngine.prefetch(vi);
        } catch (_) {}
      }));

      const pct = Math.min(100, Math.round((i + batch.length) / cues.length * 100));
      UI.setLabel(`⏳ ${pct}%`);

      if (i + CONFIG.PREFETCH_BATCH < cues.length)
        await new Promise(r => setTimeout(r, CONFIG.PREFETCH_DELAY_MS));
    }

    if (_active) {
      console.log("[VI-Sub] Pre-fetch complete.");
      UI.setLabel("🔊 VI • BẬT");
    }
  }

  function stop() { _active = false; }

  return { run, stop };
})();


// ══════════════════════════════════════════════════════════════════
// VIDEO SYNC ENGINE
// ══════════════════════════════════════════════════════════════════
const VideoSync = (() => {
  let _cues          = [];
  let _enabled       = false;
  let _timerId       = null;
  let _lastTime      = 0;
  let _videoEl       = null;
  let _activeCueEnd  = 0;
  const _done        = new Set();

  // ── FIX: Track tất cả setTimeout đang pending để hủy khi pause ──
  const _pendingTimeouts = new Set();

  function _onVideoPause() {
    // Hủy tất cả cue đã schedule nhưng chưa kịp phát
    _pendingTimeouts.forEach(t => clearTimeout(t));
    _pendingTimeouts.clear();
    // Dừng audio ngay lập tức
    TTSEngine.pauseAudio();
    // Dừng word highlight nhưng GIỮ NGUYÊN text phụ đề (không ẩn)
    UI.clearHighlightTimers();
  }

  function _onVideoPlay() {
    // Resume audio từ chỗ đang dừng (nếu có)
    TTSEngine.resumeAudio();
    // Tick sẽ tự xử lý cue tiếp theo khi video chạy lại
  }

  function _tick() {
    if (!_enabled) return;

    const currentVideo = document.querySelector('video');
    if (!currentVideo) return;

    const currentTime = currentVideo.currentTime;

    // Seek detection
    if (Math.abs(currentTime - _lastTime) > 1.5) {
      _done.clear();
      _pendingTimeouts.forEach(t => clearTimeout(t));
      _pendingTimeouts.clear();
      _activeCueEnd = 0;
      TTSEngine.stop();
      UI.hideSub();
    }
    _lastTime = currentTime;

    // Khi video paused → không làm gì thêm, giữ nguyên subtitle đang hiển thị
    if (currentVideo.paused) return;

    // Ẩn subtitle khi cue kết thúc
    if (_activeCueEnd > 0 && currentTime >= _activeCueEnd + 0.08) {
      _activeCueEnd = 0;
      UI.hideSub();
    }

    AudioDucker.setup(currentVideo);

    if (Math.abs(currentVideo.volume - VOL.vid) > 0.01) currentVideo.volume = VOL.vid;

    const rate = currentVideo.playbackRate || 1;

    _cues.forEach((cue, idx) => {
      if (_done.has(idx)) return;
      if (cue.startTime < currentTime - 0.3) { _done.add(idx); return; }
      if (cue.startTime - currentTime > CONFIG.LOOKAHEAD_SEC * 2) return;

      if (cue.startTime - currentTime <= CONFIG.LOOKAHEAD_SEC) {
        _done.add(idx);
        const delayMs = Math.max(0, (cue.startTime - currentTime) * 1000 / rate - CONFIG.TTS_EARLY_MS);

        const tid = setTimeout(async () => {
          _pendingTimeouts.delete(tid);

          if (!_enabled) return;

          const vNow = document.querySelector('video');
          // ── FIX: Không phát khi video đang pause ──
          if (!vNow || vNow.paused) return;
          if (Math.abs(vNow.currentTime - cue.startTime) > 2.0) return;

          const text = cue.text.replace(/<[^>]+>/g, "").trim();
          if (!text) return;

          try {
            const vi = await translate(text);
            const durationMs = (cue.endTime - cue.startTime) * 1000;
            if (!vi || !_enabled) return;

            // Kiểm tra lại video không bị pause trong lúc đang fetch dịch
            const vCheck = document.querySelector('video');
            if (!vCheck || vCheck.paused) return;

            console.log(`[VI-Sub] Cue [${idx}]: "${vi}"`);
            _activeCueEnd = cue.endTime;
            UI.showSub(vi, text, durationMs);   // EN nổi bật + VI phụ
            TTSEngine.speak(vi, durationMs);
          } catch (e) {
            console.warn("[VI-Sub] cue error:", e.message);
          }
        }, delayMs);

        _pendingTimeouts.add(tid);
      }
    });
  }

  function attach(videoEl, cues) {
    detach();
    _cues    = cues;
    _enabled = true;
    _done.clear();
    _lastTime = 0;

    if (videoEl) {
      AudioDucker.setup(videoEl);
      videoEl.addEventListener('pause', _onVideoPause);
      videoEl.addEventListener('play',  _onVideoPlay);
      _videoEl = videoEl;
    }

    _timerId = setInterval(_tick, 250);
    console.log(`[VI-Sub] VideoSync attached (250ms): ${cues.length} cues`);
  }

  function detach() {
    if (_timerId) { clearInterval(_timerId); _timerId = null; }
    if (_videoEl) {
      _videoEl.removeEventListener('pause', _onVideoPause);
      _videoEl.removeEventListener('play',  _onVideoPlay);
      _videoEl = null;
    }
    _pendingTimeouts.forEach(t => clearTimeout(t));
    _pendingTimeouts.clear();
    _done.clear();
    _cues = [];
    _enabled = false;
    _activeCueEnd = 0;
    TTSEngine.stop();
  }

  return { attach, detach };
})();


// ══════════════════════════════════════════════════════════════════
// DETECTOR — 3 chiến lược tìm phụ đề
// ══════════════════════════════════════════════════════════════════
const KNOWN_SELECTORS = [
  ".ytp-caption-segment",
  ".rc-SubtitleItem", ".subtitle-item span", "[data-testid='subtitle-item']",
  ".well--text--2WPkk", "[class*='captions--captions']",
  ".subtitles li.current", ".closed-captions span",
  ".vjs-text-track-display span", ".vjs-text-track-cue span",
  "[class*='subtitle']", "[class*='caption']",
];

function waitForCues(track) {
  return new Promise(resolve => {
    track.mode = "hidden";
    if (track.cues && track.cues.length > 0) {
      return resolve(Array.from(track.cues));
    }
    track.addEventListener("load", () => resolve(Array.from(track.cues || [])), { once: true });
    setTimeout(() => resolve(Array.from(track.cues || [])), 5000);
  });
}

async function tryTrackStrategy(video) {
  const tracks = Array.from(video.textTracks || []);
  const track  = tracks.find(t => (t.kind === "subtitles" || t.kind === "captions") && (t.language === "en" || t.language?.startsWith("en")))
              || tracks.find(t => t.kind === "subtitles" || t.kind === "captions");
  if (!track) return false;

  const cues = await waitForCues(track);
  if (!cues.length) return false;

  console.log(`[VI-Sub] Strategy 1 (track): ${cues.length} cues`);
  UI.createOverlay(video);
  VideoSync.attach(video, cues);
  PreFetcher.run(cues);
  return true;
}

function tryKnownSelectors(video) {
  for (const sel of KNOWN_SELECTORS) {
    try {
      const el = document.querySelector(sel);
      if (!el || !el.innerText?.trim()) continue;

      console.log("[VI-Sub] Strategy 2 (selector):", sel);
      UI.createOverlay(video);
      UI.setLabel("🔊 VI • BẬT");

      let lastText = "", debounce = null;
      new MutationObserver(() => {
        clearTimeout(debounce);
        debounce = setTimeout(async () => {
          const text = el.innerText?.trim();
          if (!text || text === lastText) return;
          lastText = text;
          const vid = document.querySelector('video');
          if (vid && vid.paused) return;   // FIX: không dịch khi đang pause
          try {
            const vi = await translate(text);
            if (vi) { UI.showSub(vi, text); TTSEngine.speak(vi); }
          } catch (_) {}
        }, CONFIG.DEBOUNCE_MS);
      }).observe(el, { childList: true, subtree: true, characterData: true });

      return true;
    } catch (_) {}
  }
  return false;
}

let _proxInterval = null;

function startProximityScan(video) {
  console.log("[VI-Sub] Strategy 3 (proximity scan)...");
  UI.setLabel("⏳ Đang quét...");

  const changeLog = new Map();

  _proxInterval = setInterval(() => {
    const vr = video.getBoundingClientRect();
    if (vr.width < 100 || vr.height < 50) return;

    const area = {
      top: vr.top - 50, bottom: vr.bottom + 200,
      left: vr.left - 100, right: vr.right + 100,
    };

    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
    let node;
    while ((node = walker.nextNode())) {
      if (["SCRIPT","STYLE","NOSCRIPT"].includes(node.tagName)) continue;
      if (node.id === "vi-sub-overlay" || node.id === "vi-sub-widget") continue;

      const text = node.innerText?.trim();
      if (!text || text.length < 5 || text.length > 200) continue;
      if (text.split(" ").length < 2) continue;

      const r = node.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      if (r.top < area.top || r.bottom > area.bottom) continue;
      if (r.left < area.left || r.right > area.right) continue;

      const log = changeLog.get(node) || { count: 0, lastText: "", ts: 0 };
      if (text !== log.lastText) { log.count++; log.lastText = text; log.ts = Date.now(); }
      changeLog.set(node, log);

      if (log.count >= 2 && Date.now() - log.ts < 10_000) {
        clearInterval(_proxInterval); _proxInterval = null;
        console.log("[VI-Sub] Proximity locked:", node);
        UI.createOverlay(video);
        UI.setLabel("🔊 VI • BẬT");

        let lastText2 = "", debounce = null;
        new MutationObserver(() => {
          clearTimeout(debounce);
          debounce = setTimeout(async () => {
            const t = node.innerText?.trim();
            if (!t || t === lastText2) return;
            lastText2 = t;
            const vid = document.querySelector('video');
            if (vid && vid.paused) return;   // FIX
            try {
              const vi = await translate(t);
              if (vi) { UI.showSub(vi, t); TTSEngine.speak(vi); }
            } catch (_) {}
          }, CONFIG.DEBOUNCE_MS);
        }).observe(node, { childList: true, subtree: true, characterData: true });
        return;
      }
    }

    const now = Date.now();
    changeLog.forEach((v, k) => { if (now - v.ts > 15_000) changeLog.delete(k); });
  }, 1500);

  setTimeout(() => {
    if (_proxInterval) {
      clearInterval(_proxInterval); _proxInterval = null;
      UI.setLabel("🔊 Không thấy phụ đề");
      setTimeout(() => UI.setLabel("🔊 VI"), 3000);
    }
  }, 30_000);
}


// ══════════════════════════════════════════════════════════════════
// CONTROLLER
// ══════════════════════════════════════════════════════════════════
let _isEnabled  = false;
let _retryTimer = null;
let _domWatcher = null;

async function tryDetectNow() {
  const videos = Array.from(document.querySelectorAll("video"))
    .filter(v => v.readyState >= 1);

  if (!videos.length) {
    const allVideos = document.querySelectorAll("video");
    console.log(`[VI-Sub] Videos in DOM: ${allVideos.length}, ready: ${videos.length}`);
    return false;
  }

  for (const v of videos) {
    const tracks = Array.from(v.textTracks || []);
    console.log(`[VI-Sub] Video ${v.src?.slice(0,60)||"(blob)"} → tracks: ${tracks.length}`);
    tracks.forEach(t => console.log(`  track: kind=${t.kind} lang=${t.language} cues=${t.cues?.length ?? "?"}`));
    if (await tryTrackStrategy(v)) return true;
  }

  for (const v of videos) {
    if (tryKnownSelectors(v)) return true;
  }

  startProximityScan(videos[0]);
  return true;
}

async function startAll() {
  stopWatchers();

  const found = await tryDetectNow();
  if (found) return;

  UI.setLabel("⏳ Chờ video...");
  console.log("[VI-Sub] No ready video found. Watching DOM...");

  let attempts = 0;

  _retryTimer = setInterval(async () => {
    attempts++;
    if (!_isEnabled) { stopWatchers(); return; }

    console.log(`[VI-Sub] Retry ${attempts}/15...`);
    const found = await tryDetectNow();
    if (found) {
      stopWatchers();
    } else if (attempts >= 15) {
      stopWatchers();
      UI.setLabel("⏳ Chờ phụ đề...");
      console.log("[VI-Sub] No video in top frame after 30s.");
    }
  }, 2000);

  _domWatcher = new MutationObserver(async () => {
    if (!_isEnabled) return;
    const found = await tryDetectNow();
    if (found) stopWatchers();
  });
  _domWatcher.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: false,
  });
}

function stopWatchers() {
  if (_retryTimer) { clearInterval(_retryTimer); _retryTimer = null; }
  if (_domWatcher) { _domWatcher.disconnect(); _domWatcher = null; }
}

function stopAll() {
  stopWatchers();
  PreFetcher.stop();
  VideoSync.detach();
  if (_proxInterval) { clearInterval(_proxInterval); _proxInterval = null; }
  TTSEngine.stop();
  AudioDucker.reset();
  UI.hideSub();
  UI.destroyOverlay();
}


// ══════════════════════════════════════════════════════════════════
// INIT — Top frame vs Iframe
// ══════════════════════════════════════════════════════════════════
const IS_TOP_FRAME = window.self === window.top;

if (IS_TOP_FRAME) {
  const init = () => {
    UI.createButton(() => {
      _isEnabled = !_isEnabled;
      UI.setActive(_isEnabled);

      if (_isEnabled) {
        TTSEngine.warmup();
        UI.setLabel("⏳ Đang tìm...");
        startAll();
      } else {
        stopAll();
        UI.setLabel("🔊 VI");
      }
    });
  };

  if (document.body) init();
  else document.addEventListener("DOMContentLoaded", init);

  window.addEventListener("message", async e => {
    if (e.data?.type === "VI_IFRAME_STATUS") {
      console.log("[VI-Sub] 📡 iframe says:", e.data.msg);
      if (_isEnabled && e.data.msg?.includes("track locked")) {
        UI.setLabel("🔊 VI • BẬT");
      }
      return;
    }

    if (!_isEnabled || e.data?.type !== "VI_SUB_TEXT") return;
    const text = e.data.text?.trim();
    if (!text) return;
    try {
      const vi = await translate(text);
      if (vi) { UI.showSub(vi, text); TTSEngine.speak(vi); }
    } catch (_) {}
  });

} else {
  function iframeStatus(msg) {
    try { window.top.postMessage({ type: "VI_IFRAME_STATUS", msg }, "*"); } catch (_) {}
    console.log("[VI-Sub] iframe:", msg);
  }

  function iframeInit() {
    const videos = document.querySelectorAll("video");
    iframeStatus(`DOM scan — videos: ${videos.length}, url: ${location.href.slice(0, 80)}`);

    for (const video of videos) {
      const tracks = Array.from(video.textTracks || []);
      iframeStatus(`video found — tracks: ${tracks.length}`);
      tracks.forEach(t => iframeStatus(`  track kind=${t.kind} lang=${t.language} cues=${t.cues?.length ?? "?"}`));

      const track = tracks.find(t => (t.kind === "subtitles" || t.kind === "captions") && (t.language === "en" || t.language?.startsWith("en")))
                 || tracks.find(t => t.kind === "subtitles" || t.kind === "captions");
      if (!track) continue;

      track.mode = "hidden";

      const setupOncuechange = () => {
        iframeStatus(`track locked — ${track.cues?.length ?? 0} cues`);
        track.oncuechange = () => {
          const cue  = track.activeCues?.[0];
          const text = cue?.text?.replace(/<[^>]+>/g, "").trim();
          if (text) {
            try { window.top.postMessage({ type: "VI_SUB_TEXT", text }, "*"); } catch (_) {}
          }
        };
      };

      if (track.cues && track.cues.length > 0) {
        setupOncuechange();
      } else {
        track.addEventListener("load", setupOncuechange, { once: true });
        iframeStatus("waiting for track to load...");
      }
      return;
    }

    for (const sel of KNOWN_SELECTORS) {
      try {
        const el = document.querySelector(sel);
        if (!el?.innerText?.trim()) continue;
        new MutationObserver(() => {
          const text = el.innerText?.trim();
          if (text) {
            try { window.top.postMessage({ type: "VI_SUB_TEXT", text }, "*"); } catch (_) {}
          }
        }).observe(el, { childList: true, subtree: true, characterData: true });
        iframeStatus(`selector locked: ${sel}`);
        return;
      } catch (_) {}
    }

    iframeStatus("no video/track found — will retry");
    return false;
  }

  function iframeStartWithRetry() {
    if (iframeInit() === false) {
      let attempts = 0;
      const timer = setInterval(() => {
        attempts++;
        if (iframeInit() !== false || attempts >= 20) {
          clearInterval(timer);
          if (attempts >= 20) iframeStatus("gave up after 20 retries");
        }
      }, 1500);

      new MutationObserver(() => {
        iframeInit();
      }).observe(document.documentElement, { childList: true, subtree: true });
    }
  }

  if (document.body) iframeStartWithRetry();
  else document.addEventListener("DOMContentLoaded", iframeStartWithRetry);
}

console.log(`[VI-Sub] v3.1 loaded | top: ${IS_TOP_FRAME}`);
