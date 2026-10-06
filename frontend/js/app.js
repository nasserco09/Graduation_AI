/**
 * Visual Fashion Search - بحث الملابس بالصور
 * ES6+ JavaScript with modular structure & interactive enhancements
 */

// ===================================
// Configuration
// ===================================
const CONFIG = {
    SEARCH_ENDPOINT: '/api/search',
    SEGMENT_ENDPOINT: '/api/segment',
    REINDEX_ENDPOINT: '/api/reindex',
    FEEDBACK_ENDPOINT: '/api/feedback',
    MAX_FILE_SIZE: 8 * 1024 * 1024,    // 8MB in bytes
    ALLOWED_TYPES: ['image/png', 'image/jpeg', 'image/jpg', 'image/webp'],
    TOAST_DURATION: 4000,               // 4 seconds
    ENABLE_CLIENT_RESIZE: false,        // Keep backend input identical to the tested AI pipeline
    MAX_IMAGE_WIDTH: 800
};

// ===================================
// DOM Selectors
// ===================================
const DOM = {
    // Upload elements
    dropZone: document.getElementById('drop-zone'),
    dropZoneContent: document.getElementById('drop-zone-content'),
    fileInput: document.getElementById('file-input'),
    browseFilesBtn: document.getElementById('browse-files-btn'),
    previewContainer: document.getElementById('preview-container'),
    previewImage: document.getElementById('preview-image'),
    previewImageWrap: document.getElementById('preview-image-wrap'),
    previewBadge: document.getElementById('preview-badge'),
    segmentationMask: document.getElementById('segmentation-mask'),
    selectionCanvas: document.getElementById('selection-canvas'),
    aiPointsLayer: document.getElementById('ai-points-layer'),
    removeImageBtn: document.getElementById('remove-image'),

    // SAM2 selection
    selectionPanel: document.getElementById('selection-panel'),
    aiSelectionWorkspace: document.getElementById('ai-selection-workspace'),
    modeFullBtn: document.getElementById('mode-full-btn'),
    modeAiBtn: document.getElementById('mode-ai-btn'),
    modeRectBtn: document.getElementById('mode-rect-btn'),
    modePolyBtn: document.getElementById('mode-poly-btn'),
    modeFreeBtn: document.getElementById('mode-free-btn'),
    manualSelectionWorkspace: document.getElementById('manual-selection-workspace'),
    manualSelectionInstruction: document.getElementById('manual-selection-instruction'),
    manualSelectionStatus: document.getElementById('manual-selection-status'),
    finishPolygonBtn: document.getElementById('finish-polygon-btn'),
    clearManualSelectionBtn: document.getElementById('clear-manual-selection-btn'),
    selectionStatus: document.getElementById('selection-status'),
    selectionResult: document.getElementById('selection-result'),
    selectionConfidence: document.getElementById('selection-confidence'),
    cutoutPreview: document.getElementById('cutout-preview'),
    acceptSelectionBtn: document.getElementById('accept-selection-btn'),
    resetSelectionBtn: document.getElementById('reset-selection-btn'),
    progressContainer: document.getElementById('progress-container'),
    progressFill: document.getElementById('progress-fill'),
    progressText: document.getElementById('progress-text'),
    queryPreviewPanel: document.getElementById('query-preview-panel'),
    queryPreviewImage: document.getElementById('query-preview-image'),
    queryPreviewMode: document.getElementById('query-preview-mode'),
    queryPreviewSize: document.getElementById('query-preview-size'),
    queryPreviewVerification: document.getElementById('query-preview-verification'),
    categoryRoutingStatus: document.getElementById('category-routing-status'),

    // Samples
    samplesContainer: document.getElementById('samples-container'),

    // Options
    categoryModeSelect: document.getElementById('category-mode'),
    topKSelect: document.getElementById('top-k'),
    viewGridBtn: document.getElementById('view-grid'),
    viewListBtn: document.getElementById('view-list'),
    searchBtn: document.getElementById('search-btn'),

    // Results
    resultsSection: document.getElementById('results-section'),
    resultsGrid: document.getElementById('results-grid'),
    resultsCount: document.getElementById('results-count'),
    filterChips: document.querySelectorAll('.filter-chip'),
    filterChipsContainer: document.getElementById('filter-chips'),
    feedbackPanel: document.getElementById('feedback-panel'),
    feedbackNoMatchBtn: document.getElementById('feedback-no-match-btn'),
    feedbackWrongCategoryBtn: document.getElementById('feedback-wrong-category-btn'),
    feedbackStatus: document.getElementById('feedback-status'),

    // Loading
    loadingOverlay: document.getElementById('loading-overlay'),

    // Product Modal
    productModal: document.getElementById('product-modal'),
    modalBackdrop: document.getElementById('modal-backdrop'),
    modalClose: document.getElementById('modal-close'),
    modalImage: document.getElementById('modal-image'),
    modalTitle: document.getElementById('modal-title'),
    modalProductId: document.getElementById('modal-product-id'),
    modalSimilarity: document.getElementById('modal-similarity'),
    modalImageUrl: document.getElementById('modal-image-url'),
    modalProductLink: document.getElementById('modal-product-link'),
    modalCopyLink: document.getElementById('modal-copy-link'),
    modalDownload: document.getElementById('modal-download'),

    // About Modal
    aboutBtn: document.getElementById('about-btn'),
    aboutModal: document.getElementById('about-modal'),
    aboutBackdrop: document.getElementById('about-backdrop'),
    aboutClose: document.getElementById('about-close'),

    // Camera Modal
    cameraBtn: document.getElementById('camera-btn'),
    cameraModal: document.getElementById('camera-modal'),
    cameraBackdrop: document.getElementById('camera-backdrop'),
    cameraClose: document.getElementById('camera-close'),
    cameraVideo: document.getElementById('camera-video'),
    cameraCanvas: document.getElementById('camera-canvas'),
    cameraCaptureBtn: document.getElementById('camera-capture-btn'),

    // Back to Top
    backToTopBtn: document.getElementById('back-to-top'),

    // Theme
    themeToggle: document.getElementById('theme-toggle'),

    // Toast
    toastContainer: document.getElementById('toast-container')
};

// ===================================
// State Management
// ===================================
let state = {
    selectedFile: null,
    currentView: 'grid',
    results: [],
    filteredResults: [],
    selectedCategory: 'all',
    lastQuery: null,
    isDarkMode: false,
    cameraStream: null,
    searchMode: 'full',
    aiMaskDataUrl: null,
    aiCutoutDataUrl: null,
    aiScore: null,
    aiAccepted: false,
    aiBusy: false,
    aiRequestVersion: 0,
    aiPoints: [],
    drawing: false,
    startPoint: null,
    rectangle: null,
    polygonPoints: [],
    polygonFinished: false,
    freePoints: [],
    queryPreviewUrl: null,
    querySha256: null,
    currentSearchId: null
};

// ===================================
// Utility Functions
// ===================================

/**
 * Format similarity score as percentage
 * @param {number} score - Similarity score (0-1)
 * @returns {string} Formatted percentage string
 */
function formatSimilarity(score) {
    return Math.round(score * 100) + '%';
}

/**
 * Get similarity level class based on score
 * @param {number} score - Similarity score (0-1)
 * @returns {string} CSS class name
 */
function getSimilarityClass(score) {
    if (score >= 0.8) return 'similarity-high';
    if (score >= 0.5) return 'similarity-medium';
    return 'similarity-low';
}

/**
 * Validate file type and size
 * @param {File} file - File to validate
 * @returns {{valid: boolean, error: string|null}}
 */
function validateFile(file) {
    if (!file) return { valid: false, error: 'لم يتم اختيار ملف' };
    if (!CONFIG.ALLOWED_TYPES.includes(file.type)) {
        return { valid: false, error: 'نوع الملف غير مدعوم. يرجى اختيار صورة (PNG, JPG, WebP)' };
    }
    if (file.size > CONFIG.MAX_FILE_SIZE) {
        const maxMB = CONFIG.MAX_FILE_SIZE / (1024 * 1024);
        return { valid: false, error: `حجم الملف كبير جداً. الحد الأقصى ${maxMB}MB` };
    }
    return { valid: true, error: null };
}

/**
 * Resize image on client side
 * @param {File|Blob} file - Image file
 * @param {number} maxWidth - Maximum width
 * @returns {Promise<Blob>}
 */
