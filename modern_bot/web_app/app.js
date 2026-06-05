/* =============================================
   app.js - Extracted from index.html v5.4
   ============================================= */

const tg = (window.Telegram && window.Telegram.WebApp) ? window.Telegram.WebApp : {
    initDataUnsafe: {},
    platform: '',
    version: '',
    initData: '',
    ready: () => { },
    expand: () => { },
    requestFullscreen: () => { },
    showAlert: (message) => alert(message),
    showPopup: ({ message }) => alert(message),
    sendData: () => { },
    close: () => { },
    MainButton: {
        setText: () => { },
        show: () => { },
        hide: () => { },
        enable: () => { },
        disable: () => { },
        onClick: () => { },
        offClick: () => { },
        showProgress: () => { },
        hideProgress: () => { }
    },
    HapticFeedback: {
        impactOccurred: () => { },
        notificationOccurred: () => { },
        selectionChanged: () => { }
    }
};

let audioCtx = null;
let audioUnlocked = false;
let fullScreenRequested = false;

function getAudioContext() {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    if (!audioCtx) audioCtx = new Ctx();
    return audioCtx;
}

function unlockAudio() {
    const ctx = getAudioContext();
    if (!ctx || audioUnlocked) return;
    const resume = ctx.state === 'suspended' ? ctx.resume() : Promise.resolve();
    resume.then(() => {
        const buffer = ctx.createBuffer(1, 1, 22050);
        const source = ctx.createBufferSource();
        source.buffer = buffer;
        source.connect(ctx.destination);
        source.start(0);
        audioUnlocked = true;
    }).catch(() => { });
}

function playTone(kind = 'success') {
    const ctx = getAudioContext();
    if (!ctx) return;
    if (ctx.state === 'suspended') {
        ctx.resume().catch(() => { });
    }

    let freq = 660;
    let duration = 0.08;
    if (kind === 'error') {
        freq = 220;
        duration = 0.12;
    } else if (kind === 'tap') {
        freq = 520;
        duration = 0.05;
    }

    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'triangle';
    osc.frequency.setValueAtTime(freq, now);
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.12, now + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + duration);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(now);
    osc.stop(now + duration + 0.02);
}

function requestFullScreen(force = false) {
    if (fullScreenRequested && !force) return;
    fullScreenRequested = true;
    try {
        tg.expand();
        if (tg.requestFullscreen) tg.requestFullscreen();
    } catch (e) { }
}

