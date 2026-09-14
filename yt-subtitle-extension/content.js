/**
 * VI Subtitle Translator & TTS — v3.0
 *
 * Kiến trúc module:
 *   CONFIG       — tất cả tham số có thể tune ở một chỗ
 *   Cache        — LRU cache với TTL cho bản dịch
 *   AudioDucker  — tự động hạ âm lượng video khi TTS đang đọc
 *   TTSEngine    — Web Speech API, tự điều chỉnh rate theo cue duration
 *   UI           — floating button + subtitle overlay
 *   PreFetcher   — dịch nền toàn bộ cues ngay khi track load
 *   VideoSync    — lập lịch phát TTS chính xác qua timeupdate
 *   Detector     — 3 chiến lược: track → selector → proximity scan
 *   Controller   — điều phối bật/tắt, top-frame vs iframe
 *
 * Nâng cấp sau này:
 *   - Đổi CONFIG.USE_BACKEND_TTS = true + cài edge-tts để có giọng đẹp hơn
 *   - Thêm site vào KNOWN_SELECTORS để hỗ trợ platform mới
 *   - Tăng CONFIG.PREFETCH_BATCH nếu API không bị rate-limit
 */

// ══════════════════════════════════════════════════════════════════
// CONFIG — chỉnh tất cả tham số ở đây, không phải rải rác trong code
// ══════════════════════════════════════════════════════════════════
const CONFIG = {
  // API endpoints
  API_TRANSLATE:      "http://127.0.0.1:8000/api/translate",
  API_TTS:            "http://127.0.0.1:8000/api/tts",   // edge-tts backend (optional)
  USE_BACKEND_TTS:    true ,   // true = dùng edge-tts (giọng đẹp), false = Web Speech API

  // Cache
  CACHE_MAX:          500,
  CACHE_TTL_MS:       3_600_000,   // 1 giờ — bản dịch không đổi nên cache lâu

  // Pre-fetch
  PREFETCH_BATCH:     5,           // dịch song song bao nhiêu câu một lúc
  PREFETCH_DELAY_MS:  250,         // nghỉ giữa các batch để không spam Google

  // Sync timing
  LOOKAHEAD_SEC:      1.0,         // schedule TTS trước bao nhiêu giây
  DEBOUNCE_MS:        300,         // cho selector/proximity strategy

  // Audio ducking
  DUCK_VOLUME:        0.12,        // âm lượng video khi TTS đang đọc (0–1)
  DUCK_FADE_IN_S:     0.15,        // giây để hạ xuống
  DUCK_FADE_OUT_S:    0.40,        // giây để nâng lên

  // TTS rate
  TTS_CHARS_PER_SEC:  3.5,         // ký tự/giây ở rate = 1.0 (tiếng Việt)
  TTS_RATE_MIN:       0.75,
  TTS_RATE_MAX:       1.90,
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
    // LRU: move to end
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
// AUDIO DUCKER — hạ volume video khi TTS đang đọc
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
    gainNode.gain.setTargetAtTime(
      CONFIG.DUCK_VOLUME, ctx.currentTime, CONFIG.DUCK_FADE_IN_S / 3
    );
  }

  function unduck() {
    if (!gainNode) return;
    gainNode.gain.setTargetAtTime(
      1.0, ctx.currentTime, CONFIG.DUCK_FADE_OUT_S / 3
    );
  }

  function reset() { if (gainNode) gainNode.gain.value = 1.0; }

  return { setup, duck, unduck, reset };
})();


