/**
 * YouTube VI Subtitle Translator - Content Script
 *
 * Luồng hoạt động:
 * 1. Chờ container phụ đề YouTube xuất hiện trong DOM.
 * 2. Dùng MutationObserver để theo dõi thay đổi bên trong container đó.
 * 3. Khi phát hiện text phụ đề mới, debounce 400ms rồi gọi API dịch.
 * 4. Cache kết quả dịch để không gọi lại cùng 1 câu trong 1 giây.
 * 5. Chèn bản dịch tiếng Việt vào DOM ngay bên dưới dòng tiếng Anh.
 */

const API_URL = "http://127.0.0.1:8000/api/translate";

// --- State ---
let observer = null;
let debounceTimer = null;
let translationCache = new Map(); // Map<englishText, { viText, timestamp }>
const CACHE_TTL_MS = 1000; // Không dịch lại cùng 1 câu trong 1 giây
const DEBOUNCE_DELAY_MS = 400; // Đợi YouTube ngừng roll-up mới gọi API

// --- Selector YouTube phụ đề ---
// YouTube có thể dùng nhiều container khác nhau tùy phiên bản
const CAPTION_CONTAINER_SELECTORS = [
  ".ytp-caption-window-container",
  ".caption-window",
  "#movie_player .captions-text",
];

const CAPTION_SEGMENT_SELECTOR = ".ytp-caption-segment";
const VI_CLASS = "vi-translated-sub";

// --- Utility ---

/**
 * Lấy toàn bộ text hiện tại từ tất cả các segment phụ đề đang hiển thị.
 * YouTube đôi khi chia 1 câu thành nhiều <span> nhỏ.
 */
function getCurrentCaptionText() {
  const segments = document.querySelectorAll(CAPTION_SEGMENT_SELECTOR);
  const parts = [];
  segments.forEach((seg) => {
    // Bỏ qua những span là bản dịch do chính extension chèn vào
    if (!seg.closest("." + VI_CLASS)) {
      const text = seg.innerText.trim();
      if (text) parts.push(text);
    }
  });
  return parts.join(" ").trim();
}

/**
 * Xóa tất cả các bản dịch tiếng Việt đã chèn trước đó để tránh nhân bản.
 */
function clearExistingTranslations() {
  document.querySelectorAll("." + VI_CLASS).forEach((el) => el.remove());
}

/**
 * Gọi API backend để dịch text sang tiếng Việt.
 * Dùng FormData theo đúng spec.
 */
async function fetchTranslation(englishText) {
  const formData = new FormData();
  formData.append("text", englishText);

  const response = await fetch(API_URL, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  const data = await response.json();
  // Backend trả về JSON, lấy field "translation" (hoặc "translated_text")
  return data.translation || data.translated_text || data.result || "";
}

/**
 * Chèn span tiếng Việt vào DOM sau caption segment cuối cùng.
 */
function injectTranslation(viText) {
  clearExistingTranslations();

  if (!viText) return;

  // Tìm caption window đang active để chèn vào đúng chỗ
  let targetParent = null;

  for (const selector of CAPTION_CONTAINER_SELECTORS) {
    const container = document.querySelector(selector);
    if (container) {
      targetParent = container;
      break;
    }
  }

  if (!targetParent) return;

  const viSpan = document.createElement("span");
  viSpan.className = VI_CLASS;
  viSpan.textContent = viText;

  // Chèn vào cuối container phụ đề
  targetParent.appendChild(viSpan);
}

/**
 * Hàm chính: kiểm tra cache → gọi API → chèn DOM.
 */
async function processCaption() {
  const englishText = getCurrentCaptionText();

  if (!englishText) {
    clearExistingTranslations();
    return;
  }

  // Kiểm tra cache
  const cached = translationCache.get(englishText);
  if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) {
    injectTranslation(cached.viText);
    return;
  }

  try {
    const viText = await fetchTranslation(englishText);

    if (viText) {
      // Lưu vào cache
      translationCache.set(englishText, { viText, timestamp: Date.now() });

      // Giữ cache nhỏ gọn (max 50 entries)
      if (translationCache.size > 50) {
        const firstKey = translationCache.keys().next().value;
        translationCache.delete(firstKey);
      }

      injectTranslation(viText);
    }
  } catch (err) {
    // Không throw để tránh làm chết observer
    console.warn("[YT-VI-Sub] API error:", err.message);
  }
}

/**
 * Debounced wrapper: đợi YouTube ngừng cập nhật DOM mới gọi processCaption.
 */
function onCaptionMutation() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(processCaption, DEBOUNCE_DELAY_MS);
}

/**
 * Khởi động MutationObserver sau khi tìm được container phụ đề.
 */
function startObserver(captionContainer) {
  if (observer) {
    observer.disconnect();
  }

  observer = new MutationObserver(onCaptionMutation);

  observer.observe(captionContainer, {
    childList: true,
    subtree: true,
    characterData: true,
  });

  console.log("[YT-VI-Sub] Observer started on:", captionContainer);
}

/**
 * Dùng một observer phụ để chờ container phụ đề xuất hiện,
 * vì YouTube là SPA và container không có sẵn ngay khi load trang.
 */
function waitForCaptionContainer() {
  // Thử tìm ngay lập tức trước
  for (const selector of CAPTION_CONTAINER_SELECTORS) {
    const el = document.querySelector(selector);
    if (el) {
      startObserver(el);
      return;
    }
  }

  // Nếu chưa có, dùng observer toàn trang chờ xuất hiện
  const bodyObserver = new MutationObserver(() => {
    for (const selector of CAPTION_CONTAINER_SELECTORS) {
      const el = document.querySelector(selector);
      if (el) {
        bodyObserver.disconnect();
        startObserver(el);
        return;
      }
    }
  });

  bodyObserver.observe(document.body, { childList: true, subtree: true });
}

// --- Xử lý YouTube SPA navigation ---
// YouTube dùng pushState/popState nên cần reset khi đổi video
let lastUrl = location.href;

const navigationObserver = new MutationObserver(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href;

    // Reset state khi chuyển video
    if (observer) observer.disconnect();
    clearExistingTranslations();
    translationCache.clear();

    // Chờ player mới load xong
    setTimeout(waitForCaptionContainer, 1500);
  }
});

navigationObserver.observe(document.body, { childList: true, subtree: true });

// --- Khởi động ---
waitForCaptionContainer();
console.log("[YT-VI-Sub] Extension loaded.");