// --- CONFIGURATION ---
// WARNING: These are default values for local/demo use.
// For production, consider injecting these via environment variables or a build step.
// --- SECURITY: XSS PROTECTION ---
function escapeHtml(unsafe) {
    if (!unsafe) return '';
    return String(unsafe)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

const APP_CONFIG = {
    DEFAULT_BOT_URL: window.APP_DEFAULT_BOT_URL || "",
    IMAGEBAN_CLIENT_ID: window.APP_IMAGEBAN_CLIENT_ID || "wlbeebCGLMGRtwNpk5YS"
};

// Initialize
tg.expand();
if (tg.ready) tg.ready();
requestFullScreen();
const firstGesture = () => {
    requestFullScreen(true);
    unlockAudio();
};
document.addEventListener('click', firstGesture, { once: true });
document.addEventListener('touchstart', firstGesture, { once: true });
// Assuming restoreDraft() exists elsewhere or will be added.
// restoreDraft();

// URL params allow setting shared config for all users (e.g. from bot WebApp URL).
const urlParams = new URLSearchParams(window.location.search);
const urlBotUrl = (urlParams.get('bot_url') || '').trim();
const isInTelegram = Boolean(tg.initDataUnsafe && tg.initDataUnsafe.user);
const imagebanClientId = (urlParams.get('imageban_client') || APP_CONFIG.IMAGEBAN_CLIENT_ID || '').trim();

// Load Bot URL (for standalone mode)
let botUrl = urlBotUrl || APP_CONFIG.DEFAULT_BOT_URL;
if (!isInTelegram) {
    try {
        botUrl = localStorage.getItem('bot_url') || botUrl;
    } catch (e) { }
} else if (botUrl) {
    try {
        localStorage.setItem('bot_url', botUrl);
    } catch (e) { }
}


function showUserGuide() {
    document.getElementById('guideModal').style.display = 'flex';
    haptic('light');
}

function closeGuide() {
    document.getElementById('guideModal').style.display = 'none';
    haptic('light');
}

function showMotivation() {
    document.getElementById('motivationModal').style.display = 'flex';
    haptic('light');
}

function closeMotivation() {
    document.getElementById('motivationModal').style.display = 'none';
    haptic('light');
}

let quizQuestions = [];
let quizState = null;
const QUIZ_SIZE = 5;
const QUIZ_VERSION = '2328';
const QUIZ_FACTS = [
    'Самые ценные предметы обычно сопровождаются четкой историей происхождения.',
    'Бережная чистка ценится выше агрессивной полировки.',
    'Наличие клейм и маркировок повышает доверие к предмету.',
    'Даже небольшие повреждения стоит фиксировать в описании.',
    'Фотография в хорошем свете экономит время на проверке.',
    'Редкость модели зачастую важнее возраста.',
    'Комплектность (коробка, документы) добавляет ценность.',
    'Следы реставрации нужно указывать отдельно.',
    'Качественное описание помогает быстрее согласовать оценку.',
    'Одинаковый формат описания упрощает работу всей команды.'
];

function getQuizRegion() {
    const regionEl = document.getElementById('region');
    const current = regionEl ? regionEl.value.trim() : '';
    if (current) {
        try {
            localStorage.setItem('last_region', current);
        } catch (e) { }
        return current;
    }
    try {
        return localStorage.getItem('last_region') || '';
    } catch (e) {
        return '';
    }
}

function getQuizUserMeta() {
    const user = tg.initDataUnsafe && tg.initDataUnsafe.user ? tg.initDataUnsafe.user : null;
    if (!user) return {};
    return {
        user_id: user.id,
        username: user.username,
        first_name: user.first_name,
        last_name: user.last_name
    };
}

function sendQuizStats(payload) {
    const base = (botUrl || '').trim();
    if (!base) return;
    const cleanBase = base.replace(/\/$/, "");
    fetch(`${cleanBase}/api/quiz/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        keepalive: true
    }).catch(() => { });
}

function reportQuizAttempt() {
    if (!quizState) return;
    const total = quizState.questions ? quizState.questions.length : 0;
    const payload = {
        correct: quizState.correct || 0,
        wrong: quizState.wrong || 0,
        total: total,
        region: getQuizRegion(),
        quiz_version: QUIZ_VERSION
    };
    Object.assign(payload, getQuizUserMeta());
    sendQuizStats(payload);
}

async function loadQuizQuestions() {
    if (quizQuestions.length > 0) return;
    const response = await fetch(`quiz_questions.json?v=${QUIZ_VERSION}`, { cache: 'no-store' });
    if (!response.ok) {
        throw new Error(`Ошибка загрузки вопросов (${response.status})`);
    }
    const data = await response.json();
    if (!Array.isArray(data) || data.length === 0) {
        throw new Error('Нет доступных вопросов');
    }
    quizQuestions = data;
}

function shuffleArray(source) {
    const array = source.slice();
    for (let i = array.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [array[i], array[j]] = [array[j], array[i]];
    }
    return array;
}

async function openQuiz() {
    if (quizOpen || quizLoading) return;
    quizOpen = true;
    quizLoading = true;
    const modal = document.getElementById('quizModal');
    const body = document.getElementById('quizBody');
    modal.style.display = 'flex';
    body.innerHTML = `<div class="quiz-progress">⏱ 1 минута • Загрузка вопросов...</div>`;

    try {
        await loadQuizQuestions();
        startQuiz();
    } catch (err) {
        body.innerHTML = `
                    <div class="quiz-result">Не удалось загрузить викторину. Попробуйте позже.</div>
                    <div class="quiz-footer">
                        <button type="button" class="btn btn-secondary" onclick="closeQuiz()">Закрыть</button>
                    </div>
                `;
    } finally {
        quizLoading = false;
    }
}

function closeQuiz() {
    const modal = document.getElementById('quizModal');
    modal.style.display = 'none';
    quizOpen = false;
    quizLoading = false;
}

function startQuiz() {
    const pool = shuffleArray(quizQuestions);
    const selected = pool.slice(0, Math.min(QUIZ_SIZE, pool.length));
    quizState = {
        questions: selected,
        current: 0,
        correct: 0,
        wrong: 0,
        answered: false
    };
    renderQuizQuestion();
}

function renderQuizQuestion() {
    const body = document.getElementById('quizBody');
    const q = quizState.questions[quizState.current];
    const optionsHtml = q.options.map((opt, idx) => (
        `<button type="button" class="quiz-option" onclick="selectQuizOption(${idx})">${escapeHtml(opt)}</button>`
    )).join('');

    body.innerHTML = `
                <div class="quiz-progress">⏱ 1 минута • Вопрос ${quizState.current + 1} из ${quizState.questions.length}</div>
                <div class="quiz-question">${escapeHtml(q.question)}</div>
                <div class="quiz-options">${optionsHtml}</div>
                <div class="quiz-footer" id="quizNext" style="display:none;">
                    <button type="button" class="btn btn-primary" onclick="goToNextQuestion()" id="quizNextBtn">Дальше</button>
                    <button type="button" class="btn btn-secondary" onclick="closeQuiz()">Отмена</button>
                </div>
            `;
}

function selectQuizOption(index) {
    if (!quizState || quizState.answered) return;
    quizState.answered = true;

    const q = quizState.questions[quizState.current];
    const buttons = document.querySelectorAll('.quiz-option');
    buttons.forEach((btn, idx) => {
        btn.disabled = true;
        if (idx === q.answer) {
            btn.classList.add('correct');
        } else if (idx === index) {
            btn.classList.add('incorrect');
        }
    });

    if (index === q.answer) {
        quizState.correct += 1;
    } else {
        quizState.wrong += 1;
    }

    const nextWrap = document.getElementById('quizNext');
    const nextBtn = document.getElementById('quizNextBtn');
    if (nextBtn) {
        nextBtn.textContent = quizState.current + 1 >= quizState.questions.length ? 'Результат' : 'Дальше';
    }
    if (nextWrap) {
        nextWrap.style.display = 'flex';
    }
}

function goToNextQuestion() {
    if (!quizState) return;
    if (quizState.current + 1 >= quizState.questions.length) {
        showQuizResult();
        return;
    }
    quizState.current += 1;
    quizState.answered = false;
    renderQuizQuestion();
}

function showQuizResult() {
    reportQuizAttempt();
    const body = document.getElementById('quizBody');
    const fact = QUIZ_FACTS.length
        ? QUIZ_FACTS[Math.floor(Math.random() * QUIZ_FACTS.length)]
        : '';
    body.innerHTML = `
                <div class="quiz-result">
                    ✅ Верно: <b>${quizState.correct}</b><br>
                    ❌ Неверно: <b>${quizState.wrong}</b>
                </div>
                ${fact ? `<div class="quiz-fact">💡 ${escapeHtml(fact)}</div>` : ''}
                <div class="quiz-footer">
                    <button type="button" class="btn btn-secondary" onclick="startQuiz()">Ещё раз</button>
                    <button type="button" class="btn btn-primary" onclick="closeQuiz()">Закрыть</button>
                </div>
            `;
}

function forceUpdate() {
    haptic('medium');
    const url = new URL(window.location.href);
    url.searchParams.set('v', Date.now());
    window.location.href = url.toString();
}

// Theme handling
function applyTelegramTheme() {
    if (tg.colorScheme === 'dark') {
        document.body.classList.add('dark-mode');
    } else {
        document.body.classList.remove('dark-mode');
    }

    if (tg.themeParams) {
        const root = document.documentElement.style;
        if (tg.themeParams.button_color) {
            root.setProperty('--primary-color', tg.themeParams.button_color);
            root.setProperty('--primary-hover', tg.themeParams.button_color);
        }
        if (tg.themeParams.text_color) {
            root.setProperty('--text-color', tg.themeParams.text_color);
        }
        if (tg.themeParams.hint_color) {
            root.setProperty('--secondary-text', tg.themeParams.hint_color);
        }
        if (tg.colorScheme === 'dark' && tg.themeParams.secondary_bg_color) {
            root.setProperty('--input-bg-field', tg.themeParams.secondary_bg_color);
            root.setProperty('--input-bg-field-main', tg.themeParams.secondary_bg_color);
        }
    }
}

// Apply theme initially and listen for dynamic changes
applyTelegramTheme();
tg.onEvent('themeChanged', applyTelegramTheme);


// Set today's date and max date (prevent future dates)
const today = new Date().toISOString().split('T')[0];
const dateInput = document.getElementById('date');
dateInput.valueAsDate = new Date();
dateInput.setAttribute('max', today);

// Additional validation on change (for iOS compatibility)
dateInput.addEventListener('change', function () {
    const selectedDate = new Date(this.value);
    const todayDate = new Date(today);

    if (selectedDate > todayDate) {
        tg.showAlert('⚠️ Нельзя выбрать будущую дату! Выберите сегодня или прошедшую дату.');
        this.value = today; // Reset to today
    }
});

const regionInput = document.getElementById('region');
if (regionInput) {
    regionInput.addEventListener('change', () => {
        const value = regionInput.value.trim();
        if (!value) return;
        try {
            localStorage.setItem('last_region', value);
        } catch (e) { }
    });
}

let itemCount = 0;
let appState = 'editing'; // State: 'editing' or 'preview'
let autosaveTimeout; // For debounced autosave
let previewOpen = false;
let submitInProgress = false;
let quizOpen = false;
let quizLoading = false;

// Swipe gesture support
let touchStartX = 0;
let touchStartY = 0;
let currentCard = null;

function handleTouchStart(e) {
    const card = e.currentTarget.closest('.item-card');
    if (!card) return;
    currentCard = card;
    touchStartX = e.touches[0].clientX;
    touchStartY = e.touches[0].clientY;
    currentCard.style.transition = 'none';
}

function handleTouchMove(e) {
    if (!currentCard) return;
    const touchX = e.touches[0].clientX;
    const touchY = e.touches[0].clientY;
    const diffX = touchX - touchStartX;
    const diffY = touchY - touchStartY;

    // Only horizontal swipe to the left
    if (Math.abs(diffX) > Math.abs(diffY) && diffX < 0) {
        currentCard.style.transform = `translateX(${diffX}px)`;
        currentCard.style.opacity = 1 + diffX / 200;
    }
}

function handleTouchEnd(e) {
    if (!currentCard) return;

    const touchX = e.changedTouches[0].clientX;
    const diffX = touchX - touchStartX;

    if (diffX < -100) {
        // Swipe threshold reached - delete
        currentCard.style.transition = 'transform 0.3s, opacity 0.3s';
        currentCard.style.transform = 'translateX(-100%)';
        currentCard.style.opacity = '0';

        setTimeout(() => {
            currentCard.remove();
            updateBadge();
            haptic('medium');
        }, 300);
    } else {
        // Reset position
        currentCard.style.transition = 'transform 0.3s, opacity 0.3s';
        currentCard.style.transform = 'translateX(0)';
        currentCard.style.opacity = '1';
    }

    currentCard = null;
}

// Real-time Total Calculation
function updateTotalCost() {
    let total = 0;
    document.querySelectorAll('.eval').forEach(input => {
        const val = input.value.replace(/\s/g, ''); // Remove spaces
        total += parseInt(val) || 0;
    });

    const banner = document.getElementById('realTimeTotal');
    const display = document.getElementById('totalAmountDisplay');

    // Get current displayed value to animate from
    const currentText = display.textContent.replace(/\D/g, '');
    let currentVal = parseInt(currentText);
    if (isNaN(currentVal)) currentVal = 0;

    // If banner was hidden, current value should visually start from 0
    if (banner.style.display === 'none' || banner.style.display === '') {
        currentVal = 0;
    }

    if (total > 0) {
        banner.style.display = 'flex';

        // Only animate if value changed
        if (currentVal !== total) {
            animateValue(display, currentVal, total, 500); // 500ms duration
        }
    } else {
        banner.style.display = 'none';
        display.textContent = '0 ₽';
    }
}

// Helper to pluralize points in Russian
function getPointsPlural(n) {
    const lastDigit = n % 10;
    const lastTwo = n % 100;
    if (lastTwo >= 11 && lastTwo <= 19) return 'баллов';
    if (lastDigit === 1) return 'балл';
    if (lastDigit >= 2 && lastDigit <= 4) return 'балла';
    return 'баллов';
}

// Easing function and animation for count-up effect
function animateValue(obj, start, end, duration) {
    let startTimestamp = null;

    // Cancel any existing animation on this object
    if (obj.animationId) {
        window.cancelAnimationFrame(obj.animationId);
    }

    const step = (timestamp) => {
        if (!startTimestamp) startTimestamp = timestamp;
        // Don't animate if duration is 0
        if (duration === 0) {
            const points = 10 + Math.floor(end / 1000);
            obj.textContent = end.toLocaleString('ru-RU') + ' ₽ | 🏆 +' + points + ' ' + getPointsPlural(points);
            return;
        }

        const progress = Math.min((timestamp - startTimestamp) / duration, 1);
        // easeOutQuart
        const ease = 1 - Math.pow(1 - progress, 4);
        const current = Math.floor(ease * (end - start) + start);

        const currentPoints = 10 + Math.floor(current / 1000);
        obj.textContent = current.toLocaleString('ru-RU') + ' ₽ | 🏆 +' + currentPoints + ' ' + getPointsPlural(currentPoints);

        if (progress < 1) {
            obj.animationId = window.requestAnimationFrame(step);
        } else {
            const points = 10 + Math.floor(end / 1000);
            obj.textContent = end.toLocaleString('ru-RU') + ' ₽ | 🏆 +' + points + ' ' + getPointsPlural(points);
            obj.animationId = null;
        }
    };

    obj.animationId = window.requestAnimationFrame(step);
}


function addItem() {
    // Collapse existing items
    collapseAllItems();

    // Create new item
    const div = document.createElement('div');
    div.className = 'item-card';
    // ID and Title will be fixed by renumberItems()
    div.innerHTML = `
                <div class="item-header" onclick="toggleItem(this)">
                    <div class="item-header-left">
                        <span class="drag-handle" title="Перетащите для сортировки">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <line x1="3" y1="6" x2="21" y2="6"></line>
                                <line x1="3" y1="12" x2="21" y2="12"></line>
                                <line x1="3" y1="18" x2="21" y2="18"></line>
                            </svg>
                        </span>
                        <div class="item-header-info">
                            <span class="item-title">Предмет</span>
                            <span class="item-summary"></span>
                        </div>
                    </div>
                    <div class="item-header-actions">
                        <span class="item-toggle" aria-hidden="true">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                                stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="6 9 12 15 18 9"></polyline>
                            </svg>
                        </span>
                        <!-- Remove button will be added by renumberItems if needed -->
                    </div>
                </div>
                <div class="item-body">
                    <div class="form-group desc-group">
                        <input type="text" class="desc item-field" placeholder="Кольцо, металл желтого цвета" required id="desc-${itemCount}">
                        <label class="floating-label" for="desc-${itemCount}">Описание</label>
                        <button type="button" class="mic-btn" onclick="startSpeechRecognition(this, 'desc-${itemCount}')" title="Голосовой ввод">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path>
                                <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                                <line x1="12" y1="19" x2="12" y2="22"></line>
                            </svg>
                        </button>
                        <div class="error-message"></div>
                        <div class="input-hint">
                            Добавьте краткое описание предмета или надиктуйте голосом
                        </div>
                    </div>
                    <div class="form-group">
                        <input type="tel" class="eval item-field" placeholder="Сумма" required inputmode="numeric" id="eval-${itemCount}">
                        <label class="floating-label" for="eval-${itemCount}">Оценка (руб.)</label>
                        <div class="error-message"></div>
                        <div class="input-hint">Только цифры (например, 10 000)</div>
                    </div>
                    <div class="photo-preview-container" 
                         ondragover="handleDragOver(event)" 
                         ondragleave="handleDragLeave(event)" 
                         ondrop="handleDrop(event, this)"
                         ontouchstart="handleTouchStart(event)"
                         ontouchmove="handleTouchMove(event)"
                         ontouchend="handleTouchEnd(event)">
                        <div class="skeleton-loader"></div>
                        <div class="photo-preview"></div>
                        <label class="upload-label">
                            <svg class="upload-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                                <circle cx="8.5" cy="8.5" r="1.5"></circle>
                                <polyline points="21 15 16 10 5 21"></polyline>
                            </svg>
                            <input type="file" class="file-input" accept="image/*" onchange="handleFileSelect(this)" style="display:none">
                            <span class="btn-text">Добавить фото</span>
                            <span class="hint">Нажмите для выбора или перетащите</span>
                        </label>
                        <div class="photo-actions">
                            <button type="button" class="photo-action-btn" onclick="handleReplacePhoto(this, event)">Заменить</button>
                            <button type="button" class="photo-action-btn danger" onclick="handleRemovePhoto(this, event)">Удалить</button>
                        </div>
                        <div class="upload-progress">
                            <div class="upload-progress-bar"></div>
                        </div>
                    </div>
                    <div class="upload-status">Добавьте одно фото предмета</div>
                </div>
            `;
    // --- ADDED EVENT LISTENERS ---
    // 1. Input Mask for Evaluation (Cleave.js)
    const evalInput = div.querySelector('.eval');
    if (window.Cleave) {
        new Cleave(evalInput, {
            numeral: true,
            numeralThousandsGroupStyle: 'thousand',
            delimiter: ' '
        });
    } else {
        evalInput.addEventListener('input', () => {
            evalInput.value = evalInput.value.replace(/\D/g, '');
        });
    }

    // Real-time total update
    evalInput.addEventListener('input', updateTotalCost);

    // 2. File Input Trigger
    const fileInput = div.querySelector('.file-input');
    const previewContainer = div.querySelector('.photo-preview-container');

    // Handle click on container to trigger file input
    previewContainer.onclick = (e) => {
        // Prevent double trigger if clicking on label/input directly
        if (e.target !== fileInput && !e.target.closest('.upload-label')) {
            fileInput.click();
        }
    };

    // 3. Validation clearing
    const inputs = div.querySelectorAll('input');
    inputs.forEach(input => {
        input.addEventListener('input', () => {
            input.classList.remove('invalid');
            const errorMsg = input.closest('.form-group')?.querySelector('.error-message');
            if (errorMsg) errorMsg.classList.remove('show');
        });
    });


    // Fix numbering
    document.getElementById('itemsList').appendChild(div);

    // Enable drag-and-drop on new card
    initDragAndDrop(div);

    renumberItems();
}

function removeItem(btn, event) {
    if (event) event.stopPropagation();
    btn.closest('.item-card').remove();
    renumberItems();
    updateTotalCost();
}

function renumberItems() {
    const items = document.querySelectorAll('.item-card');
    items.forEach((card, index) => {
        const num = index + 1;
        card.id = `item-${num}`;

        // Update Title
        const title = card.querySelector('.item-title');
        if (title) title.textContent = `Предмет #${num}`;

        // Update Remove Button visibility
        const headerBtnContainer = card.querySelector('.item-header-actions');
        if (headerBtnContainer) {
            const removeBtn = headerBtnContainer.querySelector('.btn-remove');
            if (num > 1) {
                if (!removeBtn) {
                    headerBtnContainer.insertAdjacentHTML(
                        'beforeend',
                        `<button type="button" class="btn-remove" onclick="removeItem(this, event)">
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                                    Удалить
                                </button>`
                    );
                }
            } else if (removeBtn) {
                removeBtn.remove();
            }
        }
    });

    // Update global counter
    itemCount = items.length;
    updateBadge();
}