async function resizeImage(file, maxWidth) {
    return new Promise((resolve) => {
        const img = new Image();
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');

        img.onload = () => {
            let { width, height } = img;
            
            if (width > maxWidth) {
                height = (height * maxWidth) / width;
                width = maxWidth;
            }

            canvas.width = width;
            canvas.height = height;
            ctx.drawImage(img, 0, 0, width, height);

            canvas.toBlob((blob) => {
                resolve(blob || file);
            }, file.type || 'image/jpeg', 0.85);
        };

        img.onerror = () => resolve(file);
        img.src = URL.createObjectURL(file);
    });
}

/**
 * Copy text to clipboard
 * @param {string} text - Text to copy
 * @returns {Promise<boolean>}
 */
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch {
        return false;
    }
}


/** Convert a data URL returned by SAM2 into a Blob for /api/search. */
async function dataUrlToBlob(dataUrl) {
    const response = await fetch(dataUrl);
    return await response.blob();
}

function searchModeLabel(mode) {
    const labels = {
        full: 'الصورة كاملة',
        ai: 'تحديد ذكي بواسطة SAM2',
        rect: 'تحديد مستطيل',
        poly: 'تحديد مضلع',
        free: 'رسم حر'
    };
    return labels[mode] || labels.full;
}

async function sha256Hex(blob) {
    if (!window.crypto?.subtle) return null;
    const bytes = await blob.arrayBuffer();
    const hash = await window.crypto.subtle.digest('SHA-256', bytes);
    return Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, '0')).join('');
}

function clearQueryPreview() {
    if (state.queryPreviewUrl) URL.revokeObjectURL(state.queryPreviewUrl);
    state.queryPreviewUrl = null;
    state.querySha256 = null;
    if (DOM.queryPreviewPanel) DOM.queryPreviewPanel.hidden = true;
    if (DOM.queryPreviewImage) DOM.queryPreviewImage.removeAttribute('src');
    if (DOM.queryPreviewVerification) {
        DOM.queryPreviewVerification.className = 'query-preview-verification';
        DOM.queryPreviewVerification.textContent = 'سيتم التحقق منها عند وصول رد الخادم.';
    }
    if (DOM.categoryRoutingStatus) {
        DOM.categoryRoutingStatus.className = 'category-routing-status';
        DOM.categoryRoutingStatus.textContent = 'سيظهر نوع القطعة المتوقع بعد البحث.';
    }
}

async function showQueryPreview(blob, mode) {
    clearQueryPreview();
    state.queryPreviewUrl = URL.createObjectURL(blob);
    try {
        state.querySha256 = await sha256Hex(blob);
    } catch {
        state.querySha256 = null;
    }
    if (DOM.queryPreviewImage) DOM.queryPreviewImage.src = state.queryPreviewUrl;
    if (DOM.queryPreviewMode) DOM.queryPreviewMode.textContent = `طريقة البحث: ${searchModeLabel(mode)}`;
    if (DOM.queryPreviewSize) DOM.queryPreviewSize.textContent = `حجم الملف: ${(blob.size / 1024).toFixed(1)} كيلوبايت`;
    if (DOM.queryPreviewPanel) DOM.queryPreviewPanel.hidden = false;
    return state.querySha256;
}

function verifyQueryReceipt(query) {
    if (!DOM.queryPreviewVerification) return;
    const serverHash = query?.sha256 || null;
    if (!state.querySha256 || !serverHash) {
        DOM.queryPreviewVerification.textContent = 'تعذر التحقق من البصمة في هذا المتصفح.';
        return;
    }
    const verified = state.querySha256 === serverHash;
    DOM.queryPreviewVerification.className = `query-preview-verification ${verified ? 'verified' : 'mismatch'}`;
    DOM.queryPreviewVerification.textContent = verified
        ? `تم التحقق: الخادم استلم نفس الصورة تمامًا • ${serverHash.slice(0, 12)}`
        : 'تحذير: الصورة المستلمة لا تطابق الصورة المعروضة.';
}

function renderCategoryRouting(query) {
    if (!DOM.categoryRoutingStatus) return;
    const routing = query?.category_routing;
    if (!routing) {
        DOM.categoryRoutingStatus.textContent = 'لم تصل معلومات تصنيف القطعة من الخادم.';
        return;
    }

    const confidence = Math.round(Number(routing.confidence || 0) * 100);
    if (routing.requested_category === 'auto') {
        DOM.categoryRoutingStatus.className = 'category-routing-status detected';
        DOM.categoryRoutingStatus.textContent = routing.applied_label
            ? `تعرّف النظام على: ${routing.applied_label} • ثقة داخل الكتالوج: ${confidence}% • تم حصر النتائج في هذا النوع.`
            : 'لم يتمكن النظام من تحديد نوع القطعة، لذلك لم يطبق فلترة.';
    } else if (routing.requested_category === 'all') {
        DOM.categoryRoutingStatus.className = 'category-routing-status';
        DOM.categoryRoutingStatus.textContent = `التوقع الآلي: ${routing.predicted_label || 'غير معروف'} • اخترت عرض جميع الأنواع دون فلترة.`;
    } else {
        DOM.categoryRoutingStatus.className = 'category-routing-status manual';
        DOM.categoryRoutingStatus.textContent = `تم تطبيق تصحيح المستخدم وحصر النتائج في: ${routing.applied_label || routing.applied_category}.`;
    }
}

/** Turn FastAPI validation errors into readable text instead of [object Object]. */
function formatApiErrorDetail(detail) {
    if (!detail) return '';
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
        return detail.map((item) => {
            if (typeof item === 'string') return item;
            if (item && typeof item === 'object') {
                const location = Array.isArray(item.loc) ? item.loc.join(' → ') : '';
                const message = item.msg || item.message || JSON.stringify(item);
                return location ? `${location}: ${message}` : message;
            }
            return String(item);
        }).join(' | ');
    }
    if (typeof detail === 'object') return detail.message || detail.msg || JSON.stringify(detail);
    return String(detail);
}

/** Read JSON while preserving FastAPI's detail message on errors. */
async function readApiJson(response) {
    let data = {};
    try {
        data = await response.json();
    } catch {
        // Keep a predictable error object if the server returned non-JSON content.
    }
    if (!response.ok) {
        const raw = data.detail ?? data.message ?? `HTTP ${response.status}`;
        throw new Error(formatApiErrorDetail(raw));
    }
    return data;
}

/** Extract a readable identifier from a backend image URL. */
function getResultId(url, index) {
    if (!url) return `RESULT-${index + 1}`;
    try {
        const pathname = new URL(url, window.location.href).pathname;
        const name = decodeURIComponent(pathname.split('/').filter(Boolean).pop() || '');
        return name || `RESULT-${index + 1}`;
    } catch {
        return `RESULT-${index + 1}`;
    }
}

/** Adapt the tested backend contract ({url, score}) to the richer existing UI contract. */
function normalizeSearchResponse(data) {
    const rawResults = Array.isArray(data?.results) ? data.results : [];
    return {
        query_image_url: state.queryPreviewUrl || DOM.previewImage?.src || null,
        query: data?.query || null,
        results: rawResults.map((item, index) => {
            const imageUrl = item.image_url || item.url || '';
            const similarity = Number(item.similarity ?? item.score ?? 0);
            return {
                ...item,
                product_id: item.product_id || getResultId(imageUrl, index),
                image_url: imageUrl,
                title: item.title || `نتيجة مشابهة ${index + 1}`,
                category: item.category || null,
                color: item.color || null,
                sizes: item.sizes || [],
                similarity: Number.isFinite(similarity) ? similarity : 0,
                product_url: item.product_url || null
            };
        })
    };
}

function escapeHtml(value) {
    const element = document.createElement('span');
    element.textContent = String(value ?? '');
    return element.innerHTML;
}

function safeHttpUrl(value) {
    if (!value) return '';
    try {
        const url = new URL(value, window.location.href);
        return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
    } catch {
        return '';
    }
}

const MANUAL_MODES = new Set(['rect', 'poly', 'free']);

function isManualMode(mode = state.searchMode) {
    return MANUAL_MODES.has(mode);
}

function hasManualSelection() {
    if (state.searchMode === 'rect') {
        return Boolean(state.rectangle && Math.abs(state.rectangle.width) >= 3 && Math.abs(state.rectangle.height) >= 3);
    }
    if (state.searchMode === 'poly') {
        return state.polygonFinished && state.polygonPoints.length >= 3;
    }
    if (state.searchMode === 'free') {
        return state.freePoints.length >= 3;
    }
    return false;
}

