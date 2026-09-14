// =============================================================================
// content.js – Logic rẽ nhánh Top Window vs Iframe
// =============================================================================
//
// Do manifest.json có "all_frames": true, file này sẽ được Chrome inject vào:
//   1. Top-level document (trang Coursera chính)
//   2. Tất cả iframe con (kể cả iframe khác origin chứa video)
//
// Vì vậy PHẢI rẽ nhánh ngay từ đầu dựa vào window === window.top.
//
// ┌─────────────────────────────────────────────────────────────────────────┐
// │                        LUỒNG TỔNG THỂ                                  │
// │                                                                         │
// │  [Top Window]          [Background]         [Iframe chứa video]         │
// │      │                     │                        │                   │
// │  User click 🔊             │                        │                   │
// │      │──START_DUBBING_CMD──►│                        │                   │
// │      │                     │──EXECUTE_DUBBING───────►│                   │
// │      │                     │                   waitForVideo() chờ DOM   │
// │      │                     │                   → MutationObserver+Poll  │
// │      │                     │                   → Chạy dubbing pipeline  │
// │      │◄──UPDATE_UI_STATUS──│◄──IFRAME_STATUS_REPORT──│                   │
// │   Cập nhật UI              │                        │                   │
// └─────────────────────────────────────────────────────────────────────────┘
//
// NOTE: Coursera dùng React SPA nên <video> được render bất đồng bộ.
// Không thể querySelector ngay – phải dùng waitForVideo() để chờ DOM.
// =============================================================================