function collapseAllItems() {
    document.querySelectorAll('.item-card').forEach(card => {
        card.classList.add('collapsed');
        updateItemSummary(card);
    });
}

function updateItemSummary(card) {
    const desc = card.querySelector('.desc').value;
    const price = card.querySelector('.eval').value;
    const hasPhoto = card.querySelector('.file-input').files.length > 0;

    let summary = [];
    if (desc) summary.push(desc);
    if (price) {
        // Check if formatNumberWithSpaces exists (might not be loaded yet on initial load)
        if (typeof formatNumberWithSpaces === 'function') {
            summary.push(formatNumberWithSpaces(price) + ' ₽');
        } else {
            summary.push(price + ' ₽');
        }
    }
    if (hasPhoto) summary.push('📷 Фото');

    const summaryText = summary.join(', ') || 'Нет данных';
    card.querySelector('.item-summary').textContent = summaryText;
}

function toggleItem(header) {
    const card = header.closest('.item-card');
    if (card.classList.contains('collapsed')) {
        card.classList.remove('collapsed');
    } else {
        card.classList.add('collapsed');
        updateItemSummary(card);
    }
}

function updateBadge() {
    const count = document.getElementById('itemsList').children.length;
    const badge = document.getElementById('itemCountBadge');
    if (badge) {
        badge.textContent = count;
        // Optional: Hide badge if 0 (though we always have 1 item)
        // badge.style.display = count > 0 ? 'inline-block' : 'none';
    }
}

// --- UX Features ---

// Helper for formatting numbers
function formatNumberWithSpaces(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

// 1. Drag & Drop
function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.style.borderColor = 'var(--primary-color)';
    e.currentTarget.style.background = 'rgba(0, 122, 255, 0.05)';
}