function updateSearchButtonState() {
    if (!DOM.searchBtn) return;
    const hasFile = Boolean(state.selectedFile);
    let selectionReady = true;

    if (state.searchMode === 'ai') selectionReady = state.aiAccepted;
    if (isManualMode()) selectionReady = hasManualSelection();

    DOM.searchBtn.disabled = !hasFile || !selectionReady || state.aiBusy;

    const label = DOM.searchBtn.querySelector('.btn-search-inner span');
    if (!label) return;

    const labels = {
        full: 'ابحث الآن بالصورة كاملة',
        ai: state.aiAccepted ? 'ابحث عن القطعة المحددة' : 'حدد القطعة واعتمدها أولاً',
        rect: hasManualSelection() ? 'ابحث داخل المستطيل' : 'ارسم مستطيلاً على القطعة أولاً',
        poly: hasManualSelection() ? 'ابحث داخل المضلع' : 'حدد المضلع ثم اضغط إنهاء المضلع',
        free: hasManualSelection() ? 'ابحث داخل الرسم الحر' : 'ارسم حول القطعة أولاً'
    };
    label.textContent = labels[state.searchMode] || labels.full;
}

function renderAIPoints() {
    if (!DOM.aiPointsLayer) return;
    DOM.aiPointsLayer.innerHTML = '';
    DOM.aiPointsLayer.hidden = state.searchMode !== 'ai' || state.aiPoints.length === 0;

    state.aiPoints.forEach((point, index) => {
        const marker = document.createElement('span');
        marker.className = `ai-point-marker ${point.label === 0 ? 'negative' : 'positive'}`;
        marker.style.left = `${point.leftPct}%`;
        marker.style.top = `${point.topPct}%`;
        marker.textContent = point.label === 0 ? '−' : '+';
        marker.title = point.label === 0 ? `نقطة استبعاد ${index + 1}` : `نقطة اختيار ${index + 1}`;
        DOM.aiPointsLayer.appendChild(marker);
    });
}

function aiPromptSummary() {
    const positives = state.aiPoints.filter(p => p.label === 1).length;
    const negatives = state.aiPoints.filter(p => p.label === 0).length;
    return `${positives} نقطة اختيار${negatives ? ` • ${negatives} استبعاد` : ''}`;
}

function resetAISelection({ keepMode = true } = {}) {
    // Invalidate pending responses before clearing or replacing the image.
    state.aiRequestVersion += 1;
    clearQueryPreview();
    state.aiMaskDataUrl = null;
    state.aiCutoutDataUrl = null;
    state.aiScore = null;
    state.aiAccepted = false;
    state.aiBusy = false;
    state.aiPoints = [];

    if (DOM.segmentationMask) {
        DOM.segmentationMask.src = '';
        DOM.segmentationMask.hidden = true;
        DOM.segmentationMask.classList.remove('accepted');
    }
    renderAIPoints();
    if (DOM.selectionResult) DOM.selectionResult.hidden = true;
    if (DOM.cutoutPreview) DOM.cutoutPreview.src = '';
    if (DOM.selectionConfidence) DOM.selectionConfidence.textContent = '—';
    if (DOM.acceptSelectionBtn) DOM.acceptSelectionBtn.disabled = true;
    if (DOM.resetSelectionBtn) DOM.resetSelectionBtn.disabled = true;
    if (DOM.previewBadge) {
        DOM.previewBadge.classList.remove('ai-badge');
        const badgeText = DOM.previewBadge.querySelector('span');
        if (badgeText) badgeText.textContent = 'تم اختيار الصورة';
    }
    if (DOM.selectionStatus) {
        DOM.selectionStatus.className = 'selection-status';
        DOM.selectionStatus.innerHTML = '<i class="fas fa-computer-mouse"></i> كليك يسار = مطلوب، كليك يمين = استبعاد.';
    }

    if (!keepMode) state.searchMode = 'full';
    updateSearchButtonState();
}

function resetManualSelection() {
    clearQueryPreview();
    state.drawing = false;
    state.startPoint = null;
    state.rectangle = null;
    state.polygonPoints = [];
    state.polygonFinished = false;
    state.freePoints = [];

    if (DOM.manualSelectionStatus) {
        DOM.manualSelectionStatus.className = 'selection-status';
        DOM.manualSelectionStatus.textContent = 'في انتظار التحديد...';
    }
    if (DOM.finishPolygonBtn) DOM.finishPolygonBtn.disabled = true;
    if (DOM.clearManualSelectionBtn) DOM.clearManualSelectionBtn.disabled = true;
    drawManualSelection();
    updateSearchButtonState();
}

function setSearchMode(mode) {
    const allowed = new Set(['full', 'ai', 'rect', 'poly', 'free']);
    state.searchMode = allowed.has(mode) ? mode : 'full';
    clearQueryPreview();

    const buttons = [
        [DOM.modeFullBtn, 'full'],
        [DOM.modeAiBtn, 'ai'],
        [DOM.modeRectBtn, 'rect'],
        [DOM.modePolyBtn, 'poly'],
        [DOM.modeFreeBtn, 'free']
    ];
    buttons.forEach(([button, value]) => {
        if (!button) return;
        const active = state.searchMode === value;
        button.classList.toggle('active', active);
        button.setAttribute('aria-checked', active.toString());
    });

    if (DOM.aiSelectionWorkspace) DOM.aiSelectionWorkspace.hidden = state.searchMode !== 'ai';
    if (DOM.manualSelectionWorkspace) DOM.manualSelectionWorkspace.hidden = !isManualMode();
    if (DOM.previewImageWrap) {
        DOM.previewImageWrap.classList.toggle('ai-select-active', state.searchMode === 'ai');
        DOM.previewImageWrap.classList.toggle('manual-select-active', isManualMode());
    }
    if (DOM.selectionCanvas) {
        DOM.selectionCanvas.hidden = !isManualMode();
        DOM.selectionCanvas.classList.toggle('active', isManualMode());
    }

    if (state.searchMode === 'full') {
        if (DOM.segmentationMask) DOM.segmentationMask.hidden = true;
        if (DOM.aiPointsLayer) DOM.aiPointsLayer.hidden = true;
    } else if (state.searchMode === 'ai') {
        if (state.aiMaskDataUrl && DOM.segmentationMask) DOM.segmentationMask.hidden = false;
        if (DOM.aiPointsLayer) DOM.aiPointsLayer.hidden = false;
        renderAIPoints();
    } else {
        if (DOM.segmentationMask) DOM.segmentationMask.hidden = true;
        if (DOM.aiPointsLayer) DOM.aiPointsLayer.hidden = true;
        ensureSelectionCanvasSize();
        drawManualSelection();
        updateManualInstructions();
    }

    if (DOM.finishPolygonBtn) {
        DOM.finishPolygonBtn.hidden = state.searchMode !== 'poly';
        DOM.finishPolygonBtn.disabled = state.searchMode !== 'poly' || state.polygonPoints.length < 3 || state.polygonFinished;
    }
    updateSearchButtonState();
}

function ensureSelectionCanvasSize() {
    if (!DOM.selectionCanvas || !DOM.previewImage || !DOM.previewImage.naturalWidth || !DOM.previewImage.naturalHeight) return;
    if (DOM.selectionCanvas.width !== DOM.previewImage.naturalWidth) DOM.selectionCanvas.width = DOM.previewImage.naturalWidth;
    if (DOM.selectionCanvas.height !== DOM.previewImage.naturalHeight) DOM.selectionCanvas.height = DOM.previewImage.naturalHeight;
}

function getSelectionPoint(event) {
    if (!DOM.selectionCanvas) return null;
    const rect = DOM.selectionCanvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    const x = (event.clientX - rect.left) * DOM.selectionCanvas.width / rect.width;
    const y = (event.clientY - rect.top) * DOM.selectionCanvas.height / rect.height;
    return {
        x: Math.max(0, Math.min(DOM.selectionCanvas.width, x)),
        y: Math.max(0, Math.min(DOM.selectionCanvas.height, y))
    };
}