// ══════════════════════════════════════════════════════════════════
// TTS ENGINE — Web Speech API với auto rate-adjust theo cue duration
// ══════════════════════════════════════════════════════════════════
const TTSEngine = (() => {
  let viVoice = null;

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

  /**
   * Gọi trong click handler (user gesture) để bypass autoplay policy của Edge/Chrome.
   * Nếu không gọi warmup, speak() từ async callback sẽ bị block silently.
   */
  function warmup() {
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(" ");
      u.volume = 0; u.lang = "vi-VN";
      if (viVoice) u.voice = viVoice;
      window.speechSynthesis.speak(u);
    } catch (_) {}
  }

  /**
   * @param {string} text       — bản dịch tiếng Việt
   * @param {number} durationMs — thời lượng cue (ms), 0 = không điều chỉnh rate
   */
  function speak(text, durationMs = 0) {
    if (!text) return;
    console.log(`[VI-Sub] Đang thử phát âm thanh: "${text}"`);

    // ── Backend TTS (gTTS qua server) ──────────────────────────
    if (CONFIG.USE_BACKEND_TTS) {
      window.speechSynthesis.cancel();
      const _url = CONFIG.API_TTS + '?text=' + encodeURIComponent(text);
      const _audio = new Audio(_url);
      AudioDucker.duck();
      _audio.onended = () => AudioDucker.unduck();
      _audio.onerror = (e) => {
        AudioDucker.unduck();
        console.warn('[VI-Sub TTS] Server error:', e);
      };
      _audio.play().catch(e => {
        AudioDucker.unduck();
        console.warn('[VI-Sub TTS] Play blocked:', e);
      });
      return;
    }
    // ── Web Speech API (fallback) ───────────────────────────────
    window.speechSynthesis.cancel();

    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = "vi-VN";
    if (viVoice) utter.voice = viVoice;

    if (durationMs > 0) {
      // Tính rate để câu vừa khít trong cue duration
      const naturalMs = (text.length / CONFIG.TTS_CHARS_PER_SEC) * 1000;
      const rate      = naturalMs / durationMs;
      utter.rate = Math.min(CONFIG.TTS_RATE_MAX, Math.max(CONFIG.TTS_RATE_MIN, rate));
    } else {
      utter.rate = 1.0;
    }

    utter.onstart = () => AudioDucker.duck();
    utter.onend   = () => AudioDucker.unduck();
    utter.onerror = (e) => {
      console.error("[VI-Sub] LỖI PHÁT ÂM THANH:", e);
      AudioDucker.unduck();
    };

    window.speechSynthesis.speak(utter);
  }

  function stop()   { window.speechSynthesis.cancel(); AudioDucker.unduck(); }
  function pause()  { window.speechSynthesis.pause();  }
  function resume() { window.speechSynthesis.resume(); }

  return { warmup, speak, stop, pause, resume };
})();