function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.style.borderColor = 'rgba(0, 0, 0, 0.1)';
    e.currentTarget.style.background = 'rgba(0, 0, 0, 0.03)';
}

function handleDrop(e, container) {
    e.preventDefault();
    e.stopPropagation();

    container.style.borderColor = 'rgba(0, 0, 0, 0.1)';
    container.style.background = 'rgba(0, 0, 0, 0.03)';

    const dt = e.dataTransfer;
    const files = dt.files;

    if (files && files[0]) {
        const fileInput = container.querySelector('.file-input');
        fileInput.files = files;
        handleFileSelect(fileInput);
    }
}

// 3. Input Mask for Ticket (Digits only, max 11) + Auto-focus
document.getElementById('ticket').addEventListener('input', function (e) {
    e.target.value = e.target.value.replace(/\D/g, '').substring(0, 11);

    // \u2705 UX: Auto-focus to date field when 11 digits entered
    if (e.target.value.length === 11) {
        document.getElementById('date').focus();
    }
});

// Input Mask for Department and Issue (Digits only)
['department', 'issue'].forEach(id => {
    document.getElementById(id).addEventListener('input', function (e) {
        e.target.value = e.target.value.replace(/\D/g, '');
    });
});

// Smart focus: move to next field on Enter
const focusOrder = ['department', 'issue', 'ticket', 'date', 'region'];
focusOrder.forEach((id, index) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.setAttribute('enterkeyhint', index < focusOrder.length - 1 ? 'next' : 'done');
    el.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            const nextId = focusOrder[index + 1];
            if (nextId) {
                document.getElementById(nextId)?.focus();
            }
        }
    });
});

// Input Mask for Evaluation (Thousands Separator)
// Dynamically attached in addItem() but also need utility function
function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

function cleanNumber(str) {
    return str.replace(/\s/g, '');
}

// Auto-save on input
['department', 'issue', 'ticket', 'date', 'region'].forEach(id => {
    document.getElementById(id)?.addEventListener('change', saveDraft);
});

// Restore draft on load
restoreDraft();

// ============================================
// SERVICE WORKER & OFFLINE MODE
// ============================================
if ('serviceWorker' in navigator) {
    const swVersion = '2400';
    const basePath = location.pathname.endsWith('/') ? location.pathname : `${location.pathname}/`;
    const swUrl = `${basePath}service-worker.js?v=${swVersion}`;
    navigator.serviceWorker.register(swUrl)
        .then(reg => console.log('Service Worker registered:', reg.scope))
        .catch(err => console.error('Service Worker registration failed:', err));

    // Listen for sync messages from SW
    navigator.serviceWorker.addEventListener('message', (event) => {
        if (event.data && event.data.type === 'SYNC_COMPLETE') {
            showOfflineBanner('✅ Заключение из очереди успешно отправлено!', true);
        }
    });
}

// --- Offline Banner UI ---
function showOfflineBanner(text, isOnline) {
    const banner = document.getElementById('offlineBanner');
    const bannerText = document.getElementById('offlineBannerText');
    if (!banner) return;
    banner.classList.remove('hiding', 'online');
    if (isOnline) banner.classList.add('online');
    bannerText.textContent = text || (isOnline ? 'Подключение восстановлено' : 'Нет подключения');
    banner.style.display = 'flex';

    if (isOnline) {
        setTimeout(() => {
            banner.classList.add('hiding');
            setTimeout(() => { banner.style.display = 'none'; }, 400);
        }, 3000);
    }
}

function hideOfflineBanner() {
    const banner = document.getElementById('offlineBanner');
    if (!banner) return;
    banner.classList.add('hiding');
    setTimeout(() => { banner.style.display = 'none'; }, 400);
}

// Monitor network status
window.addEventListener('offline', () => {
    showOfflineBanner('📴 Нет подключения — данные будут сохранены и отправлены автоматически', false);
});

// Show banner on load if offline
if (!navigator.onLine) {
    showOfflineBanner('📴 Нет подключения — данные будут сохранены', false);
}

// Offline queue using IndexedDB
async function openOfflineDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open('ReportsDB', 1);
        request.onerror = () => reject(request.error);
        request.onsuccess = () => resolve(request.result);
        request.onupgradeneeded = (event) => {
            const db = event.target.result;
            if (!db.objectStoreNames.contains('pending')) {
                db.createObjectStore('pending', { keyPath: 'id', autoIncrement: true });
            }
        };
    });
}

async function savePendingReport(data) {
    try {
        const db = await openOfflineDB();
        const tx = db.transaction('pending', 'readwrite');
        const store = tx.objectStore('pending');
        store.add({ data, timestamp: Date.now() });
        await new Promise((resolve, reject) => {
            tx.oncomplete = resolve;
            tx.onerror = () => reject(tx.error);
        });
        console.log('Report saved to offline queue');
        showOfflineBanner('📦 Заключение сохранено в очередь — отправится при появлении сети', false);
        return true;
    } catch (error) {
        console.error('Failed to save to offline queue:', error);
        return false;
    }
}

async function getPendingCount() {
    try {
        const db = await openOfflineDB();
        const tx = db.transaction('pending', 'readonly');
        const store = tx.objectStore('pending');
        return new Promise((resolve) => {
            const req = store.count();
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => resolve(0);
        });
    } catch { return 0; }
}

// Online event - sync pending reports
window.addEventListener('online', async () => {
    console.log('Connection restored, syncing...');
    showOfflineBanner('✅ Соединение восстановлено! Синхронизация...', true);

    try {
        const db = await openOfflineDB();
        const tx = db.transaction('pending', 'readonly');
        const store = tx.objectStore('pending');
        const getAllReq = store.getAll();
        const pending = await new Promise((resolve) => {
            getAllReq.onsuccess = () => resolve(getAllReq.result);
            getAllReq.onerror = () => resolve([]);
        });

        if (pending.length > 0) {
            let synced = 0;
            for (const item of pending) {
                try {
                    await submitData(item.data);
                    const deleteTx = db.transaction('pending', 'readwrite');
                    deleteTx.objectStore('pending').delete(item.id);
                    synced++;
                } catch (error) {
                    console.error('Failed to sync report:', error);
                }
            }
            if (synced > 0) {
                showOfflineBanner(`🎉 Синхронизировано ${synced} из ${pending.length} заключений!`, true);
            }
        } else {
            showOfflineBanner('✅ Подключение восстановлено', true);
        }
    } catch (error) {
        console.error('Failed to sync:', error);
    }
});

// ============================================
// DRAG-AND-DROP CARD SORTING
// ============================================
let dragSrcCard = null;

function initDragAndDrop(card) {
    card.setAttribute('draggable', 'true');

    card.addEventListener('dragstart', (e) => {
        dragSrcCard = card;
        card.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', card.id);
        haptic('medium'); // Haptic on pickup
    });

    card.addEventListener('dragend', () => {
        card.classList.remove('dragging');
        document.querySelectorAll('.item-card.drag-over').forEach(c => c.classList.remove('drag-over'));
        dragSrcCard = null;
    });

    card.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        if (card !== dragSrcCard) {
            if (!card.classList.contains('drag-over')) {
                haptic('light'); // Haptic when crossing over another card
            }
            card.classList.add('drag-over');
        }
    });

    card.addEventListener('dragleave', () => {
        card.classList.remove('drag-over');
    });

    card.addEventListener('drop', (e) => {
        e.preventDefault();
        card.classList.remove('drag-over');
        if (dragSrcCard && dragSrcCard !== card) {
            const list = document.getElementById('itemsList');
            const cards = Array.from(list.children);
            const fromIndex = cards.indexOf(dragSrcCard);
            const toIndex = cards.indexOf(card);

            if (fromIndex < toIndex) {
                list.insertBefore(dragSrcCard, card.nextSibling);
            } else {
                list.insertBefore(dragSrcCard, card);
            }

            renumberItems();
            haptic('light');
        }
    });
}


// 4. Smart Memory (Department & Region)
const deptInput = document.getElementById('department');

// Load defaults if not draft
if (deptInput && regionInput && !localStorage.getItem('formDraft')) {
    const savedDept = localStorage.getItem('default_department');
    const savedRegion = localStorage.getItem('default_region');
    if (savedDept) deptInput.value = savedDept;
    if (savedRegion) regionInput.value = savedRegion;
}

// Save on change
if (deptInput) {
    deptInput.addEventListener('change', (e) => {
        localStorage.setItem('default_department', e.target.value);
    });
}

if (regionInput) {
    regionInput.addEventListener('change', (e) => {
        localStorage.setItem('default_region', e.target.value);
    });
}