function drawManualSelection() {
    if (!DOM.selectionCanvas) return;
    ensureSelectionCanvasSize();
    const ctx = DOM.selectionCanvas.getContext('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, DOM.selectionCanvas.width, DOM.selectionCanvas.height);

    const scale = Math.max(1, Math.min(DOM.selectionCanvas.width, DOM.selectionCanvas.height) / 350);
    ctx.lineWidth = 3 * scale;
    ctx.strokeStyle = '#6d63ff';
    ctx.fillStyle = 'rgba(109, 99, 255, 0.18)';
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';

    if (state.searchMode === 'rect' && state.rectangle) {
        const r = state.rectangle;
        ctx.fillRect(r.x, r.y, r.width, r.height);
        ctx.strokeRect(r.x, r.y, r.width, r.height);
    }

    if (state.searchMode === 'poly' && state.polygonPoints.length) {
        ctx.beginPath();
        ctx.moveTo(state.polygonPoints[0].x, state.polygonPoints[0].y);
        state.polygonPoints.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
        if (state.polygonFinished) {
            ctx.closePath();
            ctx.fill();
        }
        ctx.stroke();
        state.polygonPoints.forEach((p) => {
            ctx.beginPath();
            ctx.arc(p.x, p.y, 5 * scale, 0, Math.PI * 2);
            ctx.fillStyle = '#6d63ff';
            ctx.fill();
            ctx.fillStyle = 'rgba(109, 99, 255, 0.18)';
        });
    }

    if (state.searchMode === 'free' && state.freePoints.length) {
        ctx.beginPath();
        ctx.moveTo(state.freePoints[0].x, state.freePoints[0].y);
        state.freePoints.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
        if (!state.drawing && state.freePoints.length >= 3) {
            ctx.closePath();
            ctx.fill();
        }
        ctx.stroke();
    }
}

function updateManualInstructions() {
    if (!DOM.manualSelectionInstruction || !DOM.manualSelectionStatus) return;
    const instructions = {
        rect: 'اسحب بالماوس لرسم مستطيل حول القطعة المطلوبة.',
        poly: 'انقر حول حدود القطعة نقطةً نقطة، ثم اضغط «إنهاء المضلع».',
        free: 'اضغط واسحب وارسم حول القطعة بشكل حر، ثم اترك زر الماوس.'
    };
    DOM.manualSelectionInstruction.textContent = instructions[state.searchMode] || '';

    if (hasManualSelection()) {
        DOM.manualSelectionStatus.className = 'selection-status ready';
        DOM.manualSelectionStatus.textContent = 'التحديد جاهز للبحث.';
    } else {
        DOM.manualSelectionStatus.className = 'selection-status';
        DOM.manualSelectionStatus.textContent = 'في انتظار التحديد...';
    }
}

function handleManualPointerDown(event) {
    clearQueryPreview();
    event.stopPropagation();
    event.preventDefault();
    if (!isManualMode() || !DOM.selectionCanvas) return;
    const point = getSelectionPoint(event);
    if (!point) return;

    if (state.searchMode === 'rect') {
        state.drawing = true;
        state.startPoint = point;
        state.rectangle = { x: point.x, y: point.y, width: 0, height: 0 };
    } else if (state.searchMode === 'free') {
        state.drawing = true;
        state.freePoints = [point];
    }
    if (DOM.clearManualSelectionBtn) DOM.clearManualSelectionBtn.disabled = false;
    drawManualSelection();
}

function handleManualPointerMove(event) {
    if (!state.drawing || !isManualMode()) return;
    event.stopPropagation();
    event.preventDefault();
    const point = getSelectionPoint(event);
    if (!point) return;

    if (state.searchMode === 'rect' && state.startPoint) {
        state.rectangle = {
            x: state.startPoint.x,
            y: state.startPoint.y,
            width: point.x - state.startPoint.x,
            height: point.y - state.startPoint.y
        };
    } else if (state.searchMode === 'free') {
        state.freePoints.push(point);
    }
    drawManualSelection();
}

function handleManualPointerUp(event) {
    if (event) {
        event.stopPropagation();
        event.preventDefault();
    }
    if (!state.drawing) return;
    state.drawing = false;
    state.startPoint = null;
    drawManualSelection();
    updateManualInstructions();
    updateSearchButtonState();
}

function handleManualCanvasClick(event) {
    clearQueryPreview();
    event.stopPropagation();
    event.preventDefault();
    if (state.searchMode !== 'poly' || state.polygonFinished) return;
    const point = getSelectionPoint(event);
    if (!point) return;
    state.polygonPoints.push(point);
    if (DOM.finishPolygonBtn) DOM.finishPolygonBtn.disabled = state.polygonPoints.length < 3;
    if (DOM.clearManualSelectionBtn) DOM.clearManualSelectionBtn.disabled = false;
    drawManualSelection();
    updateSearchButtonState();
}

function finishPolygon() {
    if (state.searchMode !== 'poly' || state.polygonPoints.length < 3) return;
    state.polygonFinished = true;
    if (DOM.finishPolygonBtn) DOM.finishPolygonBtn.disabled = true;
    drawManualSelection();
    updateManualInstructions();
    updateSearchButtonState();
}

function normalizedRectangle(rect) {
    const x1 = Math.min(rect.x, rect.x + rect.width);
    const y1 = Math.min(rect.y, rect.y + rect.height);
    const x2 = Math.max(rect.x, rect.x + rect.width);
    const y2 = Math.max(rect.y, rect.y + rect.height);
    return { x: x1, y: y1, width: x2 - x1, height: y2 - y1 };
}

function canvasToBlob(canvas, type = 'image/png', quality = 0.95) {
    return new Promise((resolve, reject) => {
        canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error('تعذر تجهيز منطقة التحديد')), type, quality);
    });
}

async function createManualSelectionBlob() {
    if (!DOM.previewImage || !hasManualSelection()) throw new Error('حدد منطقة صحيحة أولاً');
    const image = DOM.previewImage;

    if (state.searchMode === 'rect') {
        const r = normalizedRectangle(state.rectangle);
        const x = Math.max(0, Math.floor(r.x));
        const y = Math.max(0, Math.floor(r.y));
        const w = Math.max(1, Math.min(image.naturalWidth - x, Math.ceil(r.width)));
        const h = Math.max(1, Math.min(image.naturalHeight - y, Math.ceil(r.height)));
        const out = document.createElement('canvas');
        out.width = w;
        out.height = h;
        out.getContext('2d').drawImage(image, x, y, w, h, 0, 0, w, h);
        return canvasToBlob(out, 'image/jpeg', 0.95);
    }

    const points = state.searchMode === 'poly' ? state.polygonPoints : state.freePoints;
    const minX = Math.max(0, Math.floor(Math.min(...points.map(p => p.x))));
    const minY = Math.max(0, Math.floor(Math.min(...points.map(p => p.y))));
    const maxX = Math.min(image.naturalWidth, Math.ceil(Math.max(...points.map(p => p.x))));
    const maxY = Math.min(image.naturalHeight, Math.ceil(Math.max(...points.map(p => p.y))));
    const w = Math.max(1, maxX - minX);
    const h = Math.max(1, maxY - minY);

    const out = document.createElement('canvas');
    out.width = w;
    out.height = h;
    const ctx = out.getContext('2d');
    ctx.beginPath();
    ctx.moveTo(points[0].x - minX, points[0].y - minY);
    points.slice(1).forEach(p => ctx.lineTo(p.x - minX, p.y - minY));
    ctx.closePath();
    ctx.clip();
    ctx.drawImage(image, -minX, -minY);
    return canvasToBlob(out, 'image/png');
}