// ══════════════════════════════════════════════════════════════════
// UI — Floating button + subtitle overlay
// ══════════════════════════════════════════════════════════════════
const UI = (() => {
  let _btn = null, _overlay = null;

  function createButton(onToggle) {
    if (document.getElementById("vi-sub-btn")) return;
    _btn = document.createElement("button");
    _btn.id    = "vi-sub-btn";
    _btn.title = "Bật/tắt dịch và đọc phụ đề tiếng Việt";
    _btn.style.cssText = `
      position:fixed; bottom:24px; right:24px; z-index:2147483647;
      background:#1a1a2e; color:#fbbf24; border:2px solid #fbbf24;
      border-radius:50px; padding:10px 18px; font-size:15px; font-weight:bold;
      cursor:pointer; box-shadow:0 4px 20px rgba(0,0,0,.5);
      transition:all .2s ease; font-family:system-ui,sans-serif; user-select:none;
    `;
    _btn.textContent = "🔊 VI";
    _btn.addEventListener("mouseenter", () => { _btn.style.transform = "scale(1.08)"; });
    _btn.addEventListener("mouseleave", () => { _btn.style.transform = "scale(1)";    });
    _btn.addEventListener("click", onToggle);
    document.body.appendChild(_btn);
  }

  function setActive(active) {
    if (!_btn) return;
    _btn.style.background = active ? "#fbbf24" : "#1a1a2e";
    _btn.style.color      = active ? "#1a1a2e" : "#fbbf24";
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
      width:80%; text-align:center; color:#fbbf24; font-size:1.15em;
      font-weight:600; font-family:system-ui,sans-serif;
      text-shadow:0 0 5px #000,0 0 5px #000,0 0 5px #000;
      transition:opacity .15s ease;
    `;
    const wrapper = videoEl.parentElement || document.body;
    if (wrapper !== document.body) wrapper.style.position ||= "relative";
    wrapper.appendChild(_overlay);
  }

  function showSub(text) {
    if (!_overlay || !text) return;
    _overlay.textContent = text;
    _overlay.style.display  = "block";
    _overlay.style.opacity  = "1";
  }

  function hideSub() {
    if (!_overlay) return;
    _overlay.style.opacity = "0";
    setTimeout(() => { if (_overlay) _overlay.style.display = "none"; }, 160);
  }

  function destroyOverlay() {
    const el = document.getElementById("vi-sub-overlay");
    if (el) el.remove();
    _overlay = null;
  }

  return { createButton, setActive, setLabel, createOverlay, showSub, hideSub, destroyOverlay };
})();


// ══════════════════════════════════════════════════════════════════
// PRE-FETCHER — dịch nền toàn bộ cues khi track load xong
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
        try { await translate(text); } catch (_) { /* retry realtime */ }
      }));

      // Progress trên button: "⏳ 42%"
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
// VIDEO SYNC ENGINE — vòng lặp timer độc lập (250ms) quét DOM 4 lần/giây (chống Coursera tráo thẻ <video>)
// ══════════════════════════════════════════════════════════════════
const VideoSync = (() => {
  let _cues     = [];
  let _enabled  = false;
  let _timerId  = null;
  let _lastTime = 0;
  const _done   = new Set();   // Set<cue index> đã schedule/phát

  function _tick() {
    if (!_enabled) return;

    // 1. Luôn truy vấn thẻ video trực tiếp từ DOM để chống việc Coursera/YouTube tráo thẻ
    const currentVideo = document.querySelector('video');
    if (!currentVideo) return;

    const currentTime = currentVideo.currentTime;

    // Phát hiện user tua video (Seek detection)
    if (Math.abs(currentTime - _lastTime) > 1.5) {
      _done.clear();
      TTSEngine.stop();
      UI.hideSub();
    }
    _lastTime = currentTime;

    // Bỏ qua khi video paused
    if (currentVideo.paused) return;

    // Đảm bảo AudioDucker được bind với thẻ video hiện tại
    AudioDucker.setup(currentVideo);

    const rate = currentVideo.playbackRate || 1;

    // 2. Duyệt qua mảng phụ đề (_cues)
    _cues.forEach((cue, idx) => {
      if (_done.has(idx)) return;
      if (cue.startTime < currentTime - 0.3) { _done.add(idx); return; } // đã qua
      if (cue.startTime - currentTime > CONFIG.LOOKAHEAD_SEC * 2) return; // quá xa

      if (cue.startTime - currentTime <= CONFIG.LOOKAHEAD_SEC) {
        _done.add(idx);
        const delayMs = Math.max(0, (cue.startTime - currentTime) * 1000 / rate);

        setTimeout(async () => {
          if (!_enabled) return;

          // Re-query thẻ video mới nhất từ DOM trong callback
          const vNow = document.querySelector('video');
          if (!vNow || Math.abs(vNow.currentTime - cue.startTime) > 2.0) return;

          const text = cue.text.replace(/<[^>]+>/g, "").trim();
          if (!text) return;

          try {
            const vi = await translate(text);
            const durationMs = (cue.endTime - cue.startTime) * 1000;
            if (!vi || !_enabled) return;

            console.log(`[VI-Sub] Đang phát câu [${idx}]: "${vi}"`);
            UI.showSub(vi);
            TTSEngine.speak(vi, durationMs);
            setTimeout(() => UI.hideSub(), durationMs);
          } catch (e) {
            console.warn("[VI-Sub] cue error:", e.message);
          }
        }, delayMs);
      }
    });
  }

  function attach(videoEl, cues) {
    detach();
    _cues    = cues;
    _enabled = true;
    _done.clear();
    _lastTime = 0;

    if (videoEl) AudioDucker.setup(videoEl);

    // Vòng lặp Timer Độc lập 250ms (4 lần / giây)
    _timerId = setInterval(_tick, 250);
    console.log(`[VI-Sub] VideoSync attached (Timer Loop 250ms): ${cues.length} cues`);
  }

  function detach() {
    if (_timerId) {
      clearInterval(_timerId);
      _timerId = null;
    }
    _done.clear();
    _cues = [];
    _enabled = false;
    TTSEngine.stop();
  }

  return { attach, detach };
})();


// ══════════════════════════════════════════════════════════════════
// DETECTOR — 3 chiến lược tìm phụ đề
// ══════════════════════════════════════════════════════════════════
const KNOWN_SELECTORS = [
  // YouTube
  ".ytp-caption-segment",
  // Coursera
  ".rc-SubtitleItem", ".subtitle-item span", "[data-testid='subtitle-item']",
  // Udemy
  ".well--text--2WPkk", "[class*='captions--captions']",
  // edX
  ".subtitles li.current", ".closed-captions span",
  // Video.js (nhiều platform dùng)
  ".vjs-text-track-display span", ".vjs-text-track-cue span",
  // Generic fallback
  "[class*='subtitle']", "[class*='caption']",
];

/** Chờ track.cues load xong (browser tải WebVTT lazily) */
function waitForCues(track) {
  return new Promise(resolve => {
    track.mode = "hidden";   // trigger load nếu chưa load
    if (track.cues && track.cues.length > 0) {
      return resolve(Array.from(track.cues));
    }
    track.addEventListener("load", () => resolve(Array.from(track.cues || [])), { once: true });
    setTimeout(() => resolve(Array.from(track.cues || [])), 5000);
  });
}

/**
 * Strategy 1: <track kind="subtitles/captions">
 * Tốt nhất vì có timing chính xác → dùng VideoSync + PreFetcher
 */
async function tryTrackStrategy(video) {
  const tracks = Array.from(video.textTracks || []);
  const track  = tracks.find(t => (t.kind === "subtitles" || t.kind === "captions") && (t.language === "en" || t.language?.startsWith("en"))) || (tracks.find(t => (t.kind === "subtitles" || t.kind === "captions") && (t.language === "en" || t.language?.startsWith("en"))) || (tracks.find(t => (t.kind === "subtitles" || t.kind === "captions") && (t.language === "en" || t.language?.startsWith("en"))) || tracks.find(t => t.kind === "subtitles" || t.kind === "captions")));
  if (!track) return false;

  const cues = await waitForCues(track);
  if (!cues.length) return false;

  console.log(`[VI-Sub] Strategy 1 (track): ${cues.length} cues`);
  UI.createOverlay(video);
  VideoSync.attach(video, cues);
  PreFetcher.run(cues);   // chạy nền, button sẽ hiện %
  return true;
}

/**
 * Strategy 2: CSS selectors phổ biến
 * Dùng MutationObserver, debounce, không có timing chính xác
 */
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
          try {
            const vi = await translate(text);
            if (vi) { UI.showSub(vi); TTSEngine.speak(vi); }
          } catch (_) {}
        }, CONFIG.DEBOUNCE_MS);
      }).observe(el, { childList: true, subtree: true, characterData: true });

      return true;
    } catch (_) {}
  }
  return false;
}

/**
 * Strategy 3: Proximity scan
 * Tìm element gần <video> có text ngắn thay đổi liên tục → đó là phụ đề
 */
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
      if (["SCRIPT","STYLE","NOSCRIPT"].includes(node.tagName))    continue;
      if (node.id === "vi-sub-overlay" || node.id === "vi-sub-btn") continue;

      const text = node.innerText?.trim();
      if (!text || text.length < 5 || text.length > 200)          continue;
      if (text.split(" ").length < 2)                              continue;

      const r = node.getBoundingClientRect();
      if (!r.width || !r.height)                                   continue;
      if (r.top < area.top || r.bottom > area.bottom)              continue;
      if (r.left < area.left || r.right > area.right)              continue;

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
            try {
              const vi = await translate(t);
              if (vi) { UI.showSub(vi); TTSEngine.speak(vi); }
            } catch (_) {}
          }, CONFIG.DEBOUNCE_MS);
        }).observe(node, { childList: true, subtree: true, characterData: true });
        return;
      }
    }

    // Dọn log cũ
    const now = Date.now();
    changeLog.forEach((v, k) => { if (now - v.ts > 15_000) changeLog.delete(k); });
  }, 1500);

  // Dừng sau 30 giây nếu không tìm thấy
  setTimeout(() => {
    if (_proxInterval) {
      clearInterval(_proxInterval); _proxInterval = null;
      UI.setLabel("🔊 Không thấy phụ đề");
      setTimeout(() => UI.setLabel("🔊 VI"), 3000);
    }
  }, 30_000);
}


// ══════════════════════════════════════════════════════════════════
// CONTROLLER — điều phối toàn bộ
// ══════════════════════════════════════════════════════════════════
let _isEnabled  = false;
let _retryTimer = null;
let _domWatcher = null;

/**
 * Thử detect trên các video hiện có trong DOM.
 * Trả về true nếu đã lock được strategy nào đó.
 */
async function tryDetectNow() {
  const videos = Array.from(document.querySelectorAll("video"))
    .filter(v => v.readyState >= 1);   // chỉ lấy video đã có metadata

  if (!videos.length) {
    // Debug: log tất cả video element (kể cả chưa ready)
    const allVideos = document.querySelectorAll("video");
    console.log(`[VI-Sub] Videos in DOM: ${allVideos.length}, ready: ${videos.length}`);
    return false;
  }

  // Strategy 1: <track> WebVTT (tốt nhất)
  for (const v of videos) {
    const tracks = Array.from(v.textTracks || []);
    console.log(`[VI-Sub] Video ${v.src?.slice(0,60)||"(blob)"} → tracks: ${tracks.length}`);
    tracks.forEach(t => console.log(`  track: kind=${t.kind} lang=${t.language} cues=${t.cues?.length ?? "?"}`));
    if (await tryTrackStrategy(v)) return true;
  }

  // Strategy 2: known CSS selectors
  for (const v of videos) {
    if (tryKnownSelectors(v)) return true;
  }

  // Strategy 3: proximity scan (last resort)
  startProximityScan(videos[0]);
  return true;   // proximity scan đang chạy nền → coi như đã xử lý
}

/**
 * Khởi động detection với retry + DOM watcher.
 * Xử lý 3 trường hợp:
 *   - Video load muộn (SPA navigation, lazy embed)
 *   - Track cues chưa ready ngay khi page load
 *   - Video nằm trong iframe → top frame chỉ cần nghe postMessage
 */
async function startAll() {
  stopWatchers();

  const found = await tryDetectNow();
  if (found) return;

  // Không thấy video ready → thông báo và chờ
  UI.setLabel("⏳ Chờ video...");
  console.log("[VI-Sub] No ready video found. Watching DOM for changes...");

  let attempts = 0;

  // Retry mỗi 2 giây (tổng 30 giây)
  _retryTimer = setInterval(async () => {
    attempts++;
    if (!_isEnabled) { stopWatchers(); return; }

    console.log(`[VI-Sub] Retry ${attempts}/15...`);
    const found = await tryDetectNow();
    if (found) {
      stopWatchers();
    } else if (attempts >= 15) {
      stopWatchers();
      // Lúc này video có thể nằm trong iframe — vẫn nghe postMessage
      // Không báo lỗi vì iframe script vẫn đang chạy
      UI.setLabel("⏳ Chờ phụ đề...");
      console.log("[VI-Sub] No video in top frame after 30s. Listening for iframe postMessage.");
    }
  }, 2000);

  // MutationObserver: phát hiện video/track được thêm vào DOM muộn
  _domWatcher = new MutationObserver(async () => {
    if (!_isEnabled) return;
    const found = await tryDetectNow();
    if (found) stopWatchers();
  });
  _domWatcher.observe(document.documentElement, {
    childList: true,
    subtree: true,
    // Chỉ quan tâm khi có element mới (không cần watch text change)
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
  // ── Trang chính: hiện nút điều khiển ──
  const init = () => {
    UI.createButton(() => {
      _isEnabled = !_isEnabled;
      UI.setActive(_isEnabled);

      if (_isEnabled) {
        // Warm-up TTS ngay trong user gesture để bypass autoplay policy
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

  // Nhận phụ đề + status từ iframe
  window.addEventListener("message", async e => {
    // Status từ iframe → log ra console để debug
    if (e.data?.type === "VI_IFRAME_STATUS") {
      console.log("[VI-Sub] 📡 iframe says:", e.data.msg);
      // Nếu iframe đã lock track → cập nhật button
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
      if (vi) { UI.showSub(vi); TTSEngine.speak(vi); }
    } catch (_) {}
  });

} else {
  // ── Iframe: detect và forward lên top frame ──
  // Gửi status về top frame để button phản ánh đúng tình trạng
  function iframeStatus(msg) {
    try { window.top.postMessage({ type: "VI_IFRAME_STATUS", msg }, "*"); } catch (_) {}
    console.log("[VI-Sub] iframe:", msg);
  }

  function iframeInit() {
    const videos = document.querySelectorAll("video");
    iframeStatus(`DOM scan — videos: ${videos.length}, url: ${location.href.slice(0, 80)}`);

    // Strategy 1: track
    for (const video of videos) {
      const tracks = Array.from(video.textTracks || []);
      iframeStatus(`video found — tracks: ${tracks.length}`);
      tracks.forEach(t => iframeStatus(`  track kind=${t.kind} lang=${t.language} cues=${t.cues?.length ?? "?"}`));

      const track = tracks.find(t => (t.kind === "subtitles" || t.kind === "captions") && (t.language === "en" || t.language?.startsWith("en"))) || (tracks.find(t => (t.kind === "subtitles" || t.kind === "captions") && (t.language === "en" || t.language?.startsWith("en"))) || (tracks.find(t => (t.kind === "subtitles" || t.kind === "captions") && (t.language === "en" || t.language?.startsWith("en"))) || tracks.find(t => t.kind === "subtitles" || t.kind === "captions")));
      if (!track) continue;

      track.mode = "hidden";

      // Đợi cues load nếu chưa có
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
      return; // locked
    }

    // Strategy 2: selector
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

    // Không tìm thấy gì
    iframeStatus("no video/track found — will retry");
    return false;
  }

  // Retry trong iframe (video có thể load muộn trong SPA)
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

      // Cũng watch DOM
      new MutationObserver(() => {
        if (iframeInit() !== false) {
          // Không có cách dừng MutationObserver từ trong callback dễ dàng
          // nhưng iframeInit sẽ return sớm sau khi lock
        }
      }).observe(document.documentElement, { childList: true, subtree: true });
    }
  }

  if (document.body) iframeStartWithRetry();
  else document.addEventListener("DOMContentLoaded", iframeStartWithRetry);
}

console.log(`[VI-Sub] v3.0 loaded | top: ${IS_TOP_FRAME}`);