function setUploadProgress(previewContainer, percent) {
    const progress = previewContainer.querySelector('.upload-progress');
    const bar = previewContainer.querySelector('.upload-progress-bar');
    if (!progress || !bar) return;

    if (percent === null) {
        progress.classList.remove('visible');
        bar.style.width = '0%';
        return;
    }

    const safePercent = Math.max(0, Math.min(100, percent));
    progress.classList.add('visible');
    bar.style.width = `${safePercent}%`;

    if (safePercent >= 100) {
        setTimeout(() => {
            progress.classList.remove('visible');
            bar.style.width = '0%';
        }, 400);
    }
}

function handleReplacePhoto(button, event) {
    if (event) event.stopPropagation();
    const container = button.closest('.item-card');
    const input = container?.querySelector('.file-input');
    if (input) {
        input.click();
    }
}

function handleRemovePhoto(button, event) {
    if (event) event.stopPropagation();
    const container = button.closest('.item-card');
    if (!container) return;

    const input = container.querySelector('.file-input');
    const previewContainer = container.querySelector('.photo-preview-container');
    const status = container.querySelector('.upload-status');
    const btnText = container.querySelector('.btn-text');

    if (input) {
        input.value = '';
    }

    const img = previewContainer.querySelector('.photo-preview-img');
    if (img) img.remove();

    const label = previewContainer.querySelector('.upload-label');
    if (label) label.style.opacity = '1';

    previewContainer.classList.remove('loading');
    previewContainer.classList.remove('has-photo');
    delete container.dataset.photoUrl;

    setUploadProgress(previewContainer, null);

    if (btnText) btnText.textContent = "Добавить фото";
    if (status) {
        status.textContent = "Добавьте одно фото предмета";
        status.className = "upload-status";
    }
}

async function handleFileSelect(input) {
    const file = input.files[0];
    if (!file) return;

    const container = input.closest('.item-card');
    const previewContainer = container.querySelector('.photo-preview-container');
    const btnText = container.querySelector('.btn-text');
    const status = container.querySelector('.upload-status');

    previewContainer.classList.remove('photo-invalid');
    previewContainer.style.borderColor = '';
    previewContainer.style.animation = 'none';

    // Show loading state
    previewContainer.classList.add('loading');
    const skeleton = previewContainer.querySelector('.skeleton-loader');
    if (skeleton) skeleton.style.display = 'block';
    const compressionAvailable = typeof imageCompression === 'function';
    btnText.textContent = compressionAvailable ? "Сжатие..." : "Подготовка...";
    status.textContent = "⏳ Обработка фото...";
    status.className = "upload-status";
    delete container.dataset.photoUrl;
    setUploadProgress(previewContainer, null);

    try {
        // Compression options
        const options = {
            maxSizeMB: 1,
            maxWidthOrHeight: 1280, // Optimized for speed
            useWebWorker: true,
            fileType: 'image/jpeg'
        };

        if (compressionAvailable) {
            console.log(`Original: ${(file.size / 1024 / 1024).toFixed(2)} MB`);
        }

        // Compress (fallback to original if library is unavailable)
        const compressedFile = compressionAvailable ? await imageCompression(file, options) : file;

        if (compressionAvailable) {
            console.log(`Compressed: ${(compressedFile.size / 1024 / 1024).toFixed(2)} MB`);
        }

        // Show preview
        const reader = new FileReader();
        reader.onload = function (e) {
            // Create or get IMG element
            let img = previewContainer.querySelector('.photo-preview-img');
            if (!img) {
                img = document.createElement('img');
                img.className = 'photo-preview-img';
                img.style.cssText = 'position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; z-index: 10; border-radius: 16px;';
                previewContainer.appendChild(img);
            }

            img.src = e.target.result;
            img.style.display = 'block';

            if (skeleton) skeleton.style.display = 'none';

            // Hide placeholder elements
            const label = previewContainer.querySelector('.upload-label');
            if (label) label.style.opacity = '0';

            previewContainer.classList.add('has-photo');

            // Lightbox trigger
            img.onclick = (evt) => {
                evt.stopPropagation();
                openLightbox(e.target.result);
            };
        };
        reader.readAsDataURL(compressedFile);

        // 🚀 BACKGROUND UPLOAD with Compressed File
        btnText.textContent = "Загрузка...";
        status.textContent = "⏳ Загрузка: 0%";
        setUploadProgress(previewContainer, 0);

        const uploadedUrl = await uploadImageToBot(compressedFile, (percent) => {
            const safePercent = Math.max(0, Math.min(100, percent));
            setUploadProgress(previewContainer, safePercent);
            if (safePercent > 0 && safePercent < 100) {
                status.textContent = `⏳ Загрузка: ${safePercent}%`;
            }
        });

        // Store URL
        container.dataset.photoUrl = uploadedUrl;

        // Success UI
        previewContainer.classList.remove('loading');
        setUploadProgress(previewContainer, 100);
        btnText.textContent = "✓ Загружено";
        status.textContent = "✅ Готово к отправке";
        status.className = "upload-status success";
        haptic('success', { sound: true, vibrate: true });

    } catch (error) {
        const skeleton = previewContainer.querySelector('.skeleton-loader');
        if (skeleton) skeleton.style.display = 'none';
        console.error('Processing failed:', error);
        btnText.textContent = "❌ Ошибка";
        status.textContent = `⚠️ ${error.message || 'Ошибка обработки'}`;
        status.className = "upload-status";
        haptic('error');

        // Reset UI
        input.value = '';
        const previewDiv = previewContainer.querySelector('.photo-preview');
        previewDiv.style.backgroundImage = ''; // Clear background image
        previewDiv.innerHTML = ''; // Clear any content

        // Restore default upload label content if it was removed/hidden
        const uploadLabel = previewContainer.querySelector('.upload-label');
        if (uploadLabel) {
            uploadLabel.style.display = 'flex'; // Ensure it's visible
            btnText.textContent = "Добавить фото"; // Reset text
            previewContainer.querySelector('.hint').style.display = 'block'; // Show hint
        }

        previewContainer.classList.remove('loading');
        previewContainer.classList.remove('has-photo');
        delete container.dataset.photoUrl;
        setUploadProgress(previewContainer, null);

        // Re-attach click handler for upload
        previewContainer.onclick = (e) => {
            if (e.target !== input && !e.target.closest('.upload-label')) {
                input.click();
            }
        };
    }
}

// New function to handle Bot API upload
async function uploadImageToBot(file, onProgress) {
    if (imagebanClientId) {
        return await uploadImageToImageBan(file, onProgress);
    }

    const compressedBlob = file;
    const formData = new FormData();
    formData.append('image', compressedBlob, 'image.jpg');

    const baseUrl = typeof botUrl !== 'undefined' ? botUrl : '';
    const cleanBase = baseUrl.replace(/\/$/, "");
    const uploadUrl = `${cleanBase}/api/upload-photo`;

    const result = await uploadWithRetry(
        () => uploadWithProgress(uploadUrl, formData, {}, onProgress),
        1
    );
    if (result && result.data && result.data.url) {
        return result.data.url;
    }
    throw new Error(result?.error || "Неизвестная ошибка загрузки");
}

async function uploadImageToImageBan(file, onProgress) {
    const formData = new FormData();
    formData.append('image', file, file.name || 'image.jpg');
    const result = await uploadWithRetry(
        () => uploadWithProgress(
            'https://api.imageban.ru/v1',
            formData,
            { 'Authorization': `TOKEN ${imagebanClientId}` },
            onProgress
        ),
        1
    );
    const link = result?.data?.[0]?.link || result?.data?.link;
    if (result?.success && link) {
        return link;
    }

    const message = result?.message || result?.error || "Ошибка загрузки в ImageBan";
    throw new Error(message);
}

function shouldRetryUpload(error) {
    const msg = (error && error.message) ? error.message : '';
    if (msg.startsWith('HTTP 4')) return false;
    return true;
}

async function uploadWithRetry(fn, retries = 1) {
    let lastErr;
    for (let attempt = 0; attempt <= retries; attempt += 1) {
        try {
            return await fn();
        } catch (err) {
            lastErr = err;
            if (attempt >= retries || !shouldRetryUpload(err)) {
                break;
            }
            await new Promise(resolve => setTimeout(resolve, 800 * (attempt + 1)));
        }
    }
    throw lastErr;
}