async function runAISelection(event, label = 1) {
    if (state.searchMode === 'ai') {
        event.preventDefault();
        event.stopPropagation();
    }
    if (!state.selectedFile || state.searchMode !== 'ai' || state.aiBusy || !DOM.previewImage) return;
    clearQueryPreview();

    const rect = DOM.previewImage.getBoundingClientRect();
    if (!rect.width || !rect.height || !DOM.previewImage.naturalWidth || !DOM.previewImage.naturalHeight) return;

    const localX = event.clientX - rect.left;
    const localY = event.clientY - rect.top;
    if (localX < 0 || localY < 0 || localX > rect.width || localY > rect.height) return;

    const x = Math.round(localX * DOM.previewImage.naturalWidth / rect.width);
    const y = Math.round(localY * DOM.previewImage.naturalHeight / rect.height);

    const newPoint = {
        x,
        y,
        label,
        leftPct: (localX / rect.width) * 100,
        topPct: (localY / rect.height) * 100
    };

    const requestVersion = ++state.aiRequestVersion;
    const previousAccepted = state.aiAccepted;
    state.aiPoints.push(newPoint);
    state.aiBusy = true;
    state.aiAccepted = false;
    renderAIPoints();

    if (DOM.selectionStatus) {
        DOM.selectionStatus.className = 'selection-status busy';
        DOM.selectionStatus.innerHTML = `<i class="fas fa-circle-notch fa-spin"></i> SAM2 يعيد التحديد باستخدام ${aiPromptSummary()}...`;
    }
    if (DOM.acceptSelectionBtn) DOM.acceptSelectionBtn.disabled = true;
    if (DOM.resetSelectionBtn) DOM.resetSelectionBtn.disabled = false;
    updateSearchButtonState();

    try {
        const formData = new FormData();
        formData.append('image', state.selectedFile, state.selectedFile.name || 'query-image.jpg');
        formData.append('points', JSON.stringify(state.aiPoints.map(p => [p.x, p.y])));
        formData.append('labels', JSON.stringify(state.aiPoints.map(p => p.label)));

        const response = await fetch(CONFIG.SEGMENT_ENDPOINT, { method: 'POST', body: formData });
        const data = await readApiJson(response);
        if (requestVersion !== state.aiRequestVersion) return;

        const maskValue = data.mask || data.overlay;
        if (!maskValue || !data.cutout) {
            throw new Error('استجابة SAM2 لا تحتوي على mask/overlay أو cutout');
        }

        state.aiMaskDataUrl = `data:image/png;base64,${maskValue}`;
        state.aiCutoutDataUrl = `data:image/png;base64,${data.cutout}`;
        state.aiScore = Number(data.score ?? 0);

        if (DOM.segmentationMask) {
            DOM.segmentationMask.src = state.aiMaskDataUrl;
            DOM.segmentationMask.hidden = false;
            DOM.segmentationMask.classList.remove('accepted');
        }
        if (DOM.cutoutPreview) DOM.cutoutPreview.src = state.aiCutoutDataUrl;
        if (DOM.selectionResult) DOM.selectionResult.hidden = false;
        if (DOM.selectionConfidence) DOM.selectionConfidence.textContent = `ثقة ${(state.aiScore * 100).toFixed(1)}%`;
        if (DOM.acceptSelectionBtn) DOM.acceptSelectionBtn.disabled = false;
        if (DOM.resetSelectionBtn) DOM.resetSelectionBtn.disabled = false;
        if (DOM.selectionStatus) {
            DOM.selectionStatus.className = 'selection-status ready';
            DOM.selectionStatus.innerHTML = `<i class="fas fa-circle-check"></i> التحديد جاهز باستخدام ${aiPromptSummary()}. أضف نقاطًا أخرى أو اضغط «اعتماد القطعة».`;
        }
    } catch (error) {
        if (requestVersion !== state.aiRequestVersion) return;
        console.error('SAM2 segmentation error:', error);
        // Remove only the point that caused the failed request and keep the previous valid prompts.
        state.aiPoints.pop();
        state.aiAccepted = previousAccepted;
        const hasPreviousSelection = Boolean(state.aiMaskDataUrl && state.aiCutoutDataUrl);
        if (DOM.acceptSelectionBtn) DOM.acceptSelectionBtn.disabled = !hasPreviousSelection;
        renderAIPoints();
        if (DOM.selectionStatus) {
            DOM.selectionStatus.className = 'selection-status error';
            DOM.selectionStatus.innerHTML = `<i class="fas fa-triangle-exclamation"></i> ${escapeHtml(error.message)}${hasPreviousSelection ? ' — تم الاحتفاظ بالتحديد السابق.' : ''}`;
        }
        showToast(`تعذر تحديد القطعة: ${error.message}`, 'error');
    } finally {
        if (requestVersion === state.aiRequestVersion) {
            state.aiBusy = false;
            updateSearchButtonState();
        }
    }
}

function acceptAISelection() {
    if (!state.aiCutoutDataUrl || !state.aiMaskDataUrl) return;
    state.aiAccepted = true;
    if (DOM.segmentationMask) DOM.segmentationMask.classList.add('accepted');
    if (DOM.previewBadge) {
        DOM.previewBadge.classList.add('ai-badge');
        const badgeText = DOM.previewBadge.querySelector('span');
        if (badgeText) badgeText.textContent = 'تم اعتماد القطعة';
    }
    if (DOM.selectionStatus) {
        DOM.selectionStatus.className = 'selection-status accepted';
        DOM.selectionStatus.innerHTML = '<i class="fas fa-check-double"></i> تم اعتماد القطعة. يمكنك بدء البحث الآن.';
    }
    updateSearchButtonState();
    showToast('تم اعتماد القطعة المحددة للبحث', 'success');
}

// ===================================
// Toast Notifications
// ===================================

/**
 * Show toast notification
 * @param {string} message - Message to display
 * @param {'success'|'error'|'warning'} type - Toast type
 */
function showToast(message, type = 'success') {
    if (!DOM.toastContainer) return;
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    const icons = {
        success: 'fa-check-circle',
        error: 'fa-exclamation-circle',
        warning: 'fa-exclamation-triangle'
    };

    toast.innerHTML = `
        <i class="fas ${icons[type] || 'fa-info-circle'} toast-icon"></i>
        <span class="toast-message">${escapeHtml(message)}</span>
        <button class="toast-close" aria-label="إغلاق" type="button">
            <i class="fas fa-times"></i>
        </button>
    `;

    DOM.toastContainer.appendChild(toast);

    // Close button handler
    const closeBtn = toast.querySelector('.toast-close');
    if (closeBtn) closeBtn.addEventListener('click', () => removeToast(toast));

    // Auto remove
    setTimeout(() => removeToast(toast), CONFIG.TOAST_DURATION);
}

/**
 * Remove toast with animation
 * @param {HTMLElement} toast - Toast element
 */
function removeToast(toast) {
    toast.classList.add('toast-exit');
    setTimeout(() => toast.remove(), 300);
}

// ===================================
// File Upload Handlers
// ===================================

/**
 * Handle file selection
 * @param {File|Blob} file - Selected file
 */
function handleFileSelect(file) {
    const validation = validateFile(file);

    if (!validation.valid) {
        showToast(validation.error, 'error');
        return;
    }

    state.selectedFile = file;
    resetAISelection({ keepMode: false });
    resetManualSelection();
    setSearchMode('full');
    showPreview(file);
    if (DOM.selectionPanel) DOM.selectionPanel.hidden = false;
    updateSearchButtonState();
    showToast('تم اختيار الصورة بنجاح! يمكنك الآن بدء البحث.', 'success');
}

/**
 * Show image preview
 * @param {File|Blob} file - Image file
 */
function showPreview(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
        if (DOM.previewImage) {
            DOM.previewImage.onload = () => {
                ensureSelectionCanvasSize();
                drawManualSelection();
            };
            DOM.previewImage.src = e.target.result;
        }
        if (DOM.dropZoneContent) DOM.dropZoneContent.hidden = true;
        if (DOM.previewContainer) DOM.previewContainer.hidden = false;
    };
    reader.readAsDataURL(file);
}

/**
 * Clear selected image
 */
function clearImage() {
    clearQueryPreview();
    state.selectedFile = null;
    state.currentSearchId = null;
    resetAISelection({ keepMode: false });
    resetManualSelection();
    setSearchMode('full');
    if (DOM.selectionPanel) DOM.selectionPanel.hidden = true;
    if (DOM.previewImage) DOM.previewImage.src = '';
    if (DOM.previewContainer) DOM.previewContainer.hidden = true;
    if (DOM.dropZoneContent) DOM.dropZoneContent.hidden = false;
    if (DOM.feedbackPanel) DOM.feedbackPanel.hidden = true;
    updateSearchButtonState();
    if (DOM.fileInput) DOM.fileInput.value = '';
}

/**
 * Update progress bar
 * @param {number} percent - Progress percentage (0-100)
 * @param {string} text - Progress text
 */