(function () {
  'use strict';

  // ============================================================
  // NHÁNH 1: TOP WINDOW (window === window.top)
  // Chịu trách nhiệm: Render UI, bắt sự kiện người dùng
  // KHÔNG được query video ở đây vì video nằm trong iframe!
  // ============================================================
  if (window === window.top) {
    console.log('[Content - Top] Đang chạy ở top-level window.');
    initTopWindow();
  }

  // ============================================================
  // NHÁNH 2: IFRAME WINDOW (window !== window.top)
  // Chịu trách nhiệm: Lắng nghe lệnh, tìm video, chạy dubbing
  // ============================================================
  else {
    // ── Lọc iframe rác (quảng cáo DoubleClick, tracking pixel, v.v.) ──────
    // Coursera nhúng hàng chục iframe từ doubleclick.net, 2mdn.net, v.v.
    // Nếu không lọc, extension chạy hoang phí tài nguyên trong các iframe đó.
    // Chỉ tiếp tục khi hostname chứa 'coursera.org' (hoặc các domain hợp lệ khác).
    const ALLOWED_HOSTNAMES = [
      'coursera.org',
      'youtube.com',
      'udemy.com',
      'player.vimeo.com'  // Thêm domain khác nếu cần
    ];
    const isAllowed = ALLOWED_HOSTNAMES.some(h => window.location.hostname.includes(h));
    if (!isAllowed) {
      // Im lặng thoát – không log để tránh spam console với hàng chục iframe rác
      return;
    }

    console.log('[Content - Iframe] Đang chạy trong iframe hợp lệ:', location.href);
    initIframeWindow();
  }


  // ─────────────────────────────────────────────────────────────
  // NHÁNH 1 IMPLEMENTATION: Top Window Logic
  // ─────────────────────────────────────────────────────────────
  function initTopWindow() {

    // ── 1.1: Inject UI Button vào trang ──────────────────────
    const btn = createDubbingButton();
    document.body.appendChild(btn);

    // ── 1.2: Bắt sự kiện click nút 🔊 VI ─────────────────────
    btn.addEventListener('click', () => {
      const isDubbing = btn.dataset.active === 'true';

      if (!isDubbing) {
        // Bắt đầu lồng tiếng: gửi lệnh lên background
        btn.dataset.active = 'true';
        btn.textContent = '⏹ Dừng VI';
        btn.style.background = '#dc3545';

        // ✅ ĐIỂM THEN CHỐT: Gửi tới background, KHÔNG dùng postMessage.
        // Background sẽ dùng chrome.tabs.sendMessage để broadcast xuống iframe.
        chrome.runtime.sendMessage(
          {
            action: 'START_DUBBING_COMMAND',
            config: {
              targetLang: 'vi',
              ttsSpeed:   1.0,
              duckVolume: 0.2  // Giảm âm gốc xuống 20% khi phát TTS
            }
          },
          (response) => {
            if (chrome.runtime.lastError) {
              console.error('[Content - Top] Gửi lệnh thất bại:', chrome.runtime.lastError.message);
              resetButton(btn);
              return;
            }
            console.log('[Content - Top] Background xác nhận:', response?.message);
          }
        );

      } else {
        // Dừng lồng tiếng
        btn.dataset.active = 'false';
        resetButton(btn);

        chrome.runtime.sendMessage({ action: 'STOP_DUBBING_COMMAND' });
      }
    });

    // ── 1.3: Lắng nghe cập nhật trạng thái từ background ─────
    // Background chuyển tiếp trạng thái từ iframe về đây để cập nhật UI
    chrome.runtime.onMessage.addListener((message) => {
      if (message.action === 'UPDATE_UI_STATUS') {
        handleUIStatusUpdate(btn, message.status, message.data);
      }
    });
  }

  /**
   * Cập nhật UI dựa trên trạng thái trả về từ iframe
   * @param {HTMLElement} btn - Nút lồng tiếng
   * @param {string} status - 'VIDEO_FOUND' | 'VIDEO_NOT_FOUND' | 'DUBBING_STARTED' | 'ERROR'
   * @param {Object} data - Dữ liệu bổ sung
   */
  function handleUIStatusUpdate(btn, status, data) {
    console.log('[Content - Top] Cập nhật UI:', status, data);

    switch (status) {
      case 'VIDEO_FOUND':
        showToast('✅ Đã tìm thấy video trong iframe. Đang khởi động...');
        break;

      case 'VIDEO_NOT_FOUND':
        showToast('❌ Không tìm thấy video trong iframe nào.', 'error');
        resetButton(btn);
        break;

      case 'DUBBING_STARTED':
        showToast('🔊 Lồng tiếng Việt đã bắt đầu!');
        break;

      case 'DUBBING_STOPPED':
        resetButton(btn);
        showToast('⏹ Đã dừng lồng tiếng.');
        break;

      case 'ERROR':
        showToast(`⚠️ Lỗi: ${data?.message ?? 'Không xác định'}`, 'error');
        resetButton(btn);
        break;
    }
  }

  /**
   * Tạo nút lồng tiếng và gắn vào DOM
   */
  function createDubbingButton() {
    const btn = document.createElement('button');
    btn.id             = 'vi-dubbing-btn';
    btn.textContent    = '🔊 VI';
    btn.dataset.active = 'false';
    Object.assign(btn.style, {
      position:     'fixed',
      bottom:       '80px',
      right:        '20px',
      zIndex:       '999999',
      padding:      '10px 16px',
      background:   '#007bff',
      color:        '#fff',
      border:       'none',
      borderRadius: '24px',
      fontSize:     '14px',
      fontWeight:   'bold',
      cursor:       'pointer',
      boxShadow:    '0 4px 12px rgba(0,0,0,0.3)',
      transition:   'background 0.2s'
    });
    return btn;
  }

  function resetButton(btn) {
    btn.dataset.active = 'false';
    btn.textContent    = '🔊 VI';
    btn.style.background = '#007bff';
  }

  function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.textContent = message;
    Object.assign(toast.style, {
      position:     'fixed',
      bottom:       '140px',
      right:        '20px',
      zIndex:       '999999',
      padding:      '10px 16px',
      background:   type === 'error' ? '#dc3545' : '#333',
      color:        '#fff',
      borderRadius: '8px',
      fontSize:     '13px',
      maxWidth:     '300px',
      opacity:      '1',
      transition:   'opacity 0.5s'
    });
    document.body.appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0'; }, 3000);
    setTimeout(() => { toast.remove(); }, 3600);
  }


  // ─────────────────────────────────────────────────────────────
  // NHÁNH 2 IMPLEMENTATION: Iframe Window Logic
  // ─────────────────────────────────────────────────────────────
  function initIframeWindow() {

    // ── 2.1: Lắng nghe lệnh từ background ────────────────────
    chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {

      // ── Nhận lệnh THỰC THI lồng tiếng ──────────────────────
      if (message.action === 'EXECUTE_DUBBING') {
        console.log('[Content - Iframe] Nhận lệnh EXECUTE_DUBBING. Tìm video...');
        handleExecuteDubbing(message.config ?? {});
        sendResponse({ received: true, url: location.href });
      }

      // ── Nhận lệnh DỪNG lồng tiếng ──────────────────────────
      else if (message.action === 'STOP_DUBBING') {
        console.log('[Content - Iframe] Nhận lệnh STOP_DUBBING.');
        stopDubbingPipeline();
        sendResponse({ stopped: true });
      }

      return true; // Giữ kênh message mở để dùng sendResponse async
    });
  }

  // ─────────────────────────────────────────────────────────────────────────
  // waitForVideo – "Mắt thần" chờ <video> xuất hiện trong DOM
  // ─────────────────────────────────────────────────────────────────────────
  //
  // Tại sao cần hàm này?
  //   Coursera là React SPA: khi content.js chui vào iframe, React vẫn đang
  //   render. Gọi querySelector('video') ngay lập tức → luôn trả về null.
  //   Hàm này dùng 3 lớp bảo vệ chồng lên nhau:
  //     1. Tìm ngay lập tức (phòng khi video đã sẵn sàng)
  //     2. MutationObserver  → lắng nghe mọi thay đổi DOM, phản ứng tức thì
  //     3. Polling 500ms     → backup khi video nằm trong Shadow DOM ngầm
  //     4. Timeout 15s       → không treo tab nếu Coursera lỗi không render
  //
  // @param {number} timeout_ms - Thời gian chờ tối đa (mặc định 15 giây)
  // @returns {Promise<HTMLVideoElement>}
  // ─────────────────────────────────────────────────────────────────────────
  function waitForVideo(timeout_ms = 15000) {
    return new Promise((resolve, reject) => {

      // ── LỚP 1: Tìm ngay – phòng khi video đã có sẵn ─────────────────────
      const existing = document.querySelector('video');
      if (existing) {
        console.log('[Content - Iframe] Video đã sẵn sàng ngay lập tức.');
        return resolve(existing);
      }

      console.log('[Content - Iframe] Video chưa render, bắt đầu theo dõi DOM...');

      let resolved = false; // Cờ tránh resolve() được gọi nhiều lần

      function cleanup(timerRef, intervalRef, observerRef) {
        observerRef.disconnect();
        clearInterval(intervalRef);
        clearTimeout(timerRef);
      }

      // ── LỚP 2: MutationObserver – phản ứng tức thì khi DOM thay đổi ─────
      // Ưu điểm: không tốn CPU như polling, kích hoạt chính xác khoảnh khắc
      // React vẽ xong thẻ <video> vào DOM.
      const observer = new MutationObserver(() => {
        const v = document.querySelector('video');
        if (v && !resolved) {
          resolved = true;
          cleanup(fallbackTimer, polling, observer);
          console.log('[Content - Iframe] ✅ MutationObserver tóm được <video>!');
          resolve(v);
        }
      });

      // Theo dõi toàn bộ cây DOM bên trong iframe (childList + subtree)
      observer.observe(document.body || document.documentElement, {
        childList: true,
        subtree:   true
      });

      // ── LỚP 3: Polling 500ms – backup cho Shadow DOM / lazy render ────────
      // Một số player nhúng video vào Shadow DOM (Vimeo, JW Player...).
      // MutationObserver không xuyên qua shadow root, nhưng querySelector
      // sẽ tìm được nếu shadow root đã "pierce" ra ngoài.
      const polling = setInterval(() => {
        const v = document.querySelector('video');
        if (v && !resolved) {
          resolved = true;
          cleanup(fallbackTimer, polling, observer);
          console.log('[Content - Iframe] ✅ Polling tóm được <video>!');
          resolve(v);
        }
      }, 500);

      // ── LỚP 4: Timeout – không treo vô thời hạn nếu Coursera lỗi ─────────
      const fallbackTimer = setTimeout(() => {
        if (!resolved) {
          resolved = true;
          cleanup(fallbackTimer, polling, observer);
          console.warn(`[Content - Iframe] ⏱ Đã chờ ${timeout_ms / 1000}s nhưng không tìm thấy video tại:`, location.href);
          reject(new Error(`Timeout ${timeout_ms}ms: Không tìm thấy <video>`));
        }
      }, timeout_ms);
    });
  }

  /**
   * Tìm video (async) và khởi chạy toàn bộ pipeline lồng tiếng bên trong iframe
   * @param {Object} config - { targetLang, ttsSpeed, duckVolume }
   */
  async function handleExecuteDubbing(config) {
    try {
      // ✅ Chờ video xuất hiện thay vì querySelector thẳng một phát
      const video = await waitForVideo(15000);

      // Video tìm thấy – báo cáo về top window
      console.log('[Content - Iframe] ✅ Tìm thấy video!', video);
      chrome.runtime.sendMessage({
        action: 'IFRAME_STATUS_REPORT',
        status: 'VIDEO_FOUND',
        data:   { iframeUrl: location.href, videoSrc: video.src }
      });

      // ── Khởi chạy pipeline lồng tiếng ────────────────────────────────────
      startDubbingPipeline(video, config);

    } catch (err) {
      // Timeout hoặc lỗi khác – báo cáo về top window để reset UI
      console.error('[Content - Iframe] handleExecuteDubbing thất bại:', err.message);
      chrome.runtime.sendMessage({
        action: 'IFRAME_STATUS_REPORT',
        status: 'VIDEO_NOT_FOUND',
        data:   { iframeUrl: location.href, reason: err.message }
      });
    }
  }

  /**
   * Pipeline lồng tiếng – GHÉP NỐI VÀO MODULE GỐC CỦA BẠN
   *
   * Hàm này chạy hoàn toàn trong ngữ cảnh iframe, nghĩa là:
   *   - Có toàn quyền truy cập video.currentTime, video.textTracks, v.v.
   *   - Có thể gọi Web Audio API để duck âm gốc
   *   - Có thể phát TTS audio cạnh video
   *
   * @param {HTMLVideoElement} video
   * @param {Object} config
   */
  function startDubbingPipeline(video, config) {
    console.log('[Content - Iframe] Bắt đầu dubbing pipeline. Config:', config);

    _isDubbing = true;
    let lastTime = 0;
    const playedSet = new Set();

    if (_ttsPlayer) clearInterval(_ttsPlayer);

    // Vòng lặp Timer Độc lập (250ms = 4 lần/giây) chống tráo thẻ video của Coursera
    _ttsPlayer = setInterval(() => {
      if (!_isDubbing) return;

      // 1. Luôn truy vấn thẻ video trực tiếp từ DOM
      const currentVideo = document.querySelector('video');
      if (!currentVideo) return;

      const currentTime = currentVideo.currentTime;

      // Reset danh sách đã phát khi user tua video
      if (Math.abs(currentTime - lastTime) > 1.5) {
        playedSet.clear();
      }
      lastTime = currentTime;

      if (currentVideo.paused) return;

      // 2. Duyệt qua mảng phụ đề
      const translated = config.subtitles || window.translatedSubtitles || [];
      for (let i = 0; i < translated.length; i++) {
        let sub = translated[i];

        if (currentTime >= sub.startTime && !sub.isPlayed && !playedSet.has(i)) {
          sub.isPlayed = true;
          playedSet.add(i);

          console.log(`[VI-Sub] Đang phát câu: ${sub.text}`);

          if (sub.audioUrl) {
            let audio = new Audio(sub.audioUrl);
            currentVideo.volume = config.duckVolume ?? 0.15;

            let playPromise = audio.play();
            if (playPromise !== undefined) {
              playPromise.then(() => {
                console.log("[VI-Sub] Phát audio thành công!");
              }).catch(err => {
                console.error("[VI-Sub] Trình duyệt chặn phát âm thanh:", err);
              });
            }

            audio.onended = () => {
              currentVideo.volume = 1.0;
            };
          }
        }
      }
    }, 250);

    // Báo cáo đã bắt đầu
    chrome.runtime.sendMessage({
      action: 'IFRAME_STATUS_REPORT',
      status: 'DUBBING_STARTED',
      data:   { iframeUrl: location.href }
    });
  }

  /** Biến lưu trạng thái pipeline để có thể dừng */
  let _isDubbing    = false;
  let _ttsPlayer    = null;  // Reference tới TTS player instance

  function stopDubbingPipeline() {
    _isDubbing = false;

    if (_ttsPlayer) {
      clearInterval(_ttsPlayer);
      _ttsPlayer = null;
    }

    // Khôi phục âm lượng video gốc
    const video = document.querySelector('video');
    if (video) video.volume = 1.0;

    console.log('[Content - Iframe] Đã dừng dubbing pipeline.');
  }

  /**
   * Giảm âm lượng video gốc để tiếng lồng nghe rõ hơn
   * Dùng Web Audio API để kiểm soát mịn hơn (fade in/out)
   */
  function applyAudioDucking(video, targetVolume) {
    // Cách đơn giản: set volume trực tiếp
    // video.volume = targetVolume;

    // Cách tốt hơn: fade dần để tránh giật âm thanh
    const FADE_DURATION = 500; // ms
    const STEPS         = 20;
    const stepTime      = FADE_DURATION / STEPS;
    const stepValue     = (video.volume - targetVolume) / STEPS;

    let step = 0;
    const fadeInterval = setInterval(() => {
      step++;
      video.volume = Math.max(targetVolume, video.volume - stepValue);
      if (step >= STEPS) clearInterval(fadeInterval);
    }, stepTime);
  }

  // ─────────────────────────────────────────────────────────────────────────
  // safePlay – Phát audio an toàn, bắt lỗi Autoplay Policy của Chrome
  // ─────────────────────────────────────────────────────────────────────────
  //
  // Vấn đề:
  //   Chrome áp dụng "Autoplay Policy": audio.play() bị chặn và throw
  //   NotAllowedError nếu trang chưa có "user gesture" (click/tap/keypress).
  //   Lệnh .play() trả về Promise – nếu không .catch() thì lỗi im lặng,
  //   audio không phát, extension im ru, rất khó debug.
  //
  // Giải pháp:
  //   1. Luôn await/catch Promise của .play()
  //   2. Nếu lỗi NotAllowedError → hiện toast yêu cầu user click vào video
  //   3. Nếu lỗi khác (src rỗng, format không hỗ trợ) → log chi tiết để debug
  //
  // Cách dùng trong TTS player của bạn:
  //   const audio = new Audio(ttsUrl);
  //   await safePlay(audio, subtitleText);
  //
  // @param {HTMLAudioElement} audio   - Object Audio cần phát
  // @param {string}           label   - Nhãn để debug (câu phụ đề đang phát)
  // @returns {Promise<boolean>}        - true nếu phát được, false nếu bị chặn
  // ─────────────────────────────────────────────────────────────────────────
  async function safePlay(audio, label = '') {
    console.log(`[VI-Sub] Thử phát audio: "${label.slice(0, 40)}..."`);

    try {
      await audio.play();
      console.log(`[VI-Sub] ✅ Phát THÀNH CÔNG: "${label.slice(0, 40)}"`);
      return true;

    } catch (err) {

      // ── Lỗi 1: Trình duyệt chặn do chưa có user gesture ─────────────────
      if (err.name === 'NotAllowedError') {
        console.warn('[VI-Sub] ⛔ Autoplay bị chặn. Chrome yêu cầu user phải click vào trang trước.');

        // Thông báo lên top window để hiện hướng dẫn cho user
        chrome.runtime.sendMessage({
          action: 'IFRAME_STATUS_REPORT',
          status: 'ERROR',
          data:   {
            message:   'Autoplay bị chặn – hãy click vào video một lần rồi thử lại 🔊 VI',
            errorName: 'NotAllowedError'
          }
        });

        // Fallback: Gắn listener phát audio khi user tương tác lần kế
        schedulePlayOnNextGesture(audio, label);
        return false;
      }

      // ── Lỗi 2: File audio lỗi / src rỗng / codec không hỗ trợ ───────────
      if (err.name === 'NotSupportedError') {
        console.error('[VI-Sub] ❌ Định dạng audio không được hỗ trợ. Kiểm tra src:', audio.src);
        return false;
      }

      // ── Lỗi 3: Mạng – TTS API chưa trả về file kịp ──────────────────────
      if (err.name === 'AbortError') {
        console.warn('[VI-Sub] ⏳ audio.play() bị abort (có thể do load chưa xong). Sẽ thử lại...');
        // Thử lại sau 300ms để đợi audio load
        await new Promise(r => setTimeout(r, 300));
        return safePlay(audio, label + ' [retry]');
      }

      // ── Lỗi 4: Không xác định ────────────────────────────────────────────
      console.error('[VI-Sub] ❌ Lỗi không xác định khi play():', err.name, err.message);
      return false;
    }
  }

  /**
   * Fallback khi autoplay bị chặn:
   * Lắng nghe lần tương tác kế tiếp của user (click/keydown) rồi phát audio.
   * Giải quyết trường hợp user bật extension TRƯỚC khi click vào video.
   *
   * @param {HTMLAudioElement} audio
   * @param {string} label
   */
  function schedulePlayOnNextGesture(audio, label) {
    const events = ['click', 'keydown', 'touchstart'];

    function onGesture() {
      // Dọn listener sau khi dùng xong
      events.forEach(e => document.removeEventListener(e, onGesture, { once: true }));
      console.log('[VI-Sub] Đã phát hiện gesture – thử phát lại audio:', label);
      safePlay(audio, label + ' [after-gesture]');
    }

    events.forEach(e => document.addEventListener(e, onGesture, { once: true, passive: true }));
    console.log('[VI-Sub] Đang chờ user gesture để phát audio...');
  }

})();
// ─── Kết thúc IIFE ─── Toàn bộ code được bọc để tránh pollution global scope