function uploadWithProgress(url, formData, headers, onProgress) {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.timeout = 45000;
        xhr.open('POST', url, true);
        if (headers) {
            Object.entries(headers).forEach(([key, value]) => {
                xhr.setRequestHeader(key, value);
            });
        }

        if (xhr.upload && onProgress) {
            xhr.upload.onprogress = (event) => {
                if (!event.lengthComputable) return;
                const percent = Math.round((event.loaded / event.total) * 100);
                onProgress(percent);
            };
        }

        xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                try {
                    resolve(JSON.parse(xhr.responseText));
                } catch (err) {
                    reject(new Error('Ошибка ответа сервера'));
                }
            } else {
                reject(new Error(`HTTP ${xhr.status}`));
            }
        };

        xhr.onerror = () => reject(new Error('Ошибка сети'));
        xhr.ontimeout = () => reject(new Error('Превышено время ожидания'));
        xhr.send(formData);
    });
}

// Lightbox Functions
function openLightbox(src) {
    const modal = document.getElementById('lightboxModal');
    const img = document.getElementById('lightboxImage');
    img.src = src;
    modal.style.display = 'flex'; // Flex to center
    modal.style.alignItems = 'center';
    modal.style.justifyContent = 'center';
}

function closeLightbox() {
    document.getElementById('lightboxModal').style.display = 'none';
}

// Confetti Trigger
function fireConfetti() {
    if (typeof confetti === 'function') {
        confetti({
            particleCount: 100,
            spread: 70,
            origin: { y: 0.6 }
        });
    }
}

// 5. Telegram Native UI & Haptic Feedback
const mainButton = tg.MainButton;

// State Machine Button Handler
function handleMainButton() {
    if (appState === 'editing') {
        showPreview();
    } else if (appState === 'preview') {
        submitForm();
    }
}

function updateMainButton() {
    // Keep HTML buttons visible
    const mainFormBtn = document.querySelector('.btn-primary[onclick="showPreview()"]');
    if (mainFormBtn) {
        mainFormBtn.style.display = 'block';
    }
    const finalBtn = document.getElementById('finalSubmitBtn');
    if (finalBtn) {
        finalBtn.style.display = 'block';
    }

    if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
        // We are in Telegram, configure the native MainButton too
        mainButton.setText("ПРОВЕРИТЬ И ОТПРАВИТЬ");
        mainButton.show();
        // Use single state-based handler and clear existing to prevent duplicates
        mainButton.offClick(handleMainButton);
        mainButton.onClick(handleMainButton);
    }
}

// Call on load
updateMainButton();

// Haptic Feedback Helper
function haptic(type = 'light', opts = {}) {
    const sound = opts && opts.sound === true;
    const vibrate = opts && opts.vibrate === true;

    if (tg.HapticFeedback) {
        switch (type) {
            case 'light':
            case 'medium':
            case 'heavy':
            case 'rigid':
            case 'soft':
                tg.HapticFeedback.impactOccurred(type);
                break;
            case 'error':
            case 'success':
            case 'warning':
                tg.HapticFeedback.notificationOccurred(type);
                break;
            case 'selection':
                tg.HapticFeedback.selectionChanged();
                break;
            default:
                tg.HapticFeedback.impactOccurred('light');
        }
    } else if (vibrate && navigator.vibrate) {
        const pattern = type === 'error' ? [30, 40, 30] : 20;
        navigator.vibrate(pattern);
    }

    if (sound) {
        const soundKind = type === 'error' ? 'error' : (type === 'success' ? 'success' : 'tap');
        playTone(soundKind);
    }
}

// Add haptic to interactive elements
document.querySelectorAll('input, select').forEach(el => {
    el.addEventListener('focus', () => haptic('light'));
});

document.querySelectorAll('.btn').forEach(btn => {
    btn.addEventListener('click', () => haptic('medium'));
});

function validateForm() {
    let isValid = true;
    let firstInvalidField = null; // Track first invalid for auto-scroll
    const requiredIds = ['department', 'issue', 'ticket', 'date', 'region'];

    requiredIds.forEach(id => {
        const el = document.getElementById(id);
        if (!el.value.trim()) {
            isValid = false;
            el.classList.add('invalid');
            if (!firstInvalidField) firstInvalidField = el;
            // Add listener to remove invalid class on input
            el.addEventListener('input', () => el.classList.remove('invalid'), { once: true });
        } else {
            // Specific checks
            if (id === 'ticket' && el.value.length !== 11) {
                isValid = false;
                el.classList.add('invalid');
                if (!firstInvalidField) firstInvalidField = el;
                el.addEventListener('input', () => el.classList.remove('invalid'), { once: true });
            }
        }
    });

    // Validate item fields (description and evaluation)
    document.querySelectorAll('.item-card').forEach((card) => {
        const desc = card.querySelector('.desc');
        const evalInput = card.querySelector('.eval');

        if (desc && !desc.value.trim()) {
            isValid = false;
            desc.classList.add('invalid');
            card.classList.remove('collapsed');
            if (!firstInvalidField) firstInvalidField = desc;
            desc.addEventListener('input', () => desc.classList.remove('invalid'), { once: true });
        }

        if (evalInput && !evalInput.value.trim()) {
            isValid = false;
            evalInput.classList.add('invalid');
            card.classList.remove('collapsed');
            if (!firstInvalidField) firstInvalidField = evalInput;
            evalInput.addEventListener('input', () => evalInput.classList.remove('invalid'), { once: true });
        }
    });

    if (!isValid) {
        // Auto-scroll to first invalid field
        if (firstInvalidField) {
            firstInvalidField.scrollIntoView({
                behavior: 'smooth',
                block: 'center'
            });

            // Focus after scroll animation
            setTimeout(() => {
                firstInvalidField.focus();
            }, 500);
        }

        tg.showAlert("Пожалуйста, заполните все обязательные поля корректно.");
        haptic('error');
    }

    return isValid;
}

function showPreview() {
    if (previewOpen || appState === 'preview') return;
    previewOpen = true;
    haptic('medium');
    // Centralized validation
    if (!validateForm()) {
        previewOpen = false;
        return;
    }

    // Check photos
    let allPhotosSelected = true;
    let firstMissingPhoto = null;
    document.querySelectorAll('.item-card').forEach(div => {
        const input = div.querySelector('.file-input');
        if (!input.files || !input.files[0]) {
            allPhotosSelected = false;
            const container = div.querySelector('.photo-preview-container');
            div.classList.remove('collapsed');
            container.classList.add('photo-invalid');
            container.style.borderColor = 'var(--danger-color)';
            container.style.animation = 'shake 0.4s cubic-bezier(.36, .07, .19, .97) both';
            if (!firstMissingPhoto) {
                firstMissingPhoto = container;
            }
            haptic('error');

            // Remove error on click/drop
            input.addEventListener('change', () => {
                container.style.borderColor = 'rgba(0, 0, 0, 0.1)';
                container.style.animation = 'none';
                container.classList.remove('photo-invalid');
            }, { once: true });
        }
    });

    if (!allPhotosSelected) {
        if (firstMissingPhoto) {
            firstMissingPhoto.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        tg.showAlert("Пожалуйста, выберите фото для всех предметов!");
        previewOpen = false;
        return;
    }

    const isTest = document.getElementById('mode-test').checked;
    const modeText = isTest ? "Черновик (Тест)" : "Оригинал (В группу)";
    const modeExplanation = isTest
        ? "Сообщение будет отправлено только вам для проверки."
        : "Сообщение будет отправлено в рабочий чат. Изменить после отправки нельзя.";

    // Calculate total cost (remove spaces before parsing)
    let totalCost = 0;
    const items = [];
    document.querySelectorAll('.item-card').forEach(div => {
        const evalInput = div.querySelector('.eval');
        const descInput = div.querySelector('.desc');
        if (evalInput && evalInput.value) {
            // Remove spaces and parse
            const cleanValue = evalInput.value.replace(/\s/g, '');
            const price = parseInt(cleanValue) || 0;
            totalCost += price;
            items.push({
                desc: descInput.value,
                price: price
            });
        }
    });

    // Get ticket value
    const ticketValue = document.getElementById('ticket').value;

    // Build items list
    let itemsList = '';
    items.forEach((item, idx) => {
        // Get image preview URL
        const fileInput = document.querySelectorAll('.item-card')[idx].querySelector('.file-input');
        const file = fileInput.files[0];
        const imgUrl = file ? URL.createObjectURL(file) : '';
        const imgTag = imgUrl ? `<img src="${imgUrl}" class="preview-image">` : '<div class="preview-image"></div>';

        itemsList += `
                    <div class="preview-item">
                        ${imgTag}
                        <div class="preview-item-content">
                            <div class="preview-item-desc">#${idx + 1} ${escapeHtml(item.desc)}</div>
                            <div class="preview-item-price">${item.price.toLocaleString('ru-RU')} ₽</div>
                        </div>
                    </div>
                `;
    });

    // Format Date
    const dateValue = document.getElementById('date').value;
    const dateParts = dateValue.split('-');
    const formattedDate = dateParts.length === 3 ? `${dateParts[2]}.${dateParts[1]}.${dateParts[0]}` : dateValue;

    // Build preview with premium structure
    const content = document.getElementById('previewContent');
    content.innerHTML = `
                <!-- Mode Section -->
                <div class="preview-card ${isTest ? 'mode-test' : 'mode-final'}">
                    <div class="preview-section-title" style="color: ${isTest ? '#FF8C00' : '#28a745'}; margin-bottom: 6px;">
                        ${isTest ? '🧪' : '🚀'} Режим: ${modeText}
                    </div>
                    <div style="font-size: 13px; color: var(--secondary-text); line-height: 1.4;">${modeExplanation}</div>
                </div>

                <!-- Main Data Section -->
                <div class="preview-card">
                    <div class="preview-section-title">📋 Основные данные</div>
                    <div class="preview-grid">
                        <span class="preview-label">Подразделение:</span>
                        <span class="preview-value">${escapeHtml(document.getElementById('department').value)}</span>
                        
                        <span class="preview-label">Регион:</span>
                        <span class="preview-value">${escapeHtml(document.getElementById('region').value)}</span>
                        
                        <span class="preview-label">Дата:</span>
                        <span class="preview-value">${formattedDate}</span>
                        
                        <span class="preview-label">№ заключения:</span>
                        <span class="preview-value">${escapeHtml(document.getElementById('issue').value)}</span>
                        
                        <span class="preview-label">№ билета:</span>
                        <span class="preview-value">${escapeHtml(document.getElementById('ticket').value)}</span>
                    </div>
                </div>

                <!-- Items Section -->
                <div class="preview-card">
                    <div class="preview-section-title">📦 Предметы (${items.length})</div>
                    ${itemsList}

                    <!-- SMART GUARD: Price Warning -->
                    ${totalCost > 100000 ? `
                        <div style="margin-top: 12px; padding: 10px; background: rgba(255, 152, 0, 0.1); border-left: 3px solid #FF9800; border-radius: 8px;">
                            <div style="color: #FF9800; font-weight: 600; font-size: 13px; margin-bottom: 4px;">💰 Крупная сумма</div>
                            <div style="color: var(--secondary-text); font-size: 12px;">Убедитесь, что оценка произведена корректно.</div>
                        </div>
                    ` : ''}
                </div>
            `;

    const previewModal = document.getElementById('previewModal');
    previewModal.style.display = 'block';
    requestAnimationFrame(() => previewModal.classList.add('show'));

    // Update state to preview mode
    appState = 'preview';
    if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
        mainButton.setText("ОТПРАВИТЬ");
    }
    haptic('success', { sound: true, vibrate: true });
}