function updateProgress(percent, text = 'جاري الرفع...') {
    if (DOM.progressFill) DOM.progressFill.style.width = `${percent}%`;
    if (DOM.progressText) DOM.progressText.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${text}`;
}

// ===================================
// Sample Images Handler
// ===================================
async function selectSampleImage(url, label) {
    try {
        updateProgress(50, `جاري تحميل عينة ${label}...`);
        if (DOM.progressContainer) DOM.progressContainer.hidden = false;
        
        const response = await fetch(url);
        const blob = await response.blob();
        const file = new File([blob], `${label}.jpg`, { type: blob.type || 'image/jpeg' });
        
        handleFileSelect(file);
    } catch (e) {
        // Fallback: direct image preview from URL
        if (DOM.previewImage) DOM.previewImage.src = url;
        if (DOM.dropZoneContent) DOM.dropZoneContent.hidden = true;
        if (DOM.previewContainer) DOM.previewContainer.hidden = false;
        state.selectedFile = null;
        if (DOM.selectionPanel) DOM.selectionPanel.hidden = true;
        updateSearchButtonState();
        showToast(`تعذر تحميل عينة "${label}" كملف للبحث. جرّب رفع صورة من جهازك.`, 'warning');
    } finally {
        if (DOM.progressContainer) DOM.progressContainer.hidden = true;
    }
}

// ===================================
// Camera Handler
// ===================================
async function openCameraModal() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        showToast('الكاميرا غير مدعومة في متصفحك الحالي', 'error');
        return;
    }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } }
        });
        state.cameraStream = stream;
        if (DOM.cameraVideo) {
            DOM.cameraVideo.srcObject = stream;
            DOM.cameraVideo.play();
        }
        if (DOM.cameraModal) DOM.cameraModal.hidden = false;
        document.body.style.overflow = 'hidden';
    } catch (err) {
        console.error('Camera error:', err);
        showToast('تعذر الوصول إلى الكاميرا. يرجى التأكد من إعطاء الصلاحيات.', 'error');
    }
}

function closeCameraModal() {
    if (state.cameraStream) {
        state.cameraStream.getTracks().forEach(track => track.stop());
        state.cameraStream = null;
    }
    if (DOM.cameraVideo) DOM.cameraVideo.srcObject = null;
    if (DOM.cameraModal) DOM.cameraModal.hidden = true;
    document.body.style.overflow = '';
}

function captureCameraPhoto() {
    if (!DOM.cameraVideo || !DOM.cameraCanvas) return;
    const video = DOM.cameraVideo;
    const canvas = DOM.cameraCanvas;
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;

    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    canvas.toBlob((blob) => {
        if (blob) {
            const file = new File([blob], 'camera-capture.jpg', { type: 'image/jpeg' });
            handleFileSelect(file);
            closeCameraModal();
            showToast('تم التقاط الصورة بنجاح!', 'success');
        }
    }, 'image/jpeg', 0.9);
}

// ===================================
// API Communication
// ===================================

/**
 * Send image to API for search
 * @param {File|Blob} imageFile - Image file to search
 * @param {number} topK - Number of results to return
 * @returns {Promise<Object>}
 */
async function searchImage(imageFile, topK, fileName = 'query-image.jpg', searchMode = 'full', category = 'auto') {
    const formData = new FormData();
    formData.append('image', imageFile, fileName);
    formData.append('search_mode', searchMode);
    formData.append('category', category);

    const endpoint = `${CONFIG.SEARCH_ENDPOINT}?top_k=${encodeURIComponent(topK)}`;
    const response = await fetch(endpoint, {
        method: 'POST',
        body: formData
    });

    const data = await readApiJson(response);
    return normalizeSearchResponse(data);
}

async function submitSearchFeedback(verdict, options = {}) {
    if (!state.currentSearchId) {
        showToast('لا يوجد رقم بحث صالح لإرسال التقييم', 'warning');
        return;
    }

    const payload = {
        search_id: state.currentSearchId,
        verdict,
        selected_product_id: options.selectedProductId || null,
        corrected_category: options.correctedCategory || null,
        notes: options.notes || null
    };

    const response = await fetch(CONFIG.FEEDBACK_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    await readApiJson(response);

    if (DOM.feedbackStatus) {
        DOM.feedbackStatus.className = 'feedback-status saved';
        DOM.feedbackStatus.textContent = verdict === 'correct'
            ? 'تم حفظ المنتج الصحيح. شكرًا، ستُستخدم المعلومة في قياس الدقة.'
            : 'تم حفظ الملاحظة لتحليل حالة الفشل.';
    }
    showToast('تم حفظ تقييمك للبحث', 'success');
}

// ===================================
// Results Rendering
// ===================================

/**
 * Render search results
 * @param {Object} data - API response data
 */
function renderResults(data) {
    state.results = Array.isArray(data.results) ? data.results : [];
    state.lastQuery = data.query_image_url || null;
    state.currentSearchId = data.query?.search_id || null;
    state.selectedCategory = 'all';

    if (DOM.feedbackPanel) DOM.feedbackPanel.hidden = !state.currentSearchId;
    if (DOM.feedbackStatus) {
        DOM.feedbackStatus.className = 'feedback-status';
        DOM.feedbackStatus.textContent = data.query?.monitoring_warning
            ? 'اكتمل البحث، لكن تعذر تسجيله للمراقبة.'
            : 'لا تُحفظ صورة البحث أو بيانات شخصية.';
    }

    const hasCategoryData = state.results.some(item => Boolean(item.category));
    if (DOM.filterChipsContainer) DOM.filterChipsContainer.hidden = !hasCategoryData;
    if (DOM.filterChips) {
        const resultCategories = new Set(state.results.map(item => item.category).filter(Boolean));
        DOM.filterChips.forEach(chip => {
            const category = chip.dataset.category || 'all';
            chip.hidden = category !== 'all' && !resultCategories.has(category);
        });
    }

    applyCategoryFilter(state.selectedCategory);

    // Show results section
    if (DOM.resultsSection) {
        DOM.resultsSection.hidden = false;
        DOM.resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

}

/**
 * Apply Category filter on results
 * @param {string} category - Category name or 'all'
 */
function applyCategoryFilter(category) {
    state.selectedCategory = category;

    // Update active filter chip UI
    if (DOM.filterChips) {
        DOM.filterChips.forEach(chip => {
            chip.classList.toggle('active', chip.dataset.category === category);
        });
    }

    let items = state.results;
    if (category !== 'all') {
        items = state.results.filter(item => (item.category && item.category.includes(category)) || item.title?.includes(category));
    }

    state.filteredResults = items;

    // Update results count
    if (DOM.resultsCount) {
        DOM.resultsCount.textContent = `(${items.length} قطعة)`;
    }

    // Render cards
    if (DOM.resultsGrid) {
        DOM.resultsGrid.innerHTML = '';
        if (items.length === 0) {
            DOM.resultsGrid.innerHTML = `
                <div style="grid-column: 1/-1; text-align: center; padding: 2.5rem; color: var(--text-2);">
                    <i class="fas fa-search" style="font-size: 2rem; margin-bottom: 0.75rem; color: var(--text-3);"></i>
                    <p style="font-weight: 700;">لا توجد قطع تطابق هذا التصنيف</p>
                    <p style="font-size: 0.85rem;">اختر تصنيفاً آخر أو انقر على "الكل" لعرض كافة النتائج.</p>
                </div>
            `;
            return;
        }

        const sortedResults = [...items].sort((a, b) => b.similarity - a.similarity);
        sortedResults.forEach((item, index) => {
            const card = createResultCard(item, index);
            DOM.resultsGrid.appendChild(card);
        });
    }
}

/**
 * Create result card element
 * @param {Object} item - Result item
 * @param {number} index - Item index
 * @returns {HTMLElement}
 */
function createResultCard(item, index) {
    const card = document.createElement('article');
    card.className = 'result-card';
    card.role = 'listitem';
    card.tabIndex = 0;
    card.dataset.index = index;

    const title = String(item.title || `نتيجة مشابهة ${index + 1}`);
    const safeTitle = escapeHtml(title);
    const safeCategory = escapeHtml(item.category || '');
    const safeProductId = escapeHtml(item.product_id || '');
    const safeImageUrl = safeHttpUrl(item.image_url) || 'assets/placeholder.svg';
    const similarityClass = getSimilarityClass(item.similarity);
    const categoryTag = item.category ? `<span style="font-size:0.75rem; color:var(--text-3);"><i class="fas fa-tag"></i> ${safeCategory}</span>` : '';

    card.innerHTML = `
        <img
            src="${safeImageUrl}"
            alt="${safeTitle}"
            class="result-card-image lazy-image"
            loading="lazy"
            onerror="this.src='assets/placeholder.svg'"
        >
        <div class="result-card-body">
            <h3 class="result-card-title" title="${safeTitle}">${safeTitle}</h3>
            <div class="card-bottom-row">
                <span class="similarity-badge ${similarityClass}">
                    <i class="fas fa-percentage"></i>
                    ${formatSimilarity(item.similarity)} تشابه
                </span>
                ${categoryTag}
            </div>
            ${item.product_id ? `
                <button type="button" class="correct-match-btn" data-product-id="${safeProductId}">
                    <i class="fas fa-circle-check"></i> هذه المطابقة صحيحة
                </button>
            ` : ''}
        </div>
    `;

    // Add click handler
    card.addEventListener('click', () => openProductModal(item));
    card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') openProductModal(item);
    });

    // Lazy load image
    const img = card.querySelector('img');
    if (img) {
        img.addEventListener('load', () => img.classList.add('loaded'));
    }

    const correctButton = card.querySelector('.correct-match-btn');
    if (correctButton) {
        correctButton.addEventListener('click', async (event) => {
            event.stopPropagation();
            try {
                await submitSearchFeedback('correct', { selectedProductId: item.product_id });
            } catch (error) {
                showToast(`تعذر حفظ التقييم: ${error.message}`, 'error');
            }
        });
    }

    return card;
}

// ===================================
// Modal Handlers
// ===================================

/**
 * Open product detail modal
 * @param {Object} product - Product data
 */
function openProductModal(product) {
    const title = product.title || 'نتيجة البحث';

    if (DOM.modalImage) {
        DOM.modalImage.src = safeHttpUrl(product.image_url) || 'assets/placeholder.svg';
        DOM.modalImage.alt = title;
    }
    if (DOM.modalTitle) DOM.modalTitle.textContent = title;
    if (DOM.modalProductId) DOM.modalProductId.textContent = product.product_id;
    if (DOM.modalSimilarity) {
        DOM.modalSimilarity.textContent = `${formatSimilarity(product.similarity)} تشابه بصري`;
        DOM.modalSimilarity.className = `info-value similarity-badge ${getSimilarityClass(product.similarity)}`;
    }
    if (DOM.modalImageUrl) DOM.modalImageUrl.textContent = product.image_url;

    // Handle product URL
    if (DOM.modalProductLink) {
        if (product.product_url) {
            const productUrl = safeHttpUrl(product.product_url);
            DOM.modalProductLink.href = productUrl;
            DOM.modalProductLink.style.display = productUrl ? 'flex' : 'none';
        } else {
            DOM.modalProductLink.style.display = 'none';
        }
    }

    // Set download link
    if (DOM.modalDownload) {
        DOM.modalDownload.href = safeHttpUrl(product.image_url) || 'assets/placeholder.svg';
        DOM.modalDownload.download = `${product.product_id}.jpg`;
    }

    // Store current image URL for copy
    if (DOM.modalCopyLink) {
        DOM.modalCopyLink.dataset.url = product.image_url;
    }

    // Show modal
    if (DOM.productModal) DOM.productModal.hidden = false;
    document.body.style.overflow = 'hidden';

    // Focus close button for accessibility
    if (DOM.modalClose) DOM.modalClose.focus();
}

/**
 * Close product modal
 */
function closeProductModal() {
    if (DOM.productModal) DOM.productModal.hidden = true;
    document.body.style.overflow = '';
}

/**
 * Open about modal
 */
function openAboutModal() {
    if (DOM.aboutModal) DOM.aboutModal.hidden = false;
    document.body.style.overflow = 'hidden';
    if (DOM.aboutClose) DOM.aboutClose.focus();
}

/**
 * Close about modal
 */
function closeAboutModal() {
    if (DOM.aboutModal) DOM.aboutModal.hidden = true;
    document.body.style.overflow = '';
}

// ===================================
// Theme Toggle
// ===================================

/**
 * Toggle dark mode
 */
function toggleTheme() {
    state.isDarkMode = !state.isDarkMode;
    document.documentElement.dataset.theme = state.isDarkMode ? 'dark' : 'light';

    if (DOM.themeToggle) {
        const icon = DOM.themeToggle.querySelector('i');
        if (icon) icon.className = state.isDarkMode ? 'fas fa-sun' : 'fas fa-moon';
    }

    localStorage.setItem('theme', state.isDarkMode ? 'dark' : 'light');
}

/**
 * Load saved theme preference
 */
function loadThemePreference() {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark' || (!savedTheme && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
        state.isDarkMode = true;
        document.documentElement.dataset.theme = 'dark';
        if (DOM.themeToggle) {
            const icon = DOM.themeToggle.querySelector('i');
            if (icon) icon.className = 'fas fa-sun';
        }
    }
}

// ===================================
// Event Handlers
// ===================================

/**
 * Handle search button click
 */
async function handleSearch() {
    if (!state.selectedFile) {
        showToast('يرجى اختيار أو رفع صورة أولاً', 'warning');
        return;
    }

    const topK = parseInt(DOM.topKSelect?.value || '8');
    const requestedCategory = DOM.categoryModeSelect?.value || 'auto';
    state.currentSearchId = null;
    if (DOM.feedbackPanel) DOM.feedbackPanel.hidden = true;

    try {
        if (DOM.loadingOverlay) DOM.loadingOverlay.hidden = false;
        if (DOM.progressContainer) DOM.progressContainer.hidden = false;
        updateProgress(25, 'جاري معالجة وتحليل الصورة...');

        let fileToUpload = state.selectedFile;
        let uploadName = state.selectedFile?.name || 'query-image.jpg';

        if (state.searchMode === 'ai') {
            if (!state.aiAccepted || !state.aiCutoutDataUrl) {
                throw new Error('حدد القطعة واعتمدها قبل بدء البحث');
            }
            updateProgress(45, 'جاري تجهيز القطعة المحددة بواسطة SAM2...');
            fileToUpload = await dataUrlToBlob(state.aiCutoutDataUrl);
            uploadName = 'sam2-selected-product.png';
        } else if (isManualMode()) {
            if (!hasManualSelection()) throw new Error('أكمل التحديد اليدوي أولاً');
            updateProgress(45, 'جاري تجهيز المنطقة المحددة...');
            fileToUpload = await createManualSelectionBlob();
            uploadName = `${state.searchMode}-selected-area.${state.searchMode === 'rect' ? 'jpg' : 'png'}`;
        } else if (CONFIG.ENABLE_CLIENT_RESIZE && fileToUpload instanceof Blob) {
            updateProgress(50, 'جاري تجهيز الصورة...');
            fileToUpload = await resizeImage(state.selectedFile, CONFIG.MAX_IMAGE_WIDTH);
        }

        await showQueryPreview(fileToUpload, state.searchMode);

        updateProgress(60, 'SigLIP2 يستخرج الخصائص البصرية...');
        updateProgress(80, 'FAISS يبحث عن أقرب الصور...');

        const results = await searchImage(fileToUpload, topK, uploadName, state.searchMode, requestedCategory);
        verifyQueryReceipt(results.query);
        renderCategoryRouting(results.query);

        updateProgress(100, 'تم استخراج أفضل النتائج!');
        renderResults(results);
        showToast('تم العثور على أزياء مشابهة بنجاح!', 'success');

    } catch (error) {
        console.error('Search error:', error);
        showToast(`حدث خطأ أثناء البحث: ${error.message}`, 'error');
    } finally {
        if (DOM.loadingOverlay) DOM.loadingOverlay.hidden = true;
        setTimeout(() => {
            if (DOM.progressContainer) DOM.progressContainer.hidden = true;
            updateProgress(0);
        }, 500);
    }
}

/**
 * Handle view toggle
 * @param {string} view - 'grid' or 'list'
 */
function handleViewToggle(view) {
    state.currentView = view;

    if (DOM.viewGridBtn) {
        DOM.viewGridBtn.classList.toggle('active', view === 'grid');
        DOM.viewGridBtn.setAttribute('aria-checked', view === 'grid');
    }
    if (DOM.viewListBtn) {
        DOM.viewListBtn.classList.toggle('active', view === 'list');
        DOM.viewListBtn.setAttribute('aria-checked', view === 'list');
    }
    if (DOM.resultsGrid) {
        DOM.resultsGrid.classList.toggle('list-view', view === 'list');
    }
}

// ===================================
// Event Listeners Setup
// ===================================

function setupEventListeners() {
    // Drop zone & Browse
    if (DOM.dropZone) {
        DOM.dropZone.addEventListener('click', (e) => {
            // Once an image is selected, clicks are used by SAM2/manual selection.
            // Never reopen the file chooser from the preview canvas/image.
            if (state.selectedFile) return;

            if (e.target.closest('.btn-remove') || e.target.closest('.btn-camera-trigger') || e.target.closest('#browse-files-btn')) return;
            DOM.fileInput.click();
        });
        DOM.dropZone.addEventListener('keydown', (e) => {
            if (state.selectedFile) return;
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                DOM.fileInput.click();
            }
        });
    }

    if (DOM.browseFilesBtn) {
        DOM.browseFilesBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            DOM.fileInput.click();
        });
    }

    // File input change
    if (DOM.fileInput) {
        DOM.fileInput.addEventListener('change', (e) => {
            if (e.target.files && e.target.files[0]) {
                handleFileSelect(e.target.files[0]);
            }
        });
    }

    // Drag and drop
    if (DOM.dropZone) {
        DOM.dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            DOM.dropZone.classList.add('drag-over');
        });

        DOM.dropZone.addEventListener('dragleave', (e) => {
            e.preventDefault();
            DOM.dropZone.classList.remove('drag-over');
        });

        DOM.dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            DOM.dropZone.classList.remove('drag-over');

            const file = e.dataTransfer.files[0];
            if (file) {
                handleFileSelect(file);
            }
        });
    }

    // Paste image from clipboard (Ctrl+V)
    window.addEventListener('paste', (e) => {
        const items = e.clipboardData?.items;
        if (!items) return;
        for (let i = 0; i < items.length; i++) {
            if (items[i].type.indexOf('image') !== -1) {
                const blob = items[i].getAsFile();
                if (blob) {
                    handleFileSelect(blob);
                    showToast('تم استيراد الصورة من الحافظة (Paste)!', 'success');
                    break;
                }
            }
        }
    });

    // Sample chips
    const sampleChips = document.querySelectorAll('.sample-chip');
    sampleChips.forEach(chip => {
        chip.addEventListener('click', (e) => {
            e.stopPropagation();
            const imgUrl = chip.dataset.img;
            const label = chip.dataset.label;
            selectSampleImage(imgUrl, label);
        });
    });

    // Camera features
    if (DOM.cameraBtn) DOM.cameraBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        openCameraModal();
    });
    if (DOM.cameraClose) DOM.cameraClose.addEventListener('click', closeCameraModal);
    if (DOM.cameraBackdrop) DOM.cameraBackdrop.addEventListener('click', closeCameraModal);
    if (DOM.cameraCaptureBtn) DOM.cameraCaptureBtn.addEventListener('click', captureCameraPhoto);

    // Remove image button
    if (DOM.removeImageBtn) {
        DOM.removeImageBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            clearImage();
        });
    }

    // Search modes: full image, SAM2, rectangle, polygon, free draw
    if (DOM.modeFullBtn) DOM.modeFullBtn.addEventListener('click', () => setSearchMode('full'));
    if (DOM.modeAiBtn) DOM.modeAiBtn.addEventListener('click', () => setSearchMode('ai'));
    if (DOM.modeRectBtn) DOM.modeRectBtn.addEventListener('click', () => { resetManualSelection(); setSearchMode('rect'); });
    if (DOM.modePolyBtn) DOM.modePolyBtn.addEventListener('click', () => { resetManualSelection(); setSearchMode('poly'); });
    if (DOM.modeFreeBtn) DOM.modeFreeBtn.addEventListener('click', () => { resetManualSelection(); setSearchMode('free'); });

    if (DOM.previewImage) {
        DOM.previewImage.addEventListener('click', (event) => runAISelection(event, 1));
        DOM.previewImage.addEventListener('contextmenu', (event) => {
            if (state.searchMode !== 'ai') return;
            event.preventDefault();
            runAISelection(event, 0);
        });
    }
    if (DOM.acceptSelectionBtn) DOM.acceptSelectionBtn.addEventListener('click', acceptAISelection);
    if (DOM.resetSelectionBtn) DOM.resetSelectionBtn.addEventListener('click', () => {
        resetAISelection({ keepMode: true });
        setSearchMode('ai');
    });

    if (DOM.selectionCanvas) {
        DOM.selectionCanvas.addEventListener('mousedown', handleManualPointerDown);
        DOM.selectionCanvas.addEventListener('mousemove', handleManualPointerMove);
        DOM.selectionCanvas.addEventListener('mouseup', handleManualPointerUp);
        DOM.selectionCanvas.addEventListener('mouseleave', handleManualPointerUp);
        DOM.selectionCanvas.addEventListener('click', handleManualCanvasClick);
    }
    if (DOM.finishPolygonBtn) DOM.finishPolygonBtn.addEventListener('click', finishPolygon);
    if (DOM.clearManualSelectionBtn) DOM.clearManualSelectionBtn.addEventListener('click', () => {
        resetManualSelection();
        setSearchMode(state.searchMode);
    });

    // Search button
    if (DOM.searchBtn) DOM.searchBtn.addEventListener('click', handleSearch);

    if (DOM.feedbackNoMatchBtn) {
        DOM.feedbackNoMatchBtn.addEventListener('click', async () => {
            try {
                await submitSearchFeedback('no_match');
            } catch (error) {
                showToast(`تعذر حفظ التقييم: ${error.message}`, 'error');
            }
        });
    }

    if (DOM.feedbackWrongCategoryBtn) {
        DOM.feedbackWrongCategoryBtn.addEventListener('click', async () => {
            const correctedCategory = DOM.categoryModeSelect?.value || 'auto';
            if (correctedCategory === 'auto' || correctedCategory === 'all') {
                showToast('اختر نوع القطعة الصحيح من القائمة أعلاه ثم اضغط الزر مرة أخرى', 'warning');
                DOM.categoryModeSelect?.focus();
                return;
            }
            try {
                await submitSearchFeedback('wrong_category', { correctedCategory });
            } catch (error) {
                showToast(`تعذر حفظ التقييم: ${error.message}`, 'error');
            }
        });
    }

    // Category filter chips
    if (DOM.filterChips) {
        DOM.filterChips.forEach(chip => {
            chip.addEventListener('click', () => {
                const category = chip.dataset.category || 'all';
                applyCategoryFilter(category);
            });
        });
    }

    // View toggle
    if (DOM.viewGridBtn) DOM.viewGridBtn.addEventListener('click', () => handleViewToggle('grid'));
    if (DOM.viewListBtn) DOM.viewListBtn.addEventListener('click', () => handleViewToggle('list'));

    // Theme toggle
    if (DOM.themeToggle) DOM.themeToggle.addEventListener('click', toggleTheme);

    // About modal
    if (DOM.aboutBtn) DOM.aboutBtn.addEventListener('click', openAboutModal);
    if (DOM.aboutClose) DOM.aboutClose.addEventListener('click', closeAboutModal);
    if (DOM.aboutBackdrop) DOM.aboutBackdrop.addEventListener('click', closeAboutModal);

    // Product modal
    if (DOM.modalClose) DOM.modalClose.addEventListener('click', closeProductModal);
    if (DOM.modalBackdrop) DOM.modalBackdrop.addEventListener('click', closeProductModal);

    // Copy link button
    if (DOM.modalCopyLink) {
        DOM.modalCopyLink.addEventListener('click', async () => {
            const url = DOM.modalCopyLink.dataset.url;
            if (url) {
                const success = await copyToClipboard(url);
                if (success) {
                    showToast('تم نسخ الرابط إلى الحافظة بنجاح', 'success');
                } else {
                    showToast('فشل نسخ الرابط', 'error');
                }
            }
        });
    }

    // Back to top button
    if (DOM.backToTopBtn) {
        window.addEventListener('scroll', () => {
            if (window.scrollY > 300) {
                DOM.backToTopBtn.classList.add('visible');
            } else {
                DOM.backToTopBtn.classList.remove('visible');
            }
        });

        DOM.backToTopBtn.addEventListener('click', () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            if (DOM.productModal && !DOM.productModal.hidden) closeProductModal();
            else if (DOM.aboutModal && !DOM.aboutModal.hidden) closeAboutModal();
            else if (DOM.cameraModal && !DOM.cameraModal.hidden) closeCameraModal();
        }

        if (e.key === 'Enter' && (!DOM.productModal || DOM.productModal.hidden) && (!DOM.aboutModal || DOM.aboutModal.hidden) && (!DOM.cameraModal || DOM.cameraModal.hidden)) {
            if (DOM.searchBtn && !DOM.searchBtn.disabled && document.activeElement !== DOM.topKSelect) {
                handleSearch();
            }
        }
    });
}

// ===================================
// Initialization
// ===================================

function init() {
    loadThemePreference();
    setupEventListeners();
    setSearchMode('full');
    updateSearchButtonState();
    console.log('Visual Fashion Search application initialized with SAM2 + SigLIP2 + FAISS integration.');
}

// Start app when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