function closePreview() {
    haptic('light');
    const previewModal = document.getElementById('previewModal');
    previewModal.classList.remove('show');
    setTimeout(() => {
        if (!previewModal.classList.contains('show')) {
            previewModal.style.display = 'none';
        }
    }, 250);

    // Revert state to editing
    appState = 'editing';
    previewOpen = false;
    if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
        mainButton.setText("ПРОВЕРИТЬ И ОТПРАВИТЬ");
    }
}

// Image Compression Helper
function compressImage(file) {
    return new Promise((resolve, reject) => {
        const maxWidth = 1280;
        const maxHeight = 1280;
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = function (event) {
            const img = new Image();
            img.src = event.target.result;
            img.onload = function () {
                let width = img.width;
                let height = img.height;

                if (width > height) {
                    if (width > maxWidth) {
                        height *= maxWidth / width;
                        width = maxWidth;
                    }
                } else {
                    if (height > maxHeight) {
                        width *= maxHeight / height;
                        height = maxHeight;
                    }
                }

                const canvas = document.createElement('canvas');
                canvas.width = width;
                canvas.height = height;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0, width, height);

                canvas.toBlob(function (blob) {
                    resolve(blob);
                }, 'image/jpeg', 0.8); // 80% quality
            };
            img.onerror = reject;
        };
        reader.onerror = reject;
    });
}

async function submitForm() {
    if (submitInProgress) return;
    submitInProgress = true;
    // Disable button
    if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
        mainButton.showProgress();
        mainButton.disable();
    }

    const btn = document.getElementById('finalSubmitBtn');
    btn.disabled = true;
    btn.textContent = "Подготовка данных...";

    const items = [];
    const cards = document.querySelectorAll('.item-card');

    // 🚀 NEW: Use pre-uploaded URLs instead of uploading again
    let allUploaded = true;
    for (let i = 0; i < cards.length; i++) {
        const div = cards[i];
        const photoUrl = div.dataset.photoUrl;

        // Check if photo was uploaded
        if (!photoUrl) {
            const fileInput = div.querySelector('.file-input');
            if (fileInput.files && fileInput.files[0]) {
                // Photo selected but not uploaded yet (shouldn't happen with background upload)
                allUploaded = false;
                tg.showAlert('⏳ Дождитесь загрузки всех фотографий');
                btn.disabled = false;
                btn.textContent = "Отправить";

                if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
                    mainButton.hideProgress();
                    mainButton.enable();
                }
                submitInProgress = false;
                return;
            }
            continue; // Skip items without photos
        }

        const rawEval = div.querySelector('.eval').value;
        const cleanEval = rawEval ? rawEval.replace(/\s/g, '') : '';

        // Use pre-uploaded URL
        items.push({
            description: div.querySelector('.desc').value,
            evaluation: cleanEval,
            photo_url: photoUrl
        });
    }

    if (items.length === 0) {
        tg.showAlert('❌ Нет загруженных фотографий');
        btn.disabled = false;
        btn.textContent = "Отправить";
        if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
            mainButton.hideProgress();
            mainButton.enable();
        }
        submitInProgress = false;
        return;
    }

    btn.textContent = "Отправка данных...";

    try {
        const isTest = document.getElementById('mode-test').checked;

        const data = {
            department_number: document.getElementById('department').value,
            issue_number: document.getElementById('issue').value,
            ticket_number: document.getElementById('ticket').value,
            date: document.getElementById('date').value.split('-').reverse().join('.'),
            region: document.getElementById('region').value,
            items: items,
            is_test: isTest
        };

        // CRITICAL: Validate date is not in the future (after formatting)
        const dateValue = document.getElementById('date').value; // YYYY-MM-DD
        const selectedDate = new Date(dateValue);
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        selectedDate.setHours(0, 0, 0, 0);

        if (selectedDate > today) {
            tg.showAlert('⚠️ Ошибка: Нельзя выбрать будущую дату!\n\nВыберите сегодняшнюю или прошедшую дату.');
            btn.disabled = false;
            btn.textContent = "Отправить";
            if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
                mainButton.hideProgress();
                mainButton.enable();
            }
            haptic('error');
            submitInProgress = false;
            return;
        }

        // Check if running in Telegram
        // iOS Telegram 9.x bug: initData may be empty even in WebApp
        // Instead, check for platform/version which are always present in Telegram
        console.log('tg.platform:', tg.platform);
        console.log('tg.version:', tg.version);
        console.log('tg.initData:', tg.initData);
        console.log('tg.initDataUnsafe:', tg.initDataUnsafe);

        // Check if we're in Telegram by platform/version presence
        const isInTelegram = (tg.platform && tg.platform.length > 0) ||
            (tg.version && tg.version.length > 0) ||
            (tg.initData && tg.initData.length > 0);

        if (isInTelegram) {
            console.log('Detected Telegram WebApp - sending via tg.sendData()');
            btn.textContent = "Отправка в Telegram...";
            tg.sendData(JSON.stringify(data));
            haptic('success', { sound: true, vibrate: true });

            // ✅ UX: Clear ticket for next form (always unique)
            document.getElementById('ticket').value = '';
            clearDraft();

            fireConfetti(); // 🎉 Celebration!

            // Close WebApp after sending data
            setTimeout(() => tg.close(), 1000);
        } else {
            // Standalone Mode
            btn.textContent = "Подключение к серверу...";

            // Add timeout to fetch
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 30000); // 30s timeout

            const response = await fetch(botUrl + '/api/generate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(data),
                signal: controller.signal
            });

            clearTimeout(timeoutId);

            if (!response.ok) {
                btn.textContent = "Ошибка сервера...";
                const err = await response.json().catch(() => ({}));
                throw new Error(err.error || `Server Error: ${response.status}`);
            }

            btn.textContent = "Скачивание файла...";

            // Download File
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `Conclusion_${data.ticket_number}.docx`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            clearDraft();

            // ✅ UX: Clear ticket for next form (always unique)
            document.getElementById('ticket').value = '';

            fireConfetti(); // 🎉 Celebration!
            haptic('success', { sound: true, vibrate: true });

            if (tg.showPopup) {
                tg.showPopup({ message: "✅ Документ готов и скачан!" });
            } else {
                alert("✅ Документ готов и скачан!");
            }
            closePreview();
            btn.disabled = false;
            btn.textContent = "Отправить";
            submitInProgress = false;
        }
    } catch (e) {
        console.error("Submission Error", e);
        haptic('error');

        if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
            mainButton.hideProgress();
            mainButton.enable();
        }

        if (e.name === 'AbortError') {
            if (tg.showPopup) {
                tg.showPopup({ message: "Ошибка: Превышено время ожидания (30с). Проверьте интернет или URL бота." });
            } else {
                alert("Ошибка: Превышено время ожидания (30с). Проверьте интернет или URL бота.");
            }
        } else {
            if (tg.showPopup) {
                tg.showPopup({ message: `Ошибка при отправке: ${e.message}` });
            } else {
                alert(`Ошибка при отправке: ${e.message}`);
            }
        }
        btn.disabled = false;
        btn.textContent = "Отправить";
        submitInProgress = false;
    }
}

// Initial item
addItem();

// ============================================
// AUTO-SAVE DRAFT & RESTORE
// ============================================
function saveDraft() {
    const draft = {
        department: document.getElementById('department').value,
        issue: document.getElementById('issue').value,
        // ticket: excluded - always unique per form
        date: document.getElementById('date').value,
        region: document.getElementById('region').value,
        timestamp: Date.now()
    };
    localStorage.setItem('formDraft', JSON.stringify(draft));
}

function restoreDraft() {
    const draftStr = localStorage.getItem('formDraft');
    if (!draftStr) return;

    const draft = JSON.parse(draftStr);
    // Only restore if draft is less than 24 hours old
    const hoursSinceLastSave = (Date.now() - draft.timestamp) / (1000 * 60 * 60);
    if (hoursSinceLastSave > 24) {
        localStorage.removeItem('formDraft');
        return;
    }

    // Restore values (ticket excluded - always unique)
    if (draft.department) document.getElementById('department').value = draft.department;
    if (draft.issue) document.getElementById('issue').value = draft.issue;
    // if (draft.ticket) document.getElementById('ticket').value = draft.ticket;  // ❌ Never restore
    if (draft.date) document.getElementById('date').value = draft.date;

    // Smart Auto-fill for Region
    const regionSelect = document.getElementById('region');
    if (draft.region) {
        regionSelect.value = draft.region;
    } else {
        // Check smart history
        const history = JSON.parse(localStorage.getItem('region_history') || '{}');
        // Find region with > 5 consecutive uses
        const smartRegion = Object.keys(history).find(r => history[r] >= 5);
        if (smartRegion) {
            regionSelect.value = smartRegion;
            // Optional: Visual cue that it was auto-selected?
        }
    }

    // Show notice
    const notice = document.getElementById('draftNotice');
    notice.style.display = 'block';
    setTimeout(() => {
        notice.style.opacity = '0';
        notice.style.transition = 'opacity 1s';
        setTimeout(() => notice.style.display = 'none', 1000);
    }, 3000);
}

// Track Region Selection
document.getElementById('region').addEventListener('change', (e) => {
    const region = e.target.value;
    if (!region) return;

    const history = JSON.parse(localStorage.getItem('region_history') || '{}');

    // Reset others, increment selected
    Object.keys(history).forEach(key => {
        if (key !== region) history[key] = 0;
    });

    history[region] = (history[region] || 0) + 1;
    localStorage.setItem('region_history', JSON.stringify(history));
});

function clearDraft() {
    localStorage.removeItem('formDraft');
}

// Update progress bar
function updateProgress(current, total) {
    const progressContainer = document.getElementById('progressContainer');
    const progressBar = document.getElementById('progressBar');
    const percent = (current / total) * 100;

    progressContainer.style.display = 'block';
    progressBar.style.width = percent + '%';

    if (current === total) {
        setTimeout(() => {
            progressContainer.style.display = 'none';
            progressBar.style.width = '0%';
        }, 1000);
    }
}

// Debounced auto-save (saves 1s after last input)
function debouncedAutosave() {
    clearTimeout(autosaveTimeout);
    autosaveTimeout = setTimeout(() => {
        saveDraft();
    }, 1000); // Save 1 second after last change
}

// Attach to all input/change events
document.getElementById('mainForm').addEventListener('input', debouncedAutosave);
document.getElementById('mainForm').addEventListener('change', debouncedAutosave);

// Smart Region: Load saved region
const savedRegion = localStorage.getItem('last_region');
if (savedRegion) {
    const regionSelect = document.getElementById('region');
    if (regionSelect) {
        regionSelect.value = savedRegion;
    }
}

// Save region on change
document.getElementById('region').addEventListener('change', (e) => {
    localStorage.setItem('last_region', e.target.value);
});

// Restore draft on page load
restoreDraft();

// --- SPEECH-TO-TEXT FOR DESCRIPTIONS ---
function startSpeechRecognition(btn, inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.showAlert) {
            window.Telegram.WebApp.showAlert("Голосовой ввод не поддерживается в вашем браузере/приложении. Пожалуйста, введите текст вручную.");
        } else {
            alert("Голосовой ввод не поддерживается в вашем браузере. Пожалуйста, введите текст вручную.");
        }
        return;
    }

    if (btn.classList.contains('listening')) {
        if (window.activeRecognition) {
            window.activeRecognition.stop();
        }
        return;
    }

    if (window.activeRecognition) {
        window.activeRecognition.stop();
    }

    const recognition = new SpeechRecognition();
    recognition.lang = 'ru-RU';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = function() {
        btn.classList.add('listening');
        btn.title = "Прослушивание... Нажмите, чтобы остановить";
        window.activeRecognition = recognition;
        
        if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.HapticFeedback) {
            window.Telegram.WebApp.HapticFeedback.triggerNotification('success');
        }
    };

    recognition.onresult = function(event) {
        const result = event.results[0][0].transcript;
        if (result) {
            if (input.value) {
                input.value += ' ' + result;
            } else {
                input.value = result;
            }
            input.dispatchEvent(new Event('input', { bubbles: true }));
        }
    };

    recognition.onerror = function(event) {
        console.error('Speech recognition error:', event.error);
        if (event.error === 'not-allowed') {
            if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.showAlert) {
                window.Telegram.WebApp.showAlert("Для голосового ввода необходимо разрешить доступ к микрофону.");
            } else {
                alert("Для голосового ввода необходимо разрешить доступ к микрофону.");
            }
        }
    };

    recognition.onend = function() {
        btn.classList.remove('listening');
        btn.title = "Голосовой ввод";
        if (window.activeRecognition === recognition) {
            window.activeRecognition = null;
        }
    };

    recognition.start();
}

// Global Clipboard Paste Support for Images
window.addEventListener('paste', async (e) => {
    if (appState !== 'editing') return;

    // Check if any modal is open
    const isModalOpen = ['guideModal', 'motivationModal', 'quizModal', 'lightboxModal', 'previewModal'].some(id => {
        const el = document.getElementById(id);
        return el && (el.style.display === 'flex' || el.style.display === 'block' || el.classList.contains('show'));
    });
    if (isModalOpen) return;

    const items = e.clipboardData?.items;
    if (!items) return;

    for (let i = 0; i < items.length; i++) {
        if (items[i].type.indexOf('image') !== -1) {
            const file = items[i].getAsFile();
            if (!file) continue;

            // Find target card
            const activeCard = document.activeElement ? document.activeElement.closest('.item-card') : null;
            const targetCard = activeCard || document.querySelector('.item-card:not(.collapsed)') || document.querySelector('.item-card');

            if (targetCard) {
                const fileInput = targetCard.querySelector('.file-input');
                if (fileInput) {
                    try {
                        const dataTransfer = new DataTransfer();
                        dataTransfer.items.add(file);
                        fileInput.files = dataTransfer.files;

                        // Highlight the target card's photo container briefly
                        const previewContainer = targetCard.querySelector('.photo-preview-container');
                        if (previewContainer) {
                            previewContainer.style.outline = '2px dashed var(--primary-color)';
                            setTimeout(() => {
                                previewContainer.style.outline = '';
                            }, 1000);
                        }

                        await handleFileSelect(fileInput);
                    } catch (err) {
                        console.error('Failed to paste image:', err);
                    }
                }
            }
            e.preventDefault();
            break;
        }
    }
});
