
const API = (typeof window !== 'undefined' && window.location.origin)
    ? window.location.origin
    : 'http://localhost:8000';

let sessionId = null;
let currentMode = 'edit';
let isStreaming = false;
let activeTurnController = null;
let activeHarnessProfile = 'general';
let userCancelledTurn = false;
let autoResumeTimer = null;
let autoResumeCountdown = null;
let autoResumeCard = null;
let autoResumeAttempt = 0;
let isListening = false;
let camStream = null;
let autoListenMode = false;
const SPEECH_ERROR_MAX_RETRIES = 3;
let speechErrorRetryCount = 0;
const SPEECH_SEND_DELAY_MS = 500;
const SPEECH_RESTART_DELAY_MS = 700;
let speechSendTimeout = null;
let pendingSendTranscript = null;
let safariVoiceHintShown = false;
let orb = null;
let recognition = null;
let ttsPlayer = null;
let pendingUploadBase64 = null;
let pendingUploadName = '';
let pendingUploadImages = [];
let pendingTextUploads = [];
let pendingUploadPreview = '';
let activeUploadChooser = null;
let currentResearchBranch = 'research';
let homeworkResponseTarget = 'chat';
let activeWorkspaceKey = 'edit';
const workspaceStates = new Map();
let pendingExternalWindow = null;
let pendingExternalUrl = '';
let guidePageIndex = 0;
const SETTINGS_KEY = 'jarvis_settings';
const DEFAULT_SETTINGS = { autoOpenActivity: true, autoOpenSearchResults: true, autoApproveSafeWork: true, thinkingSounds: true, voiceInterrupt: false };
const PRE_STARTER_FILES = ['starter_1', 'starter_2', 'starter_3', 'starter_4', 'starter_5', 'starter_6', 'starter_7', 'starter_8', 'starter_9', 'starter_10'];
let PRE_STARTER_CACHE = {};
let settings = { ...DEFAULT_SETTINGS };
const $ = id => document.getElementById(id);
const chatMessages = $('chat-messages');
const messageInput = $('message-input');
const chatModelSelector = $('chat-model-selector');
const sendBtn      = $('send-btn');
const stopTaskButton = $('stop-task-button');
const micBtn       = $('mic-btn');
const ttsBtn       = $('tts-btn');
const newChatBtn   = $('new-chat-btn');
const charCount    = $('char-count');
const welcomeTitle = $('welcome-title');
const modeSlider   = $('mode-slider');
const btnJarvis    = $('btn-jarvis');
const btnScraper   = $('btn-scraper');
const btnResearch  = $('btn-research');
const researchBranchSwitch = $('research-branch-switch');
const researchSourceControl = $('research-source-control');
const researchSourceToggle = $('research-source-toggle');
const researchSourceForm = $('research-source-form');
const researchSourceUrl = $('research-source-url');
const researchSourceManager = $('research-source-manager');
const researchSourcesToggle = $('research-sources-toggle');
const researchSourcesPopover = $('research-sources-popover');
const researchSourcesList = $('research-sources-list');
const researchSourceCount = $('research-source-count');
const researchSourceTokenTotal = $('research-source-token-total');
const homeworkSolutionBoard = $('homework-solution-board');
const homeworkLayoutDivider = $('homework-layout-divider');
const chatArea = $('chat-area');
const homeworkBoardContent = $('homework-board-content');
const homeworkBoardFiles = $('homework-board-files');
const researchFilesToggle = $('research-files-toggle');
const researchFilesPanel = $('research-files-panel');
const researchFilesClose = $('research-files-close');
const researchFilesList = $('research-files-list');
const researchFileEditor = $('research-file-editor');
const researchEditorBack = $('research-editor-back');
const researchEditorName = $('research-editor-name');
const researchEditorContent = $('research-editor-content');
const researchEditorStatus = $('research-editor-status');
const researchEditorDownload = $('research-editor-download');
const researchEditorSave = $('research-editor-save');
let activeResearchFile = null;
const statusDot    = document.querySelector('.status-dot');
const statusText   = document.querySelector('.status-text');
const orbContainer = $('orb-container');
const searchResultsToggle = $('search-results-toggle');
const searchResultsWidget = $('search-results-widget');
const searchResultsClose  = $('search-results-close');
const searchResultsQuery  = $('search-results-query');
const searchResultsAnswer = $('search-results-answer');
const searchResultsList   = $('search-results-list');
const activityPanel       = $('activity-panel');
const activityToggle      = $('activity-toggle');
const activityClose       = $('activity-close');
const activityList        = $('activity-list');
const historyPanel        = $('history-panel');
const historyToggle       = $('history-toggle');
const historyClose        = $('history-close');
const historyList         = $('history-list');
const panelOverlay        = $('panel-overlay');
const speechWidget        = $('speech-widget');
const speechWidgetText    = $('speech-widget-text');
const settingsBtn         = $('settings-btn');
const camBtn              = $('cam-btn');
const uploadBtn           = $('upload-btn');
const imageUploadInput    = $('image-upload-input');
const imageUploadPreview  = $('image-upload-preview');
const imageUploadThumb    = $('image-upload-thumb');
const imageUploadName     = $('image-upload-name');
const imageUploadRemove   = $('image-upload-remove');
const scrapeBtn           = $('scrape-btn');
const scrapeModal         = $('scrape-modal');
const scrapeModalClose    = $('scrape-modal-close');
const scrapeUrlInput      = $('scrape-url-input');
const scrapeModalGo       = $('scrape-modal-go');
const intelToggle         = $('intel-toggle');
const intelDashboard      = $('intel-dashboard');
const intelDashboardClose = $('intel-dashboard-close');
const intelTabs           = $('intel-tabs');
const intelTabContent     = $('intel-tab-content');
const camPanel            = $('cam-panel');
const camVideo            = $('cam-video');
const camCanvas           = $('cam-canvas');
const camVisionModeInput  = $('cam-vision-mode');
const camMinimize         = $('cam-minimize');
const camClose            = $('cam-close');
const camPanelHeader      = $('cam-panel-header');
const camPanelResize      = $('cam-panel-resize');
const settingsPanel       = $('settings-panel');
const settingsClose       = $('settings-close');
const toggleAutoActivity  = $('toggle-auto-activity');
const toggleAutoSearch    = $('toggle-auto-search');
const toggleAutoApproveWork = $('toggle-auto-approve-work');
const toggleThinkingSounds = $('toggle-thinking-sounds');
const toggleVoiceInterrupt = $('toggle-voice-interrupt');
const modelProviderOrder = $('model-provider-order');
const modelGroqKeys = $('model-groq-keys');
const modelGeminiKey = $('model-gemini-key');
const modelOpenRouterKey = $('model-openrouter-key');
const modelGroqModel = $('model-groq-model');
const modelGeminiModel = $('model-gemini-model');
const modelOpenRouterModel = $('model-openrouter-model');
const modelSettingsSave = $('model-settings-save');
const modelRouterStatus = $('model-router-status');
const modelProviderStatuses = $('model-provider-statuses');
const modelSettingsTest = $('model-settings-test');
const modelTestResults = $('model-test-results');
const toastContainer     = $('toast-container');
const guideBtn           = $('guide-btn');
const guideModal         = $('guide-modal');
const guideClose         = $('guide-close');
const guideBack          = $('guide-back');
const guideNext          = $('guide-next');
const guideStepLabel     = $('guide-step-label');
const googleConnectModal = $('google-connect-modal');
const googleConnectButton = $('google-connect-button');
const googleConnectLater = $('google-connect-later');
let googleConnectPoll = null;

class PreStarterPlayer {
    constructor() {
        this.audio = document.createElement('audio');
        this.audio.preload = 'auto';
    }
    play(onComplete) {
        const loaded = PRE_STARTER_FILES.filter(f => PRE_STARTER_CACHE[f]);
        if (loaded.length === 0) {
            if (onComplete) onComplete();
            return;
        }
        const file = loaded[Math.floor(Math.random() * loaded.length)];
        const base64 = PRE_STARTER_CACHE[file];
        if (!base64) {
            if (onComplete) onComplete();
            return;
        }
        this.audio.src = 'data:audio/mp3;base64,' + base64;
        this.audio.currentTime = 0;
        let fired = false;
        const done = () => {
            if (fired) return;
            fired = true;
            this.audio.onended = null;
            this.audio.onerror = null;
            if (onComplete) onComplete();
        };
        this.audio.onended = done;
        this.audio.onerror = done;
        const p = this.audio.play();
        if (p) p.catch(done);
    }
    stop() {
        this.audio.pause();
        this.audio.removeAttribute('src');
        this.audio.load();
    }
}

let preStarterPlayer = null;

class TTSPlayer {
    constructor() {
        this.queue = [];
        this.playing = false;
        this.enabled = true;
        this.stopped = false;
        this.audio = document.createElement('audio');
        this.audio.preload = 'auto';
    }
    unlock() {
        const silentWav = 'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA';
        this.audio.src = silentWav;
        const p = this.audio.play();
        if (p) p.catch(() => {});
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const g = ctx.createGain();
            g.gain.value = 0;
            const o = ctx.createOscillator();
            o.connect(g);
            g.connect(ctx.destination);
            o.start(0);
            o.stop(ctx.currentTime + 0.001);
            setTimeout(() => ctx.close(), 200);
        } catch (_) {}
    }
    enqueue(base64Audio) {
        if (!this.enabled || this.stopped) return;
        this.queue.push(base64Audio);
        if (!this.playing) this._playLoop();
    }
    stop() {
        this.stopped = true;
        this.audio.pause();
        this.audio.removeAttribute('src');
        this.audio.load();
        this.queue = [];
        this.playing = false;
        if (ttsBtn) ttsBtn.classList.remove('tts-speaking');
        if (orbContainer) orbContainer.classList.remove('speaking');
        if (orb) orb.setActive(false);
        if (typeof this.onPlaybackComplete === 'function') this.onPlaybackComplete();
    }
    reset() {
        this.stop();
        this.stopped = false;
        this._loopId = (this._loopId || 0) + 1;
    }
    async _playLoop() {
        if (this.playing) return;
        this.playing = true;
        this._loopId = (this._loopId || 0) + 1;
        const myId = this._loopId;
        if (ttsBtn) ttsBtn.classList.add('tts-speaking');
        if (orbContainer) orbContainer.classList.add('speaking');
        if (orb) orb.setActive(true);
        while (this.queue.length > 0) {
            if (this.stopped || myId !== this._loopId) break;
            const b64 = this.queue.shift();
            try {
                await this._playB64(b64);
            } catch (e) {
                console.warn('TTS segment error:', e);
            }
        }
        if (myId !== this._loopId) {
            this.playing = false;
            return;
        }
        this.playing = false;
        if (ttsBtn) ttsBtn.classList.remove('tts-speaking');
        if (orbContainer) orbContainer.classList.remove('speaking');
        if (orb) orb.setActive(false);
        if (typeof this.onPlaybackComplete === 'function') this.onPlaybackComplete();
    }
    _playB64(b64) {
        return new Promise(resolve => {
            this.audio.src = 'data:audio/mp3;base64,' + b64;
            const done = () => { resolve(); };
            this.audio.onended = done;
            this.audio.onerror = done;
            const p = this.audio.play();
            if (p) p.catch(done);
        });
    }
}

function init() {
    if (!chatMessages || !messageInput) {
        console.error('[JARVIS] Required DOM elements (chat-messages, message-input) not found.');
        return;
    }
    loadSettings();
    ttsPlayer = new TTSPlayer();
    ttsPlayer.onPlaybackComplete = maybeRestartListening;
    if (ttsBtn) ttsBtn.classList.add('tts-active');
    setGreeting();
    window.setInterval(setGreeting, 60_000);
    window.addEventListener('focus', setGreeting);
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) setGreeting();
    });
    initOrb();
    initSpeech();
    preloadStarterAudio();
    preStarterPlayer = new PreStarterPlayer();
    checkHealth();
    bindEvents();
    initHomeworkLayoutDivider();
    setMode(currentMode);
    loadModelCatalog();
    autoResizeInput();
    checkGoogleConnectionOnStartup().then(prompted => {
        if (!prompted) openGuide(0);
    });
}

async function googleConnectionInfo() {
    const response = await fetch(`${API}/plugins`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const plugins = (await response.json()).plugins || [];
    const googleIds = new Set(['gmail', 'google_drive', 'google_calendar', 'google_tasks']);
    const googlePlugins = plugins.filter(plugin => googleIds.has(plugin.id));
    return {
        configured: googlePlugins.some(plugin => plugin.connected || plugin.connect_url),
        connected: googlePlugins.some(plugin => plugin.connected),
        connectUrl: googlePlugins.find(plugin => plugin.connect_url)?.connect_url || '/oauth/google/start',
    };
}

function closeGoogleConnectPrompt(showGuide = false) {
    if (googleConnectPoll) { clearInterval(googleConnectPoll); googleConnectPoll = null; }
    googleConnectModal?.classList.remove('open');
    googleConnectModal?.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('guide-open');
    if (showGuide) openGuide(0);
}

async function checkGoogleConnected() {
    try {
        const info = await googleConnectionInfo();
        if (!info.connected) return false;
        closeGoogleConnectPrompt(false);
        showToast('Google connected — Gmail, Drive, Calendar, and Tasks are ready.');
        if (intelDashboard?.classList.contains('open')) await loadPlugins();
        return true;
    } catch (_) {
        return false;
    }
}

async function checkGoogleConnectionOnStartup() {
    if (!googleConnectModal) return false;
    try {
        const info = await googleConnectionInfo();
        if (!info.configured || info.connected) return false;
        closeGuide();
        googleConnectModal.dataset.connectUrl = info.connectUrl;
        googleConnectModal.classList.add('open');
        googleConnectModal.setAttribute('aria-hidden', 'false');
        document.body.classList.add('guide-open');
        setTimeout(() => googleConnectButton?.focus(), 0);
        return true;
    } catch (_) {
        return false;
    }
}

function beginGoogleConnection() {
    const connectUrl = googleConnectModal?.dataset.connectUrl || '/oauth/google/start';
    const popup = window.open(`${API}${connectUrl}`, 'edith-google-oauth', 'width=600,height=760');
    if (!popup) { showToast('Allow pop-ups, then select Continue with Google again.'); return; }
    googleConnectButton?.classList.add('google-connect-button-busy');
    if (googleConnectButton) googleConnectButton.textContent = 'Waiting for Google…';
    if (googleConnectPoll) clearInterval(googleConnectPoll);
    googleConnectPoll = setInterval(checkGoogleConnected, 1500);
}

async function preloadStarterAudio() {
    const base = (typeof window !== 'undefined' && window.location.origin) ? window.location.origin : '';
    for (const file of PRE_STARTER_FILES) {
        try {
            const index = file.replace('starter_', '');
            const r = await fetch(`${base}/tts/starter/${index}`, { cache: 'no-store' });
            if (!r.ok) continue;
            const blob = await r.blob();
            const base64 = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onloadend = () => resolve((reader.result || '').split(',')[1] || '');
                reader.onerror = reject;
                reader.readAsDataURL(blob);
            });
            if (base64) PRE_STARTER_CACHE[file] = base64;
        } catch (_) {}
    }
}

function loadSettings() {
    try {
        const s = localStorage.getItem(SETTINGS_KEY);
        if (s) {
            const parsed = JSON.parse(s);
            settings = { ...DEFAULT_SETTINGS, ...parsed };
        }
        if (toggleAutoActivity) toggleAutoActivity.checked = settings.autoOpenActivity;
        if (toggleAutoSearch) toggleAutoSearch.checked = settings.autoOpenSearchResults;
        if (toggleAutoApproveWork) toggleAutoApproveWork.checked = settings.autoApproveSafeWork;
        if (toggleThinkingSounds) toggleThinkingSounds.checked = settings.thinkingSounds;
        if (toggleVoiceInterrupt) toggleVoiceInterrupt.checked = settings.voiceInterrupt;
    } catch (_) {}
}

function saveSettings() {
    try {
        localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
    } catch (_) {}
}


function indiaHour(now = new Date()) {
    // IST is UTC+05:30 year-round. Deriving the hour numerically avoids
    // browser/locale edge cases where midnight can be formatted as 12 or 24.
    const timestamp = now instanceof Date ? now.getTime() : new Date(now).getTime();
    if (!Number.isFinite(timestamp)) return 0;
    return new Date(timestamp + (330 * 60 * 1000)).getUTCHours();
}

function indiaGreeting(now = new Date()) {
    const h = indiaHour(now);
    if (h >= 5 && h < 12) return 'Good morning.';
    if (h >= 12 && h < 17) return 'Good afternoon.';
    if (h >= 17 && h < 22) return 'Good evening.';
    return 'Burning the midnight oil?';
}

function setGreeting() {
    const title = document.getElementById('welcome-title');
    if (title) {
        const hour = indiaHour();
        title.textContent = indiaGreeting();
        title.dataset.indiaHour = String(hour);
        title.dataset.timeZone = 'Asia/Kolkata';
    }
}

function initOrb() {
    if (typeof OrbRenderer === 'undefined') return;
    try {
        orb = new OrbRenderer(orbContainer, {
            hue: 0,
            hoverIntensity: 0.3,
            backgroundColor: [0.02, 0.02, 0.06]
        });
    } catch (e) { console.warn('Orb init failed:', e); }
}

function isSafariOrIOS() {
    if (typeof navigator === 'undefined') return false;
    const ua = navigator.userAgent || '';
    return /iPad|iPhone|iPod/.test(ua) ||
        (navigator.vendor && navigator.vendor.indexOf('Apple') > -1) ||
        (/Safari/.test(ua) && !/Chrome|Chromium|CriOS/.test(ua));
}

function initSpeech() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { micBtn.title = 'Speech not supported in this browser'; return; }
    recognition = new SR();
    const safariMode = isSafariOrIOS();
    recognition.continuous = false;
    recognition.interimResults = !safariMode;
    recognition.maxAlternatives = 1;
    recognition.lang = 'en-US';
    recognition.onresult = e => {
        if (!isListening) return;
        if (!e.results || e.results.length === 0) return;
        const last = e.results[e.results.length - 1];
        const transcript = (last && last[0]) ? last[0].transcript.trim() : '';
        const isFinal = last && last.isFinal;
        if (speechWidgetText) speechWidgetText.textContent = transcript;
        if (speechWidget) speechWidget.classList.add('visible');
        if (settings.voiceInterrupt && ttsPlayer && ttsPlayer.playing && transcript.length > 0) {
            ttsPlayer.stop();
            ttsPlayer.stopped = false;
        }
        if (isFinal && transcript) {
            pendingSendTranscript = transcript;
            clearTimeout(speechSendTimeout);
            speechSendTimeout = setTimeout(() => {
                if (pendingSendTranscript) {
                    sendMessage(pendingSendTranscript);
                    pendingSendTranscript = null;
                }
                speechSendTimeout = null;
                stopListening();
            }, SPEECH_SEND_DELAY_MS);
        } else if (!isFinal) {
            pendingSendTranscript = null;
            clearTimeout(speechSendTimeout);
            speechSendTimeout = null;
        }
    };

    recognition.onstart = () => { speechErrorRetryCount = 0; };
    recognition.onerror = e => {
        stopListening();
        const msg = (e && e.error) ? String(e.error) : '';
        const isPermissionDenied = /denied|not-allowed|permission/i.test(msg);
        if (isPermissionDenied && micBtn) {
            micBtn.title = 'Microphone access denied. Allow in browser settings.';
            speechErrorRetryCount = SPEECH_ERROR_MAX_RETRIES;
        }
        if (autoListenMode && !isStreaming && speechErrorRetryCount < SPEECH_ERROR_MAX_RETRIES) {
            speechErrorRetryCount++;
            setTimeout(() => maybeRestartListening(), SPEECH_RESTART_DELAY_MS);
        } else if (speechErrorRetryCount >= SPEECH_ERROR_MAX_RETRIES && micBtn) {
            micBtn.title = 'Voice input — click to try again';
        }
    };

    recognition.onend = () => {
        if (pendingSendTranscript) {
            clearTimeout(speechSendTimeout);
            speechSendTimeout = null;
            sendMessage(pendingSendTranscript);
            pendingSendTranscript = null;
        } else {
            clearTimeout(speechSendTimeout);
            speechSendTimeout = null;
        }
        if (isListening) stopListening();
        maybeRestartListening();
    };
}

function startListening() {
    if (!recognition || isStreaming || isListening) return;
    if (isSafariOrIOS() && !safariVoiceHintShown) {
        showToast('Voice works best in Chrome. Safari has limited support.');
        safariVoiceHintShown = true;
    }
    isListening = true;
    pendingSendTranscript = null;
    clearTimeout(speechSendTimeout);
    speechSendTimeout = null;
    if (micBtn) micBtn.classList.add('listening');
    if (speechWidget) speechWidget.classList.add('visible');
    if (speechWidgetText) speechWidgetText.textContent = '';
    try {
        recognition.start();
    } catch (err) {
        isListening = false;
        if (micBtn) micBtn.classList.remove('listening');
        if (speechWidget) speechWidget.classList.remove('visible');
        if (isSafariOrIOS()) showToast('Tap the mic to continue voice input.');
    }
}

function stopListening() {
    clearTimeout(speechSendTimeout);
    speechSendTimeout = null;
    pendingSendTranscript = null;
    isListening = false;
    if (micBtn) micBtn.classList.remove('listening');
    if (speechWidget) speechWidget.classList.remove('visible');
    if (speechWidgetText) speechWidgetText.textContent = '';
    try { recognition.stop(); } catch (_) {}
}

function maybeRestartListening() {
    if (!autoListenMode || !recognition) return;
    if (isStreaming) return;

    const ttsActive = ttsPlayer && (ttsPlayer.playing || ttsPlayer.queue.length > 0);
    if (ttsActive && !settings.voiceInterrupt) return;

    const delay = ttsActive ? 150 : SPEECH_RESTART_DELAY_MS;
    setTimeout(() => {
        if (autoListenMode && !isStreaming && !isListening && recognition) {
            startListening();
        }
    }, delay);
}

const CAM_BYPASS_TOKEN = 'TTCAMTOKENTT';
const CAMERA_QUERY_PATTERNS = [
    /what\s+(can|do)\s+you\s+see/i,
    /can\s+you\s+see/i,
    /describe\s+(what\s+you\s+see|this|the\s+image)/i,
    /what('s|s)\sss+in\sss+(this\sss+)?(picture|image)/i,
    /what\s+do\s+i\s+look\s+like/i,
    /what\s+(am\s+i\s+)?holding/i,
    /show\s+me\s+what\s+you\s+see/i,
];
function isCameraQuery(text) {
    if (!text || typeof text !== 'string') return false;
    const t = text.trim().toLowerCase();
    return CAMERA_QUERY_PATTERNS.some(r => r.test(t)) ||
        (t.includes('see') && (t.includes('what') || t.includes('describe')));
}

function startCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        showToast('Camera not supported in this browser.');
        return Promise.reject(new Error('Camera not supported'));
    }
    if (camStream) return Promise.resolve();
    return navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false })
        .then(stream => {
            camStream = stream;
            if (camVideo) camVideo.srcObject = stream;
            if (camPanel) { camPanel.classList.add('visible'); camPanel.setAttribute('aria-hidden', 'false'); }
            if (camBtn) {
                camBtn.classList.add('cam-active');
                camBtn.title = 'Camera on — click to turn off';
                const icon = camBtn.querySelector('.cam-icon');
                const iconActive = camBtn.querySelector('.cam-icon-active');
                if (icon) icon.style.display = 'none';
                if (iconActive) iconActive.style.display = '';
            }
        })
        .catch(err => {
            showToast('Camera access denied. ' + (err.message || ''));
            throw err;
        });
}

function stopCamera() {
    if (camStream) {
        camStream.getTracks().forEach(t => t.stop());
        camStream = null;
    }
    if (camVideo) camVideo.srcObject = null;
    if (camPanel) { camPanel.classList.remove('visible'); camPanel.setAttribute('aria-hidden', 'true'); }
    if (camVisionModeInput) camVisionModeInput.checked = false;
    if (camBtn) {
        camBtn.classList.remove('cam-active');
        camBtn.title = 'Camera — capture and send for vision';
        const icon = camBtn.querySelector('.cam-icon');
        const iconActive = camBtn.querySelector('.cam-icon-active');
        if (icon) icon.style.display = '';
        if (iconActive) iconActive.style.display = 'none';
    }
}

function initCameraPanel() {
    if (!camPanel) return;
    let dragStart = { x: 0, y: 0, left: 0, top: 0 };
    let resizeStart = { x: 0, y: 0, w: 0, h: 0 };
    if (camClose) camClose.addEventListener('click', () => stopCamera());
    if (camMinimize) camMinimize.addEventListener('click', () => {
        camPanel.classList.toggle('minimized');
    });
    if (camPanelHeader) {
        camPanelHeader.addEventListener('mousedown', (e) => {
            if (e.target.closest('.cam-panel-btn, .cam-panel-vision-mode')) return;
            e.preventDefault();
            const r = camPanel.getBoundingClientRect();
            dragStart = { x: e.clientX, y: e.clientY, left: r.left, top: r.top };
            const onMove = (ev) => {
                const dx = ev.clientX - dragStart.x;
                const dy = ev.clientY - dragStart.y;
                camPanel.style.left = (dragStart.left + dx) + 'px';
                camPanel.style.top = (dragStart.top + dy) + 'px';
                camPanel.style.right = 'auto';
                camPanel.style.bottom = 'auto';
            };
            const onUp = () => { document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });
    }
    if (camPanelResize) {
        camPanelResize.addEventListener('mousedown', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const r = camPanel.getBoundingClientRect();
            resizeStart = { x: e.clientX, y: e.clientY, w: r.width, h: r.height };
            const onMove = (ev) => {
                const dw = ev.clientX - resizeStart.x;
                const dh = ev.clientY - resizeStart.y;
                const nw = Math.max(200, Math.min(window.innerWidth, resizeStart.w + dw));
                const nh = Math.max(150, Math.min(window.innerHeight * 0.7, resizeStart.h + dh));
                camPanel.style.width = nw + 'px';
                camPanel.style.height = nh + 'px';
            };
            const onUp = () => { document.removeEventListener('mousemove', onMove); document.removeEventListener('mouseup', onUp); };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });
    }
    camPanel.addEventListener('dblclick', (e) => {
        if (e.target.closest('.cam-panel-header') && !e.target.closest('.cam-panel-btn, .cam-panel-vision-mode')) {
            camPanel.classList.toggle('minimized');
        }
    });
    camPanel.querySelector('.cam-panel-body')?.addEventListener('click', (e) => {
        if (camPanel.classList.contains('minimized')) camPanel.classList.remove('minimized');
    });
}

function handleActions(actions, contentEl) {
    if (!actions) return;
    if (!contentEl) return;
    const externalUrls = [
        ...(actions.wopens || []),
        ...(actions.plays || []),
        ...(actions.googlesearches || []),
        ...(actions.youtubesearches || []),
    ].filter((url, index, all) => safeUrlForHref(url) && all.indexOf(url) === index);
    const safeOpen = url => {
        const destination = safeUrlForHref(url);
        if (destination) {
            try {
                if (pendingExternalWindow && sameExternalDestination(pendingExternalUrl, destination)) {
                    pendingExternalWindow = null;
                    pendingExternalUrl = '';
                    return true;
                }
                if (pendingExternalWindow && !pendingExternalWindow.closed) {
                    pendingExternalWindow.location.replace(destination);
                    pendingExternalWindow = null;
                    pendingExternalUrl = '';
                    return true;
                }
                const opened = window.open(destination, 'edith-external');
                if (opened) {
                    try { opened.opener = null; } catch (_) {}
                    return true;
                }
                return false;
            } catch (_) {
                return false;
            }
        }
        return false;
    };
    const browserTasks = (actions.browser_tasks || []).filter(task => task && safeUrlForHref(task.url));
    if (browserTasks.length) {
        const taskWrap = document.createElement('div');
        taskWrap.className = 'browser-task-list';
        browserTasks.forEach(task => {
            const card = document.createElement('div');
            card.className = 'browser-task-card';
            const heading = document.createElement('div');
            heading.className = 'browser-task-heading';
            heading.textContent = `Browser Operator · ${String(task.action_type || 'navigate').toUpperCase()}`;
            const objective = document.createElement('strong');
            objective.textContent = task.objective || 'Continue in browser';
            const destination = document.createElement('span');
            destination.textContent = friendlyUrlLabel(task.url) || task.url;
            const files = document.createElement('small');
            files.textContent = (task.files || []).length
                ? `Attachments ready: ${(task.files || []).map(file => file.name).join(', ')}`
                : 'No attachments';
            const open = document.createElement('a');
            open.className = 'browser-task-open';
            open.href = safeUrlForHref(task.url);
            open.target = 'edith-external';
            open.textContent = task.requires_login_handoff ? 'Open and sign in' : 'Open browser task';
            card.append(heading, objective, destination, files, open);
            taskWrap.appendChild(card);
            if (task.open_immediately) {
                window.setTimeout(() => {
                    if (!safeOpen(task.url)) showToast(`Select “${open.textContent}” to continue.`);
                }, 0);
            }
        });
        contentEl.appendChild(taskWrap);
    }
    const browserJobs = (actions.browser_jobs || []).filter(job => job && job.id);
    if (browserJobs.length) {
        const jobWrap = document.createElement('div');
        jobWrap.className = 'browser-task-list';
        browserJobs.forEach(job => {
            const card = document.createElement('div');
            card.className = 'browser-task-card universal-browser-job';
            card.dataset.jobId = job.id;
            const heading = document.createElement('div');
            heading.className = 'browser-task-heading';
            heading.textContent = 'E.D.I.T.H. BROWSER';
            const objective = document.createElement('strong');
            objective.textContent = job.objective || 'Browser workflow';
            const status = document.createElement('span');
            status.className = 'universal-browser-status';
            status.textContent = job.message || job.status || 'Starting...';
            const destination = document.createElement('small');
            destination.textContent = friendlyUrlLabel(job.url) || job.url || '';
            const handoff = document.createElement('div');
            handoff.className = 'universal-browser-handoff';
            const handoffMark = document.createElement('span');
            handoffMark.className = 'universal-browser-handoff-mark';
            handoffMark.textContent = '↗';
            const handoffCopy = document.createElement('span');
            handoffCopy.textContent = 'A real browser window is open on the right side of your screen. Sign in or interact there normally; E.D.I.T.H. shares control and continues automatically.';
            handoff.append(handoffMark, handoffCopy);
            const controls = document.createElement('div');
            controls.className = 'universal-browser-controls';
            const cancel = document.createElement('button');
            cancel.type = 'button';
            cancel.className = 'browser-task-open universal-browser-cancel';
            cancel.textContent = 'Cancel';
            cancel.addEventListener('click', async () => {
                await fetch(`${API}/browser/jobs/${encodeURIComponent(job.id)}/cancel`, { method: 'POST' });
                cancel.disabled = true;
            });
            controls.append(cancel);
            card.append(heading, objective, status, destination, handoff, controls);
            jobWrap.appendChild(card);
            pollUniversalBrowserJob(job.id, card);
        });
        contentEl.appendChild(jobWrap);
    }
    if (externalUrls.length > 0 && !safeOpen(externalUrls[0])) {
        showToast(`Select “Open ${friendlyUrlLabel(externalUrls[0])}” below to continue.`);
    }
    const visibleLinks = [
        ...(actions.links || []),
        ...externalUrls.map(url => ({
            title: `Open ${friendlyUrlLabel(url) || 'destination'}`,
            url,
            context: 'Direct link · opens here if new tabs are blocked',
            sameTabFallback: true,
        })),
    ].filter((link, index, all) => link && link.url && all.findIndex(item => item && item.url === link.url) === index);
    if (visibleLinks.length > 0) {
        const linksWrap = document.createElement('div');
        linksWrap.className = 'msg-action-links';
        visibleLinks.forEach(link => {
            const safeHref = safeUrlForHref(link && link.url);
            if (!safeHref) return;
            const anchor = document.createElement('a');
            anchor.className = 'msg-action-link';
            anchor.href = safeHref;
            anchor.target = link.sameTabFallback ? '_self' : '_blank';
            if (!link.sameTabFallback) anchor.rel = 'noopener';
            const copy = document.createElement('span');
            copy.className = 'msg-action-link-copy';
            const title = document.createElement('span');
            title.className = 'msg-action-link-title';
            title.textContent = (link.title || friendlyUrlLabel(link.url) || 'Open link').trim();
            copy.appendChild(title);
            if (link.context) {
                const context = document.createElement('span');
                context.className = 'msg-action-link-context';
                context.textContent = String(link.context).trim();
                copy.appendChild(context);
            }
            anchor.appendChild(copy);
            linksWrap.appendChild(anchor);
        });
        if (linksWrap.childElementCount) contentEl.appendChild(linksWrap);
    }
    if (actions.images && actions.images.length > 0) {
        const wrap = document.createElement('div');
        wrap.className = 'msg-actions-images';
        actions.images.forEach(url => {
            const img = document.createElement('img');
            img.src = url;
            img.alt = 'Generated image';
            img.className = 'msg-action-image';
            img.loading = 'lazy';
            img.onerror = () => {
                img.style.display = 'none';
                const fallback = document.createElement('div');
                fallback.className = 'msg-action-image-fallback';
                fallback.textContent = 'Image failed to load.';
                wrap.appendChild(fallback);
            };
            wrap.appendChild(img);
        });
        contentEl.appendChild(wrap);
    }
    if (actions.contents && actions.contents.length > 0) {
        const wrap = document.createElement('div');
        wrap.className = 'msg-actions-contents';
        actions.contents.forEach(t => {
            const p = document.createElement('div');
            p.className = 'msg-action-content';
            p.textContent = t;
            wrap.appendChild(p);
        });
        contentEl.appendChild(wrap);
    }
    if (actions.cam) {
        if (actions.cam.action === 'open') {
            startCamera();
        } else if (actions.cam.action === 'close') {
            stopCamera();
        } else if (actions.cam.action === 'open_and_capture') {
            const resendMsg = actions.cam.resend_message || 'What do you see?';
            (async () => {
                try {
                    await startCamera();
                    await new Promise((resolve) => {
                        if (!camVideo) { resolve(); return; }
                        if (camVideo.readyState >= 2 && camVideo.videoWidth > 0) {
                            setTimeout(resolve, 500);
                            return;
                        }
                        const onReady = () => {
                            camVideo.removeEventListener('loadeddata', onReady);
                            clearTimeout(t);
                            setTimeout(resolve, 600);
                        };
                        const t = setTimeout(() => {
                            camVideo.removeEventListener('loadeddata', onReady);
                            resolve();
                        }, 4000);
                        camVideo.addEventListener('loadeddata', onReady);
                    });
                    const frame = await captureFrameAsBase64Safe();
                    if (frame) {
                        sendMessageWithImage(resendMsg, frame);
                    } else {
                        showToast('Could not capture camera frame. Please try again.');
                    }
                } catch (err) {
                    showToast('Camera access denied.');
                }
            })();
        }
    }
}

async function pollUniversalBrowserJob(jobId, card) {
    const statusEl = card.querySelector('.universal-browser-status');
    const cancelBtn = card.querySelector('.universal-browser-cancel');
    const terminal = new Set(['completed', 'failed', 'cancelled']);
    for (let attempt = 0; attempt < 600; attempt++) {
        try {
            const response = await fetch(`${API}/browser/jobs/${encodeURIComponent(jobId)}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const job = await response.json();
            card.dataset.status = job.status || '';
            if (statusEl) {
                statusEl.textContent = job.message || job.status || 'Working...';
                if (job.error) statusEl.textContent += ` · ${job.error}`;
                if (job.result?.evidence) statusEl.textContent += ` · ${job.result.evidence}`;
            }
            if (terminal.has(job.status)) {
                if (cancelBtn) cancelBtn.hidden = true;
                return;
            }
        } catch (error) {
            if (statusEl) statusEl.textContent = `Could not read browser status: ${error.message}`;
            return;
        }
        await new Promise(resolve => setTimeout(resolve, 1200));
    }
}

function handleBackgroundTasks(tasks, contentEl) {
    if (!tasks || !tasks.length || !contentEl) return;
    tasks.forEach(task => {
        const card = document.createElement('div');
        card.className = 'bg-task-card';
        card.dataset.taskId = task.task_id;
        const label = task.type === 'generate image' ? 'Image Generation' : task.type === 'content' ? 'Content Writing' : task.type;
        const promptText = task.label ? `"${task.label}"` : '';
        card.innerHTML =
            '<div class="bg-task-header">' +
                '<div class="bg-task-spinner"></div>' +
                '<span class="bg-task-label">' + label + '</span>' +
                '<span class="bg-task-status">Working...</span>' +
            '</div>' +
            (promptText ? '<div class="bg-task-prompt">' + promptText + '</div>' : '');
        contentEl.appendChild(card);
        scrollToBottom();
        pollBackgroundTask(task.task_id, card);
    });
}

function renderArtifacts(artifacts, contentEl) {
    if (!contentEl || !Array.isArray(artifacts) || !artifacts.length) return;
    let tray = contentEl.querySelector('.artifact-tray');
    if (!tray) {
        tray = document.createElement('div');
        tray.className = 'artifact-tray';
        contentEl.appendChild(tray);
    }
    artifacts.forEach(artifact => {
        const link = document.createElement('a');
        link.className = 'artifact-card';
        link.href = artifact.url
            ? `${API}${artifact.url}`
            : `${API}/artifacts/${encodeURIComponent(artifact.name)}`;
        link.target = '_blank';
        link.rel = 'noopener';
        link.innerHTML = `<span class="artifact-icon">↓</span><span><strong>${escapeHtml(artifact.name || 'Generated file')}</strong><small>${escapeHtml(artifact.mime_type || 'file')}</small></span>`;
        tray.appendChild(link);
    });
    scrollToBottom();
}

function thinkingIndicatorMarkup(label = 'E.D.I.T.H. is thinking') {
    return `
        <span class="edith-thinking" role="status" aria-live="polite">
            <span class="edith-thinking-ring" aria-hidden="true"></span>
            <span class="edith-thinking-label">${escapeHtml(label)}</span>
            <span class="edith-thinking-dots" aria-hidden="true"><i></i><i></i><i></i></span>
        </span>
        <div class="msg-stream-text stream-placeholder"></div>`;
}

function updateThinkingState(contentEl, activity) {
    const label = contentEl?.querySelector('.edith-thinking-label');
    if (!label || !activity) return;
    const states = {
        query_detected: 'E.D.I.T.H. is thinking',
        decision: 'Choosing the best route',
        routing: 'Choosing the best route',
        context_retrieved: 'Checking context',
        extracting_query: 'Preparing a live search',
        vision_analyzing: 'Analyzing your image',
        searching_web: 'Searching the live web',
        scrape_triggered: 'Reading the webpage',
        scrape_self_healing: 'Trying another live-data route',
        scan_started: 'Scanning your watchlists',
        mission_started: 'Starting the research mission',
        research_route: 'Choosing the research pipeline',
        snap_queued: 'Saving screenshots to the snap queue',
        screen_scan: 'Scanning screenshots with Gemini Vision',
        web_research: 'Researching the live web',
        sources_read: 'Reading and comparing sources',
        reasoning: 'Reasoning over the evidence',
        batch_solved: 'Checking the completed solutions',
        solution_repaired: 'Completing the worked solution',
        tasks_executing: 'Executing your command',
        streaming_started: 'Composing the response',
    };
    const nextState = states[activity.event];
    if (nextState) label.textContent = nextState;
}

function assistantInlineMarkdown(value) {
    return escapeHtml(String(value || ''))
        .replace(/`([^`\n]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
        .replace(/__([^_\n]+)__/g, '<strong>$1</strong>')
        .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
        .replace(/(^|[^_])_([^_\n]+)_/g, '$1<em>$2</em>');
}

function normalizeAssistantResponse(value, final = false) {
    let text = String(value || '').replace(/\r\n/g, '\n')
        .replace(/\?<think\b[^>]*>[\s\S]*?\?<\/think\s*>/gi, '');
    const openThink = text.search(/\?<think\b[^>]*>/i);
    if (openThink >= 0) text = text.slice(0, openThink);
    if (final) text = text.replace(/(?:\n\s*\|\s*|\s+)$/, '');
    return text.replace(/^\s+/, '');
}

function formatAssistantMarkdown(value, final = false) {
    const lines = normalizeAssistantResponse(value, final).split('\n');
    const blocks = [];
    let paragraph = [];
    let listType = '';
    let listItems = [];
    let codeLanguage = '';
    let codeLines = null;
    const flushParagraph = () => {
        if (!paragraph.length) return;
        blocks.push(`<p>${assistantInlineMarkdown(paragraph.join(' '))}</p>`);
        paragraph = [];
    };
    const flushList = () => {
        if (!listItems.length) return;
        blocks.push(`<${listType}>${listItems.map(item => `<li>${assistantInlineMarkdown(item)}</li>`).join('')}</${listType}>`);
        listItems = [];
        listType = '';
    };
    const flushCode = () => {
        if (codeLines === null) return;
        blocks.push(`<pre${codeLanguage ? ` data-language="${escapeAttr(codeLanguage)}"` : ''}><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`);
        codeLines = null;
        codeLanguage = '';
    };
    for (const raw of lines) {
        const line = raw.trim();
        const fence = line.match(/^```\s*([A-Za-z0-9_+.-]*)/);
        if (fence) {
            flushParagraph(); flushList();
            if (codeLines === null) { codeLines = []; codeLanguage = fence[1] || ''; }
            else flushCode();
            continue;
        }
        if (codeLines !== null) { codeLines.push(raw); continue; }
        if (!line) { flushParagraph(); flushList(); continue; }
        const heading = line.match(/^(#{1,4})\s+(.+)$/);
        if (heading) {
            flushParagraph(); flushList();
            const level = Math.min(4, heading[1].length + 1);
            blocks.push(`<h${level}>${assistantInlineMarkdown(heading[2])}</h${level}>`);
            continue;
        }
        if (/^---+$/.test(line)) { flushParagraph(); flushList(); blocks.push('<hr>'); continue; }
        const bullet = line.match(/^[-•]\s+(.+)$/);
        const numbered = line.match(/^\d+[.)]\s+(.+)$/);
        if (bullet || numbered) {
            flushParagraph();
            const nextType = bullet ? 'ul' : 'ol';
            if (listType && listType !== nextType) flushList();
            listType = nextType;
            listItems.push((bullet || numbered)[1]);
            continue;
        }
        flushList();
        paragraph.push(line);
    }
    flushParagraph(); flushList(); flushCode();
    return blocks.join('');
}

function revealStreamingText(contentEl, fullResponse, final = false) {
    if (!contentEl) return null;
    const normalized = normalizeAssistantResponse(fullResponse, final);
    if (!final && normalized.length < 36 && !/[.!?\n:]\s*$/.test(normalized)) return null;
    contentEl.querySelector('.edith-thinking')?.remove();
    let textSpan = contentEl.querySelector('.msg-stream-text');
    if (!textSpan) {
        textSpan = document.createElement('div');
        textSpan.className = 'msg-stream-text';
        contentEl.prepend(textSpan);
    }
    if (currentMode === 'research' && currentResearchBranch === 'homework') {
        textSpan.innerHTML = formatHomeworkText(fullResponse);
        if (homeworkResponseTarget === 'board') renderHomeworkBoard(contentEl, fullResponse);
    } else {
        textSpan.innerHTML = formatAssistantMarkdown(fullResponse, final);
    }
    textSpan.classList.remove('stream-placeholder');
    textSpan.classList.toggle('is-streaming', !final);
    let progress = contentEl.querySelector('.stream-progress');
    if (final) {
        progress?.remove();
    } else if (!progress) {
        progress = document.createElement('span');
        progress.className = 'stream-progress';
        progress.setAttribute('role', 'status');
        progress.setAttribute('aria-label', 'E.D.I.T.H. is continuing the response');
        progress.innerHTML = '<span class="stream-progress-ring" aria-hidden="true"></span><span>Generating</span>';
        textSpan.insertAdjacentElement('afterend', progress);
    }
    return textSpan;
}

function normalizeHomeworkMath(text) {
    let output = String(text || '')
        .replace(/\\\[|\\\]|\\\(|\\\)/g, '')
        .replace(/\$\$?/g, '')
        .replace(/\\operatorname\{([^{}]+)\}/g, '$1')
        .replace(/\\text\{([^{}]+)\}/g, '$1')
        .replace(/\\frac\{([^{}]+)\}\{([^{}]+)\}/g, '($1)/($2)')
        .replace(/\\bar\s*\{?X\}?/g, 'X̄')
        .replace(/\\mu\b/g, 'μ')
        .replace(/\\sigma\b/g, 'σ')
        .replace(/\\Phi\b/g, 'Φ')
        .replace(/\\phi\b/g, 'φ')
        .replace(/\\varphi\b/g, 'ϕ')
        .replace(/\\theta\b/g, 'θ')
        .replace(/\\alpha\b/g, 'α')
        .replace(/\\beta\b/g, 'β')
        .replace(/\\lambda\b/g, 'λ')
        .replace(/\\rho\b/g, 'ρ')
        .replace(/\\cup\b/g, '∪')
        .replace(/\\cap\b/g, '∩')
        .replace(/\\notin\b/g, '∉')
        .replace(/\\in\b/g, '∈')
        .replace(/\\neq\b/g, '≠')
        .replace(/\\sqrt\{([^{}]+)\}/g, '√($1)')
        .replace(/\\cdot|\\times/g, '×')
        .replace(/\\leq/g, '≤')
        .replace(/\\geq/g, '≥')
        .replace(/\\dots|\\ldots/g, '…')
        .replace(/\^2\b/g, '²')
        .replace(/_\{([^{}]+)\}/g, '$1');
    return output;
}

function homeworkInline(text) {
    return escapeHtml(String(text || ''))
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/\*([^*]+)\*/g, '<em>$1</em>');
}

function formatHomeworkText(text) {
    let safeText = String(text || '').replace(/\\?<think\b[^>]*>[\s\S]*?\\?<\/think\s*>/gi, '');
    const unclosedThink = safeText.search(/\\?<think\b[^>]*>/i);
    if (unclosedThink >= 0) safeText = safeText.slice(0, unclosedThink);
    safeText = safeText.replace(/^\s*(?:Here(?:'s| is) (?:a |the )?thinking process:|Analyze User Input:)[\s\S]*?(?=^##\s+Question\b)/gim, '');
    safeText = safeText
        // Convert only actual TeX delimiters. A blanket `\\[` replacement
        // also matched the second slash in aligned-row spacing such as
        // `\\\\[4pt]`, corrupting the entire equation into visible `4pt]` text.
        .replace(/(^|[^\\])\\\[/g, '$1$$$$')
        .replace(/(^|[^\\])\\\]/g, '$1$$$$')
        .replace(/(^|[^\\])\\\(/g, '$1$')
        .replace(/(^|[^\\])\\\)/g, '$1$');
    const lines = safeText.split(/\r?\n/);
    const blocks = [];
    let index = 0;
    while (index < lines.length) {
        const raw = lines[index];
        const line = raw.trim();
        if (!line) { index++; continue; }
        if (/^-{3,}$/.test(line)) {
            blocks.push('<hr>');
            index++;
            continue;
        }
        const boldQuestion = line.match(/^\*\*Question\s+([^*]+)\*\*$/i);
        if (boldQuestion) {
            blocks.push(`<h2>Question ${homeworkInline(boldQuestion[1].trim())}</h2>`);
            index++;
            continue;
        }
        if (line === '$$') {
            const equation = [];
            index++;
            while (index < lines.length && lines[index].trim() !== '$$') {
                equation.push(lines[index].trim());
                index++;
            }
            if (index < lines.length) index++;
            blocks.push(`<div class="homework-equation">$$${escapeHtml(equation.join('\n'))}$$</div>`);
            continue;
        }
        if (line.startsWith('|') && index + 1 < lines.length && /^\|?[\s:|-]+\|?$/.test(lines[index + 1].trim())) {
            const rows = [];
            while (index < lines.length && lines[index].trim().startsWith('|')) {
                rows.push(lines[index].trim().replace(/^\||\|$/g, '').split('|').map(cell => cell.trim()));
                index++;
            }
            if (rows.length >= 2) {
                const header = rows[0];
                const body = rows.slice(2);
                blocks.push(`<table><thead><tr>${header.map(cell => `<th>${homeworkInline(cell)}</th>`).join('')}</tr></thead><tbody>${body.map(row => `<tr>${row.map(cell => `<td>${homeworkInline(cell)}</td>`).join('')}</tr>`).join('')}</tbody></table>`);
            }
            continue;
        }
        const heading = line.match(/^(#{2,3})\s+(.+)$/);
        if (heading) {
            const tag = heading[1].length === 2 ? 'h2' : 'h3';
            blocks.push(`<${tag}>${homeworkInline(heading[2])}</${tag}>`);
            index++;
            continue;
        }
        if (/^[-*]\s+/.test(line)) {
            const items = [];
            while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) {
                items.push(lines[index].trim().replace(/^[-*]\s+/, ''));
                index++;
            }
            blocks.push(`<ul>${items.map(item => `<li>${homeworkInline(item)}</li>`).join('')}</ul>`);
            continue;
        }
        if (/^\d+[.)]\s+/.test(line)) {
            const items = [];
            while (index < lines.length) {
                const numbered = lines[index].trim().match(/^\d+[.)]\s+(.+)$/);
                if (!numbered) break;
                const itemLines = [numbered[1]];
                index++;
                while (index < lines.length) {
                    const continuation = lines[index].trim();
                    if (/^\d+[.)]\s+/.test(continuation) || /^(?:#{2,3}\s+|\*\*Question\s+|\*\*Answer:\*\*|-{3,}$)/i.test(continuation)) break;
                    if (continuation) itemLines.push(continuation);
                    index++;
                }
                items.push(itemLines.join('\n'));
            }
            blocks.push(`<ol>${items.map(item => `<li>${homeworkInline(item)}</li>`).join('')}</ol>`);
            continue;
        }
        const answer = line.match(/^\*\*Answer:\*\*\s*(.*)$/i);
        if (answer) {
            const answerLines = [answer[1]];
            index++;
            while (index < lines.length && !/^(?:-{3,}|\*\*Question\s+)/i.test(lines[index].trim())) {
                if (lines[index].trim()) answerLines.push(lines[index].trim());
                index++;
            }
            blocks.push(`<div class="homework-answer"><strong>Answer</strong>${homeworkInline(answerLines.join('\n'))}</div>`);
            continue;
        }
        blocks.push(`<p>${homeworkInline(line)}</p>`);
        index++;
    }
    return blocks.join('');
}

function renderHomeworkBoard(contentEl, fullResponse) {
    if (!homeworkBoardContent) return;
    homeworkBoardContent.querySelector('.homework-board-empty')?.remove();
    let solutionId = contentEl?.dataset.homeworkSolutionId;
    let solution = solutionId ? document.getElementById(solutionId) : null;
    if (!solution) {
        solutionId = `homework-solution-${Date.now()}-${Math.random().toString(16).slice(2)}`;
        if (contentEl) contentEl.dataset.homeworkSolutionId = solutionId;
        solution = document.createElement('article');
        solution.id = solutionId;
        solution.className = 'homework-solution';
        homeworkBoardContent.appendChild(solution);
    }
    if (window.MathJax?.typesetClear) window.MathJax.typesetClear([solution]);
    solution.innerHTML = formatHomeworkText(fullResponse);
    const typeset = () => {
        if (window.MathJax?.typesetPromise) {
            window.MathJax.typesetPromise([solution]).catch(error => console.warn('[EDITH] Math rendering failed', error));
        }
    };
    if (window.MathJax?.startup?.promise) window.MathJax.startup.promise.then(typeset);
    else typeset();
    homeworkBoardContent.scrollTop = homeworkBoardContent.scrollHeight;
}

function resetHomeworkBoard() {
    if (!homeworkBoardContent) return;
    homeworkBoardContent.innerHTML = '<div class="homework-board-empty"><strong>Your worked solution will appear here.</strong><span>Upload clear screenshots, include every question edge, and press Send.</span></div>';
}

async function loadResearchFiles() {
    if (!researchFilesList) return;
    researchFilesList.innerHTML = '<div class="activity-empty">Loading files...</div>';
    try {
        const response = await fetch(`${API}/research-mode/files`, { cache: 'no-store' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const files = (await response.json()).files || [];
        if (!files.length) {
            researchFilesList.innerHTML = '<div class="activity-empty">No Research Mode files yet.</div>';
            return;
        }
        researchFilesList.innerHTML = files.map((file, index) => {
            const label = file.category === 'solution' ? 'Method sheet' : 'Temporary snap';
            const size = file.size < 1024 ? `${file.size} B` : `${(file.size / 1024).toFixed(1)} KB`;
            return `<button type="button" class="research-file-card" data-research-file-index="${index}"><span class="research-file-icon">${file.category === 'solution' ? 'M' : 'S'}</span><span class="research-file-copy"><strong>${escapeHtml(file.name)}</strong><small>${label} · ${size}</small></span><span class="research-file-download">Edit</span></button>`;
        }).join('');
        researchFilesList.querySelectorAll('[data-research-file-index]').forEach(button => {
            button.addEventListener('click', () => openResearchFileEditor(files[Number(button.dataset.researchFileIndex)]));
        });
    } catch (error) {
        researchFilesList.innerHTML = `<div class="activity-empty">Could not load files: ${escapeHtml(error.message || 'Unknown error')}</div>`;
    }
}

async function openResearchFileEditor(file) {
    if (!file || !researchFileEditor || !researchEditorContent) return;
    activeResearchFile = file;
    researchFileEditor.hidden = false;
    researchFilesList.hidden = true;
    researchFilesPanel?.classList.add('editing');
    if (researchEditorName) researchEditorName.textContent = file.name;
    if (researchEditorStatus) researchEditorStatus.textContent = 'Loading…';
    researchEditorContent.value = '';
    researchEditorContent.disabled = true;
    try {
        const response = await fetch(`${API}${file.url}/content`, { cache: 'no-store' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        researchEditorContent.value = (await response.json()).content || '';
        researchEditorContent.disabled = false;
        if (researchEditorStatus) researchEditorStatus.textContent = 'Edit anything you want, then save.';
        researchEditorContent.focus();
    } catch (error) {
        if (researchEditorStatus) researchEditorStatus.textContent = `Could not open file: ${error.message}`;
    }
}

function closeResearchFileEditor() {
    activeResearchFile = null;
    if (researchFileEditor) researchFileEditor.hidden = true;
    if (researchFilesList) researchFilesList.hidden = false;
    researchFilesPanel?.classList.remove('editing');
    if (researchEditorStatus) researchEditorStatus.textContent = '';
}

async function saveResearchFileEdits() {
    if (!activeResearchFile || !researchEditorContent || !researchEditorSave) return;
    researchEditorSave.disabled = true;
    if (researchEditorStatus) researchEditorStatus.textContent = 'Saving…';
    try {
        const response = await fetch(`${API}${activeResearchFile.url}/content`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: researchEditorContent.value }),
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        if (researchEditorStatus) researchEditorStatus.textContent = 'Saved.';
    } catch (error) {
        if (researchEditorStatus) researchEditorStatus.textContent = `Could not save: ${error.message}`;
    } finally {
        researchEditorSave.disabled = false;
    }
}

function downloadActiveResearchFile() {
    if (!activeResearchFile || !researchEditorContent) return;
    const blobUrl = URL.createObjectURL(new Blob([researchEditorContent.value], { type: 'text/markdown;charset=utf-8' }));
    const anchor = document.createElement('a');
    anchor.href = blobUrl;
    anchor.download = activeResearchFile.name || 'homework-methods.md';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
}

function openResearchFiles() {
    if (!researchFilesPanel) return;
    researchFilesPanel.classList.add('open');
    researchFilesPanel.setAttribute('aria-hidden', 'false');
    loadResearchFiles();
    updatePanelOverlay();
}

function closeResearchFiles() {
    if (!researchFilesPanel) return;
    researchFilesPanel.classList.remove('open');
    researchFilesPanel.setAttribute('aria-hidden', 'true');
    closeResearchFileEditor();
    updatePanelOverlay();
}

function setHomeworkLayout(boardPercent, persist = true) {
    if (!chatArea) return;
    if (window.matchMedia && window.matchMedia('(max-width: 680px)').matches) {
        chatArea.style.removeProperty('grid-template-columns');
        return;
    }
    const percent = Math.max(30, Math.min(85, Number(boardPercent) || 75));
    chatArea.style.gridTemplateColumns = `${percent}fr 9px ${100 - percent}fr`;
    if (homeworkLayoutDivider) {
        homeworkLayoutDivider.setAttribute('aria-valuemin', '30');
        homeworkLayoutDivider.setAttribute('aria-valuemax', '85');
        homeworkLayoutDivider.setAttribute('aria-valuenow', String(Math.round(percent)));
        homeworkLayoutDivider.title = percent > 55
            ? 'Drag to resize, or click to expand the assistant'
            : 'Drag to resize, or click to expand the solution board';
    }
    if (persist) localStorage.setItem('edith_homework_board_percent', String(percent));
}

function initHomeworkLayoutDivider() {
    if (!homeworkLayoutDivider || !chatArea) return;
    let moved = false;
    let startX = 0;
    homeworkLayoutDivider.addEventListener('pointerdown', event => {
        moved = false;
        startX = event.clientX;
        homeworkLayoutDivider.setPointerCapture(event.pointerId);
    });
    homeworkLayoutDivider.addEventListener('pointermove', event => {
        if (!homeworkLayoutDivider.hasPointerCapture(event.pointerId)) return;
        if (Math.abs(event.clientX - startX) > 3) moved = true;
        if (!moved) return;
        const bounds = chatArea.getBoundingClientRect();
        setHomeworkLayout(((event.clientX - bounds.left) / bounds.width) * 100);
    });
    homeworkLayoutDivider.addEventListener('click', () => {
        if (moved) { moved = false; return; }
        const current = Number(homeworkLayoutDivider.getAttribute('aria-valuenow') || 75);
        setHomeworkLayout(current > 55 ? 38 : 75);
    });
    homeworkLayoutDivider.addEventListener('keydown', event => {
        if (!['ArrowLeft', 'ArrowRight', 'Home'].includes(event.key)) return;
        event.preventDefault();
        const current = Number(homeworkLayoutDivider.getAttribute('aria-valuenow') || 75);
        setHomeworkLayout(event.key === 'Home' ? 75 : current + (event.key === 'ArrowRight' ? 5 : -5));
    });
}

function pollBackgroundTask(taskId, cardEl) {
    let pollCount = 0;
    const maxPolls = 120;
    const interval = setInterval(() => {
        pollCount++;
        if (pollCount > maxPolls) {
            clearInterval(interval);
            updateTaskCard(cardEl, 'failed', 'Timed out');
            return;
        }
        fetch(`${API}/tasks/${encodeURIComponent(taskId)}`)
            .then(r => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                return r.json();
            })
            .then(data => {
                if (data.status === 'completed') {
                    clearInterval(interval);
                    updateTaskCard(cardEl, 'completed', data);
                } else if (data.status === 'failed') {
                    clearInterval(interval);
                    updateTaskCard(cardEl, 'failed', data.error || 'Task failed');
                }
            })
            .catch(() => {  });
    }, 1500);
}

function updateTaskCard(cardEl, status, data) {
    if (!cardEl) return;
    const spinner = cardEl.querySelector('.bg-task-spinner');
    const statusEl = cardEl.querySelector('.bg-task-status');
    if (status === 'completed') {
        if (spinner) spinner.className = 'bg-task-done-icon';
        if (statusEl) statusEl.textContent = 'Ready!';
        cardEl.classList.add('bg-task-done');
        const viewBtn = document.createElement('button');
        viewBtn.className = 'bg-task-view-btn';
        viewBtn.textContent = 'Open in new tab';
        viewBtn.addEventListener('click', () => {
            const taskId = cardEl.dataset.taskId;
            window.open(`${window.location.origin}/app/viewer.html?task_id=${taskId}`, '_blank');
        });
        cardEl.appendChild(viewBtn);
        try {
            const taskId = cardEl.dataset.taskId;
            const w = window.open(`${window.location.origin}/app/viewer.html?task_id=${taskId}`, '_blank');
            if (!w) {
                showToast('Result ready! Click "Open in new tab" to view.');
            }
        } catch (_) {  }
    } else if (status === 'failed') {
        if (spinner) spinner.className = 'bg-task-fail-icon';
        if (statusEl) statusEl.textContent = typeof data === 'string' ? data : 'Failed';
        cardEl.classList.add('bg-task-failed');
    }
    scrollToBottom();
}

function captureFrameAsBase64() {
    if (!camVideo || !camStream || camVideo.readyState < 2) return null;
    if (!camCanvas) return null;
    const w = camVideo.videoWidth;
    const h = camVideo.videoHeight;
    if (!w || !h || w < 64 || h < 64) return null;
    camCanvas.width = w;
    camCanvas.height = h;
    const ctx = camCanvas.getContext('2d');
    if (!ctx) return null;
    ctx.drawImage(camVideo, 0, 0, w, h);
    try {
        return camCanvas.toDataURL('image/jpeg', 0.85).split(',')[1];
    } catch (_) {
        return null;
    }
}

async function captureFrameAsBase64Safe() {
    if (!camVideo || !camStream || !camCanvas) return null;
    return new Promise((resolve) => {
        const doCapture = () => {
            const w = camVideo.videoWidth;
            const h = camVideo.videoHeight;
            if (!w || !h || w < 64 || h < 64) {
                resolve(null);
                return;
            }
            camCanvas.width = w;
            camCanvas.height = h;
            const ctx = camCanvas.getContext('2d');
            if (!ctx) { resolve(null); return; }
            ctx.drawImage(camVideo, 0, 0, w, h);
            try {
                const b64 = camCanvas.toDataURL('image/jpeg', 0.9).split(',')[1];
                resolve(b64);
            } catch (_) {
                resolve(null);
            }
        };
        if (camVideo.readyState < 2) {
            const onReady = () => { camVideo.removeEventListener('loadeddata', onReady); doCapture(); };
            camVideo.addEventListener('loadeddata', onReady);
            setTimeout(() => { camVideo.removeEventListener('loadeddata', onReady); doCapture(); }, 3000);
            return;
        }
        const w = camVideo.videoWidth;
        const h = camVideo.videoHeight;
        if (w && h && w >= 64 && h >= 64) {
            if (typeof camVideo.requestVideoFrameCallback === 'function') {
                camVideo.requestVideoFrameCallback(() => { doCapture(); });
            } else {
                setTimeout(doCapture, 150);
            }
        } else {
            setTimeout(() => {
                const w2 = camVideo.videoWidth || 0;
                const h2 = camVideo.videoHeight || 0;
                if (w2 && h2 && w2 >= 64 && h2 >= 64) doCapture();
                else resolve(null);
            }, 300);
        }
    });
}

function clearPendingUpload() {
    pendingUploadBase64 = null;
    pendingUploadName = '';
    pendingUploadImages = [];
    pendingTextUploads = [];
    pendingUploadPreview = '';
    if (imageUploadInput) imageUploadInput.value = '';
    if (imageUploadPreview) imageUploadPreview.hidden = true;
    if (imageUploadThumb) imageUploadThumb.removeAttribute('src');
    if (imageUploadName) imageUploadName.textContent = '';
}

function textFileToContent(file) {
    return new Promise((resolve, reject) => {
        if (!file || file.size > 2 * 1024 * 1024) {
            reject(new Error(`${file?.name || 'That text file'} must be smaller than 2 MB.`));
            return;
        }
        const reader = new FileReader();
        reader.onerror = () => reject(new Error(`Could not read ${file.name || 'that text file'}.`));
        reader.onload = () => resolve({ text: { name: file.name || 'Uploaded text', content: String(reader.result || '') } });
        reader.readAsText(file);
    });
}

function documentFileToContent(file) {
    return new Promise((resolve, reject) => {
        if (!file || file.size > 15 * 1024 * 1024) {
            reject(new Error(`${file?.name || 'That document'} must be smaller than 15 MB.`));
            return;
        }
        const reader = new FileReader();
        reader.onerror = () => reject(new Error(`Could not read ${file.name || 'that document'}.`));
        reader.onload = () => resolve({
            text: { name: file.name || 'Uploaded document', content: String(reader.result || '') }
        });
        reader.readAsDataURL(file);
    });
}

function imageFileToJpeg(file) {
    return new Promise((resolve, reject) => {
        if (!file || !file.type.startsWith('image/')) {
            reject(new Error('Please choose an image file.'));
            return;
        }
        if (file.size > 15 * 1024 * 1024) {
            reject(new Error('Please choose an image smaller than 15 MB.'));
            return;
        }
        const reader = new FileReader();
        reader.onerror = () => reject(new Error('Could not read that image.'));
        reader.onload = () => {
            const image = new Image();
            image.onerror = () => reject(new Error('That image format could not be opened.'));
            image.onload = () => {
                const maxEdge = 1600;
                const scale = Math.min(1, maxEdge / Math.max(image.naturalWidth, image.naturalHeight));
                const width = Math.max(1, Math.round(image.naturalWidth * scale));
                const height = Math.max(1, Math.round(image.naturalHeight * scale));
                const canvas = document.createElement('canvas');
                canvas.width = width;
                canvas.height = height;
                const ctx = canvas.getContext('2d');
                if (!ctx) { reject(new Error('Image processing is unavailable.')); return; }
                ctx.drawImage(image, 0, 0, width, height);
                const dataUrl = canvas.toDataURL('image/jpeg', 0.86);
                resolve({ base64: dataUrl.split(',')[1], preview: dataUrl });
            };
            image.src = String(reader.result || '');
        };
        reader.readAsDataURL(file);
    });
}

function fileToDataUrl(file) {
    return new Promise((resolve, reject) => {
        const isImage = !!file && file.type.startsWith('image/');
        const isVideo = !!file && file.type.startsWith('video/');
        if (!isImage && !isVideo) {
            reject(new Error('Please choose a PNG, JPEG, WebP, GIF, MP4, MOV, or WebM file.'));
            return;
        }
        const maxBytes = isVideo ? 40 * 1024 * 1024 : 15 * 1024 * 1024;
        if (file.size > maxBytes) {
            reject(new Error(`${file.name || 'That file'} is larger than ${isVideo ? 40 : 15} MB.`));
            return;
        }
        const read = (duration = null) => {
            const reader = new FileReader();
            reader.onerror = () => reject(new Error(`Could not read ${file.name || 'that attachment'}.`));
            reader.onload = () => {
                let dataUrl = String(reader.result || '');
                if (isVideo && duration !== null) {
                    dataUrl = dataUrl.replace(';base64,', `;duration=${duration.toFixed(3)};base64,`);
                }
                resolve({ base64: dataUrl, preview: isImage ? dataUrl : '', isVideo });
            };
            reader.readAsDataURL(file);
        };
        if (!isVideo) { read(); return; }
        const video = document.createElement('video');
        const objectUrl = URL.createObjectURL(file);
        video.preload = 'metadata';
        video.onerror = () => { URL.revokeObjectURL(objectUrl); reject(new Error(`Could not read the duration of ${file.name || 'that video'}.`)); };
        video.onloadedmetadata = () => {
            const duration = Number(video.duration || 0);
            URL.revokeObjectURL(objectUrl);
            if (!duration || duration > 60) {
                reject(new Error(`${file.name || 'That video'} must be 60 seconds or shorter.`));
                return;
            }
            read(duration);
        };
        video.src = objectUrl;
    });
}

async function selectImageUpload(file) {
    return selectImageUploads([file]);
}

async function selectImageUploads(files) {
    try {
        const limit = currentMode === 'research' ? 8 : (currentMode === 'work' ? 5 : 1);
        const selected = Array.from(files || []).slice(0, limit);
        if (!selected.length) return;
        if (currentMode !== 'work' && selected.some(file => file.type.startsWith('video/'))) {
            throw new Error('Short-video posting is available in Work Mode.');
        }
        const isTextFile = file => file && (file.type.startsWith('text/') || file.type === 'application/json' || /\.(?:txt|md|csv|json)$/i.test(file.name || ''));
        const isDocumentFile = file => file && (
            file.type === 'application/pdf' ||
            file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
            /\.(?:pdf|docx)$/i.test(file.name || '')
        );
        if (currentMode !== 'research' && selected.some(file => isTextFile(file) || isDocumentFile(file))) {
            throw new Error('Document-source uploads are available in Research and Homework.');
        }
        const converted = currentMode === 'work'
            ? await Promise.all(selected.map(file => fileToDataUrl(file)))
            : await Promise.all(selected.map(file => isTextFile(file)
                ? textFileToContent(file)
                : isDocumentFile(file)
                    ? documentFileToContent(file)
                    : imageFileToJpeg(file)));
        pendingUploadImages = converted.filter(item => item.base64).map(item => item.base64);
        pendingTextUploads = converted.filter(item => item.text).map(item => item.text);
        pendingUploadBase64 = pendingUploadImages[0] || null;
        pendingUploadPreview = converted.find(item => item.preview)?.preview || '';
        pendingUploadName = selected.length > 1
            ? `${selected.length} attachments queued`
            : (selected[0].name || 'Uploaded attachment');
        if (imageUploadThumb) {
            if (pendingUploadPreview) imageUploadThumb.src = pendingUploadPreview;
            else imageUploadThumb.removeAttribute('src');
        }
        if (imageUploadName) imageUploadName.textContent = pendingUploadName;
        if (imageUploadPreview) imageUploadPreview.hidden = false;
        if (files.length > limit) showToast(`${currentMode === 'work' ? 'Work' : 'Research'} Mode accepts up to ${limit} attachments at once.`);
        if (messageInput) messageInput.focus();
    } catch (error) {
        clearPendingUpload();
        showToast(error.message || 'Could not attach that file.');
    }
}

function isBareYouTubeUrl(value) {
    return /^https?:\/\/(?:www\.|m\.)?(?:youtube\.com\/(?:watch\?[^\s]+|shorts\/[A-Za-z0-9_-]+)|youtu\.be\/[A-Za-z0-9_-]+)\/?$/i.test(String(value || '').trim());
}

async function loadResearchSources() {
    if (!researchSourcesList) return;
    if (!sessionId) {
        researchSourcesList.innerHTML = '<span class="research-sources-empty">Sources you upload in this session appear here.</span>';
        if (researchSourceCount) researchSourceCount.textContent = '0';
        if (researchSourceTokenTotal) researchSourceTokenTotal.textContent = '0 tokens enabled';
        return;
    }
    try {
        const response = await fetch(`${API}/research-mode/sessions/${encodeURIComponent(sessionId)}/sources`, { cache: 'no-store' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = await response.json();
        const sources = payload.sources || [];
        researchSourcesList.replaceChildren();
        if (!sources.length) {
            researchSourcesList.innerHTML = '<span class="research-sources-empty">No sources saved in this session yet.</span>';
        }
        for (const source of sources) {
            const row = document.createElement('div');
            row.className = 'research-source-row';
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.checked = source.enabled !== false;
            checkbox.title = checkbox.checked ? 'Included in retrieval' : 'Excluded from retrieval';
            const details = document.createElement('div');
            const name = document.createElement('strong');
            name.textContent = source.name || 'Source';
            const meta = document.createElement('span');
            meta.textContent = `${Number(source.token_count || 0).toLocaleString()} tokens · ${source.chunk_count || 0} chunks`;
            details.append(name, meta);
            const remove = document.createElement('button');
            remove.type = 'button';
            remove.className = 'research-source-remove';
            remove.textContent = '×';
            remove.title = 'Delete this source';
            checkbox.addEventListener('change', async () => {
                checkbox.disabled = true;
                try {
                    const result = await fetch(`${API}/research-mode/sessions/${encodeURIComponent(sessionId)}/sources/${encodeURIComponent(source.source_id)}`, {
                        method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: checkbox.checked })
                    });
                    if (!result.ok) throw new Error(`HTTP ${result.status}`);
                    await loadResearchSources();
                } catch (_) {
                    checkbox.checked = !checkbox.checked;
                    showToast('Could not update that source.');
                } finally { checkbox.disabled = false; }
            });
            remove.addEventListener('click', async () => {
                remove.disabled = true;
                try {
                    const result = await fetch(`${API}/research-mode/sessions/${encodeURIComponent(sessionId)}/sources/${encodeURIComponent(source.source_id)}`, { method: 'DELETE' });
                    if (!result.ok) throw new Error(`HTTP ${result.status}`);
                    await loadResearchSources();
                } catch (_) {
                    remove.disabled = false;
                    showToast('Could not delete that source.');
                }
            });
            row.append(checkbox, details, remove);
            researchSourcesList.appendChild(row);
        }
        if (researchSourceCount) researchSourceCount.textContent = String(sources.filter(item => item.enabled !== false).length);
        if (researchSourceTokenTotal) researchSourceTokenTotal.textContent = `${Number(payload.enabled_tokens || 0).toLocaleString()} tokens stored · retrieval stays budgeted`;
    } catch (_) {
        researchSourcesList.innerHTML = '<span class="research-sources-empty">Could not load session sources.</span>';
    }
}

function looksLikeResearchInstruction(value) {
    const text = String(value || '').trim();
    if (!text) return false;
    const opening = text.slice(0, 220);
    const closing = text.slice(-180);
    const command = /^(?:please\s+|can\s+you\s+|could\s+you\s+|i\s+(?:want|need)\s+you\s+to\s+)?(?:summarize|analyse|analyze|research|extract|compare|rewrite|explain|find|create|verify|review|translate|solve|check|list|identify|turn|convert|make|give|tell)\b/i;
    return command.test(opening) || /(?:please\s+)?(?:summarize|analyse|analyze|review|explain|research|extract|rewrite|translate)\s+(?:this|the above|the source)\s*[.!?]*$/i.test(closing);
}

function isInstructionlessResearchContent(value) {
    const text = String(value || '').trim();
    if (text.length < 280 || looksLikeResearchInstruction(text)) return false;
    const sentenceCount = (text.match(/[.!?](?:\s|$)/g) || []).length;
    const documentMarkers = /(?:^|\n)\s*(?:abstract|introduction|summary|background|methodology|findings|conclusion|references?)\b/i.test(text);
    return documentMarkers || text.includes('\n\n') || sentenceCount >= 4;
}

function showResearchUploadChooser(sourceUrl = '', pastedText = '') {
    if (activeUploadChooser?.isConnected) activeUploadChooser.remove();
    const card = document.createElement('section');
    card.className = 'research-upload-chooser';
    const heading = document.createElement('strong');
    heading.textContent = 'What should EDITH do with this source?';
    const hint = document.createElement('span');
    hint.textContent = 'Choose an action, or type your own instruction in the message box.';
    const actions = document.createElement('div');
    const options = currentResearchBranch === 'homework'
        ? [
            ['Solve questions', 'Solve every complete question in this source and show the full calculation on the solution board.'],
            ['Summarize', 'Summarize this source into clear study notes.'],
            ['Study guide', 'Create a structured study guide from this source.'],
            ['Key concepts', 'Extract and explain the key concepts from this source.'],
        ]
        : [
            ['Summarize', 'Summarize this source concisely.'],
            ['Key findings', 'Extract the key findings and important evidence from this source.'],
            ['Research deeper', 'Research this topic further and verify the source against current reliable sources.'],
            ['Questions', 'Suggest the most useful questions I can ask about this source.'],
        ];
    for (const [label, instruction] of options) {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = label;
        button.addEventListener('click', () => {
            card.remove();
            activeUploadChooser = null;
            if (pastedText) {
                pendingTextUploads = [{ name: 'Pasted research source.txt', content: pastedText }];
                pendingUploadName = 'Pasted research source queued';
            }
            if ((sourceUrl || pastedText) && messageInput) messageInput.value = '';
            sendMessage(sourceUrl ? `${instruction}\n\nSource: ${sourceUrl}` : instruction);
        });
        actions.appendChild(button);
    }
    card.append(heading, hint, actions);
    chatMessages.appendChild(card);
    activeUploadChooser = card;
    scrollToBottom();
}

async function loadModelSettings() {
    if (!modelRouterStatus) return;
    modelRouterStatus.textContent = 'Checking…';
    try {
        const response = await fetch(`${API}/settings/models`, { cache: 'no-store' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        if (modelProviderOrder) modelProviderOrder.value = (data.provider_order || []).join(',') || 'groq,gemini,openrouter';
        if (modelGroqKeys) modelGroqKeys.placeholder = data.groq_keys ? 'Groq key saved — leave blank to keep it' : 'Paste Groq API key';
        if (modelGeminiKey) modelGeminiKey.placeholder = data.gemini_configured ? 'Gemini key saved — leave blank to keep it' : 'Paste Gemini API key';
        if (modelOpenRouterKey) modelOpenRouterKey.placeholder = data.openrouter_configured ? 'OpenRouter key saved — leave blank to keep it' : 'Paste OpenRouter API key';
        if (modelGroqModel) modelGroqModel.value = data.groq_model || '';
        if (modelGeminiModel) modelGeminiModel.value = data.gemini_model || '';
        if (modelOpenRouterModel) modelOpenRouterModel.value = data.openrouter_model || 'openrouter/free';
        const active = data.last_provider ? `Last used: ${data.last_provider}` : `${data.available ? 'Ready' : 'No provider configured'}`;
        modelRouterStatus.textContent = data.failovers ? `${active} · ${data.failovers} failover(s)` : active;
        const configuredProviders = {
            groq: Number(data.groq_keys || 0) > 0,
            gemini: !!data.gemini_configured,
            openrouter: !!data.openrouter_configured,
        };
        modelProviderStatuses?.querySelectorAll('[data-provider-status]').forEach(chip => {
            const provider = chip.dataset.providerStatus;
            const configured = configuredProviders[provider];
            chip.textContent = `${provider === 'openrouter' ? 'OpenRouter' : provider[0].toUpperCase() + provider.slice(1)} · ${configured ? 'saved globally' : 'not set'}`;
            chip.classList.toggle('configured', configured);
            chip.classList.toggle('missing', !configured);
        });
        await loadModelCatalog();
    } catch (_) {
        modelRouterStatus.textContent = 'Could not load';
    }
}

async function saveModelProviderSettings() {
    if (!modelSettingsSave) return;
    modelSettingsSave.disabled = true;
    modelSettingsSave.textContent = 'Saving…';
    try {
        const response = await fetch(`${API}/settings/models`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                provider_order: modelProviderOrder?.value || 'groq,gemini,openrouter',
                groq_api_keys: modelGroqKeys?.value || '',
                gemini_api_key: modelGeminiKey?.value || '',
                openrouter_api_key: modelOpenRouterKey?.value || '',
                groq_model: modelGroqModel?.value || '',
                gemini_model: modelGeminiModel?.value || '',
                openrouter_model: modelOpenRouterModel?.value || '',
            }),
        });
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.detail || `HTTP ${response.status}`);
        }
        if (modelGroqKeys) modelGroqKeys.value = '';
        if (modelGeminiKey) modelGeminiKey.value = '';
        if (modelOpenRouterKey) modelOpenRouterKey.value = '';
        showToast('Global AI settings saved for every mode.');
        await loadModelSettings();
    } catch (error) {
        showToast(error.message || 'Could not save AI settings.');
    } finally {
        modelSettingsSave.disabled = false;
        modelSettingsSave.textContent = 'Save global AI settings';
    }
}

async function testModelConnections() {
    if (!modelSettingsTest || !modelTestResults) return;
    modelSettingsTest.disabled = true;
    modelSettingsTest.textContent = 'Testing…';
    modelTestResults.hidden = false;
    modelTestResults.innerHTML = '<div><strong>Checking</strong><span>Testing the saved providers without exposing your keys…</span></div>';
    try {
        const response = await fetch(`${API}/settings/models/test`, { method: 'POST' });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
        modelTestResults.innerHTML = Object.entries(data.providers || {}).map(([provider, result]) =>
            `<div><strong>${escapeHtml(provider)}</strong><span>${escapeHtml(result.message || result.status || 'Unknown')}</span></div>`
        ).join('') || '<div><strong>Result</strong><span>No provider is configured yet.</span></div>';
        await loadModelSettings();
    } catch (error) {
        modelTestResults.innerHTML = `<div><strong>Test failed</strong><span>${escapeHtml(error.message || 'Could not test the saved providers.')}</span></div>`;
    } finally {
        modelSettingsTest.disabled = false;
        modelSettingsTest.textContent = 'Test saved connections';
    }
}

async function loadModelCatalog() {
    if (!chatModelSelector) return;
    const selected = localStorage.getItem('edith_model_preference') || chatModelSelector.value || 'auto';
    try {
        const response = await fetch(`${API}/settings/models/catalog`, { cache: 'no-store' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        chatModelSelector.innerHTML = '';
        const groups = new Map();
        for (const model of (data.models || [])) {
            const provider = model.provider || 'Models';
            if (!groups.has(provider)) {
                const group = document.createElement('optgroup');
                group.label = provider;
                groups.set(provider, group);
                chatModelSelector.appendChild(group);
            }
            const option = document.createElement('option');
            option.value = model.value;
            const speedSuffix = model.speed === 'fast' ? ' · Fast' : (model.speed === 'deep' ? ' · Deep' : '');
            option.textContent = model.value === 'auto' ? '✦ Auto · Fast' : `${model.name}${speedSuffix}`;
            option.disabled = model.value !== 'auto' && !model.configured;
            option.title = model.configured
                ? `${model.provider} · ${model.speed || 'standard'} response profile`
                : `${model.provider} · add its global API key in Settings`;
            groups.get(provider).appendChild(option);
        }
        const selectedOption = [...chatModelSelector.options].find(option => option.value === selected && !option.disabled);
        chatModelSelector.value = selectedOption ? selected : 'auto';
        if (!selectedOption && selected !== 'auto') localStorage.setItem('edith_model_preference', 'auto');
        chatModelSelector.title = chatModelSelector.selectedOptions[0]?.title || 'Automatically use the first available provider';
    } catch (_) {
        if (!chatModelSelector.options.length) chatModelSelector.innerHTML = '<option value="auto">✦ Auto</option>';
    }
}

async function sendMessageWithImage(text, imgBase64) {
    if (!text || !imgBase64 || isStreaming) return;
    const messageToSend = text + ' ' + CAM_BYPASS_TOKEN;
    addMessage('user', text, `data:image/jpeg;base64,${imgBase64}`);
    addTypingIndicator();
    userCancelledTurn = false;
    setStreamingControls(true);
    if (messageInput) messageInput.disabled = true;
    if (orbContainer) orbContainer.classList.add('active');
    if (ttsPlayer) { ttsPlayer.reset(); ttsPlayer.unlock(); }
    let timeoutId = null;
    const controller = new AbortController();
    activeTurnController = controller;
    try {
        timeoutId = setTimeout(() => controller.abort(), 300000);
        const res = await fetch(`${API}/chat/jarvis/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: messageToSend,
                session_id: sessionId,
                tts: !!(ttsPlayer && ttsPlayer.enabled),
                imgbase64: imgBase64,
                mode: currentMode,
                research_branch: currentResearchBranch,
                model_preference: chatModelSelector?.value || 'auto',
            }),
            signal: controller.signal,
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        removeTypingIndicator();
        const contentEl = addMessage('assistant', '');
        contentEl.innerHTML = thinkingIndicatorMarkup('Analyzing your image');
        scrollToBottom();
        if (!res.body) throw new Error('No response body');
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let sseBuffer = '';
        let fullResponse = '';
        let streamDone = false;
        while (!streamDone) {
            const { done, value } = await reader.read();
            if (done) break;
            sseBuffer += decoder.decode(value, { stream: true });
            const lines = sseBuffer.split('\n\n');
            sseBuffer = lines.pop();
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.session_id) sessionId = data.session_id;
                    if (data.activity) {
                        if (data.activity.route === 'trueforge' && data.activity.profile) activeHarnessProfile = data.activity.profile;
                        updateThinkingState(contentEl, data.activity);
                        appendActivity(data.activity);
                        if (activityToggle) activityToggle.style.display = '';
                        if (activityPanel && shouldAutoOpenActivity()) { activityPanel.classList.add('open'); updatePanelOverlay(); }
                    }
                    if (data.actions) handleActions(data.actions, contentEl);
                    if (data.background_tasks) handleBackgroundTasks(data.background_tasks, contentEl);
                    if ('chunk' in data) {
                        const chunkText = data.chunk || '';
                        fullResponse += chunkText;
                        revealStreamingText(contentEl, fullResponse);
                        scrollToBottom();
                    }
                    if (data.audio && ttsPlayer) {
                        if (preStarterPlayer) preStarterPlayer.stop();
                        ttsPlayer.enqueue(data.audio);
                    }
                    if (data.error) throw new Error(data.error);
                    if (data.done) { streamDone = true; break; }
                } catch (parseErr) {
                    if (parseErr.message && !parseErr.message.includes('JSON')) throw parseErr;
                }
            }
            if (streamDone) break;
        }
        if (fullResponse) revealStreamingText(contentEl, fullResponse, true);
        else revealStreamingText(contentEl, '(No response)', true);
    } catch (err) {
        clearTimeout(timeoutId);
        removeTypingIndicator();
        if (err.name === 'AbortError' && userCancelledTurn) {
            addMessage('assistant', 'Turn cancelled.');
        } else {
            addMessage('assistant', 'Something went wrong analyzing the image. Please try again.');
        }
    } finally {
        clearTimeout(timeoutId);
        finalizePendingAssistantIndicators();
        if (activeTurnController === controller) activeTurnController = null;
        isStreaming = false;
        if (sendBtn) sendBtn.disabled = false;
        if (messageInput) messageInput.disabled = false;
        if (orbContainer) orbContainer.classList.remove('active');
    }
}

async function checkHealth() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);
        const r = await fetch(`${API}/health`, { signal: controller.signal });
        clearTimeout(timeoutId);
        const d = await r.json().catch(() => null);
        const ok = d && (d.status === 'healthy' || d.status === 'degraded');
        if (statusDot) statusDot.classList.toggle('offline', !ok);
        if (statusText) statusText.textContent = ok ? 'Online' : 'Offline';
    } catch (e) {
        if (statusDot) statusDot.classList.add('offline');
        if (statusText) statusText.textContent = 'Offline';
        if (typeof console !== 'undefined' && console.warn) console.warn('[Health] Check failed:', e);
    }
}

function showToast(msg, durationMs = 5000) {
    if (!toastContainer || !msg) return;
    const el = document.createElement('div');
    el.className = 'toast';
    el.textContent = msg;
    toastContainer.appendChild(el);
    el.offsetHeight;
    el.classList.add('toast-visible');
    const t = setTimeout(() => {
        el.classList.remove('toast-visible');
        setTimeout(() => el.remove(), 300);
    }, durationMs);
    el.addEventListener('click', () => { clearTimeout(t); el.classList.remove('toast-visible'); setTimeout(() => el.remove(), 300); });
}

function updateGuidePage() {
    if (!guideModal) return;
    const pages = [...guideModal.querySelectorAll('.guide-page')];
    const dots = [...guideModal.querySelectorAll('.guide-dots span')];
    guidePageIndex = Math.max(0, Math.min(pages.length - 1, guidePageIndex));
    pages.forEach((page, index) => {
        const active = index === guidePageIndex;
        page.classList.toggle('active', active);
        page.setAttribute('aria-hidden', String(!active));
    });
    guideModal.setAttribute('aria-labelledby', guidePageIndex === 0 ? 'guide-title' : 'guide-title-controls');
    dots.forEach((dot, index) => dot.classList.toggle('active', index === guidePageIndex));
    if (guideStepLabel) guideStepLabel.textContent = `${guidePageIndex + 1} OF ${pages.length}`;
    if (guideBack) guideBack.hidden = guidePageIndex === 0;
    if (guideNext) {
        guideNext.innerHTML = guidePageIndex === pages.length - 1
            ? 'Start using E.D.I.T.H. <span>✓</span>'
            : 'Next: controls <span>→</span>';
    }
}

function openGuide(page = 0) {
    if (!guideModal) return;
    guidePageIndex = page;
    updateGuidePage();
    guideModal.classList.add('open');
    guideModal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('guide-open');
    setTimeout(() => guideClose?.focus(), 0);
}

function closeGuide() {
    if (!guideModal) return;
    guideModal.classList.remove('open');
    guideModal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('guide-open');
    messageInput?.focus();
}

function looksLikeExternalAction(text) {
    const msg = String(text || '').trim().toLowerCase();
    return /^(?:please\s+)?(?:open|launch|visit|go\s+to|play|post|publish|upload|submit)\b/.test(msg) ||
        /\b(?:post|publish|upload|submit|edit)\b.*\b(?:linkedin|website|site|portal)\b/.test(msg) ||
        /^(?:please\s+)?(?:search|find)\b.*\b(?:youtube|google)\b/.test(msg) ||
        /\b(?:search|find)\s+(?:on\s+)?(?:youtube|google)\b/.test(msg);
}

function sameExternalDestination(first, second) {
    try {
        const normalize = value => {
            const url = new URL(value);
            const host = url.hostname.replace(/^www\./i, '').toLowerCase();
            const path = url.pathname.replace(/\/$/, '') || '/';
            return `${host}${path}${url.search}`;
        };
        return normalize(first) === normalize(second);
    } catch (_) {
        return false;
    }
}

function inferDirectOpenUrl(text) {
    const match = String(text || '').trim().match(
        /^(?:please\s+)?(?:open|launch|visit|go\s+to)\s+(?:the\s+)?(?:website\s+)?([^\s,;]+)/i
    );
    if (!match) return '';
    let target = match[1].trim().replace(/[.!?,;:]+$/, '').toLowerCase();
    const knownSites = {
        youtube: 'https://www.youtube.com',
        google: 'https://www.google.com',
        nvidia: 'https://www.nvidia.com',
        amazon: 'https://www.amazon.com',
        github: 'https://github.com',
        netflix: 'https://www.netflix.com',
        spotify: 'https://open.spotify.com',
        whatsapp: 'https://web.whatsapp.com',
        linkedin: 'https://www.linkedin.com',
    };
    if (knownSites[target]) return knownSites[target];
    if (/^https?:\/\//i.test(target)) return safeUrlForHref(target);
    if (/^(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:\/[^\s]*)?$/i.test(target)) {
        return safeUrlForHref(`https://${target}`);
    }
    if (/^[a-z0-9-]+$/i.test(target)) return safeUrlForHref(`https://www.${target}.com`);
    return '';
}

function prepareExternalWindow(text) {
    if (!looksLikeExternalAction(text) || pendingExternalWindow) return;
    try {
        pendingExternalUrl = inferDirectOpenUrl(text);
        pendingExternalWindow = window.open(pendingExternalUrl || 'about:blank', 'edith-external');
        if (pendingExternalWindow) {
            try { pendingExternalWindow.opener = null; } catch (_) {}
            if (!pendingExternalUrl) {
                pendingExternalWindow.document.title = 'E.D.I.T.H. is opening your destination…';
                pendingExternalWindow.document.body.style.cssText = 'margin:0;background:#05020d;color:#fff;font:16px system-ui;display:grid;place-items:center;height:100vh';
                pendingExternalWindow.document.body.textContent = 'E.D.I.T.H. is opening your destination…';
            }
        } else if (pendingExternalUrl) {
            const sameTabDestination = pendingExternalUrl;
            pendingExternalUrl = '';
            window.location.assign(sameTabDestination);
        } else {
            pendingExternalUrl = '';
        }
    } catch (_) {
        pendingExternalWindow = null;
        pendingExternalUrl = '';
    }
}

function releaseUnusedExternalWindow() {
    if (!pendingExternalWindow) return;
    try {
        if (!pendingExternalWindow.closed) pendingExternalWindow.close();
    } catch (_) {}
    pendingExternalWindow = null;
    pendingExternalUrl = '';
}

function bindEvents() {
    if (sendBtn) sendBtn.addEventListener('click', () => { if (isStreaming) cancelActiveHarnessTurn(); else sendMessage(); });
    if (stopTaskButton) stopTaskButton.addEventListener('click', cancelActiveHarnessTurn);
    if (messageInput) messageInput.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (!isStreaming) sendMessage(); }
    });
    if (messageInput) messageInput.addEventListener('input', () => {
        autoResizeInput();
        const len = messageInput.value.length;
        if (charCount) charCount.textContent = len > 100 ? `${len.toLocaleString()} / 32,000` : '';
    });
    if (camBtn) camBtn.addEventListener('click', () => {
        if (camStream) stopCamera();
        else startCamera();
    });
    if (uploadBtn && imageUploadInput) {
        uploadBtn.addEventListener('click', () => imageUploadInput.click());
        imageUploadInput.addEventListener('change', () => {
            if (imageUploadInput.files?.length) selectImageUploads(imageUploadInput.files);
        });
    }
    if (imageUploadRemove) imageUploadRemove.addEventListener('click', clearPendingUpload);
    initCameraPanel();
    if (scrapeBtn) scrapeBtn.style.display = 'none';
    if (intelToggle) intelToggle.addEventListener('click', openPluginManager);
    if (intelDashboardClose) intelDashboardClose.addEventListener('click', closePluginManager);
    if (intelDashboard) intelDashboard.addEventListener('click', e => {
        if (e.target === intelDashboard) closePluginManager();
    });
    if (googleConnectButton) googleConnectButton.addEventListener('click', beginGoogleConnection);
    if (googleConnectLater) googleConnectLater.addEventListener('click', () => closeGoogleConnectPrompt(true));
    window.addEventListener('message', event => {
        if (event.origin === window.location.origin && event.data?.type === 'edith-google-connected') checkGoogleConnected();
    });
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && googleConnectModal?.classList.contains('open')) { closeGoogleConnectPrompt(true); return; }
        if (e.key === 'Escape' && guideModal?.classList.contains('open')) { closeGuide(); return; }
        if (e.key === 'ArrowRight' && guideModal?.classList.contains('open') && guidePageIndex === 0) { guidePageIndex = 1; updateGuidePage(); return; }
        if (e.key === 'ArrowLeft' && guideModal?.classList.contains('open') && guidePageIndex === 1) { guidePageIndex = 0; updateGuidePage(); return; }
        if (e.key === 'Escape' && intelDashboard?.classList.contains('open')) closePluginManager();
    });
    if (micBtn) micBtn.addEventListener('click', () => {
        if (isListening) {
            autoListenMode = false;
            stopListening();
            if (micBtn) micBtn.classList.remove('auto-listen');
        } else {
            autoListenMode = true;
            speechErrorRetryCount = 0;
            if (micBtn) {
                micBtn.classList.add('auto-listen');
                micBtn.title = 'Voice input — click to stop auto-listen';
            }
            startListening();
        }
    });
    if (ttsBtn) ttsBtn.addEventListener('click', () => {
        if (ttsPlayer) ttsPlayer.enabled = !ttsPlayer.enabled;
        ttsBtn.classList.toggle('tts-active', ttsPlayer && ttsPlayer.enabled);
        if (ttsPlayer && !ttsPlayer.enabled) ttsPlayer.stop();
    });
    if (newChatBtn) newChatBtn.addEventListener('click', newChat);
    if (btnJarvis) btnJarvis.addEventListener('click', () => setMode('edit'));
    if (btnScraper) btnScraper.addEventListener('click', () => setMode('work'));
    if (btnResearch) btnResearch.addEventListener('click', () => setMode('research'));
    if (researchFilesToggle) researchFilesToggle.addEventListener('click', openResearchFiles);
    if (homeworkBoardFiles) homeworkBoardFiles.addEventListener('click', openResearchFiles);
    if (researchFilesClose) researchFilesClose.addEventListener('click', closeResearchFiles);
    if (researchEditorBack) researchEditorBack.addEventListener('click', closeResearchFileEditor);
    if (researchEditorSave) researchEditorSave.addEventListener('click', saveResearchFileEdits);
    if (researchEditorDownload) researchEditorDownload.addEventListener('click', downloadActiveResearchFile);
    if (researchBranchSwitch) {
        researchBranchSwitch.querySelectorAll('[data-research-branch]').forEach(button => {
            button.addEventListener('click', () => {
                currentResearchBranch = button.dataset.researchBranch === 'homework' ? 'homework' : 'research';
                researchBranchSwitch.querySelectorAll('[data-research-branch]').forEach(candidate => {
                    candidate.classList.toggle('active', candidate === button);
                });
                setMode('research', false);
            });
        });
    }
    if (researchSourceToggle && researchSourceForm) {
        researchSourceToggle.addEventListener('click', () => {
            researchSourceForm.hidden = !researchSourceForm.hidden;
            if (!researchSourceForm.hidden) researchSourceUrl?.focus();
        });
    }
    if (researchSourcesToggle && researchSourcesPopover) {
        researchSourcesToggle.addEventListener('click', async () => {
            researchSourcesPopover.hidden = !researchSourcesPopover.hidden;
            if (!researchSourcesPopover.hidden) await loadResearchSources();
        });
    }
    if (researchSourceForm) {
        researchSourceForm.addEventListener('submit', event => {
            event.preventDefault();
            const url = String(researchSourceUrl?.value || '').trim();
            if (!isBareYouTubeUrl(url)) {
                showToast('Please paste a valid public YouTube video URL.');
                return;
            }
            if (researchSourceUrl) researchSourceUrl.value = '';
            researchSourceForm.hidden = true;
            showResearchUploadChooser(url);
        });
    }
    document.querySelectorAll('.chip').forEach(c => {
        c.addEventListener('click', () => { if (!isStreaming) sendMessage(c.dataset.msg); });
    });
    if (searchResultsToggle) {
        searchResultsToggle.addEventListener('click', () => {
            if (searchResultsWidget) { searchResultsWidget.classList.toggle('open'); updatePanelOverlay(); }
        });
    }
    if (searchResultsClose && searchResultsWidget) {
        searchResultsClose.addEventListener('click', () => { searchResultsWidget.classList.remove('open'); updatePanelOverlay(); });
    }
    if (activityToggle) {
        activityToggle.addEventListener('click', () => {
            if (activityPanel) {
                if (!activityPanel.classList.contains('open') && historyPanel) historyPanel.classList.remove('open');
                activityPanel.classList.toggle('open'); updatePanelOverlay();
            }
        });
    }
    if (activityClose && activityPanel) {
        activityClose.addEventListener('click', () => { activityPanel.classList.remove('open'); updatePanelOverlay(); });
    }
    if (historyToggle) {
        historyToggle.addEventListener('click', () => {
            if (!historyPanel) return;
            const opening = !historyPanel.classList.contains('open');
            if (opening) {
                if (activityPanel) activityPanel.classList.remove('open');
                loadHistoryList();
            }
            historyPanel.classList.toggle('open');
            updatePanelOverlay();
        });
    }
    if (historyClose && historyPanel) {
        historyClose.addEventListener('click', () => { historyPanel.classList.remove('open'); updatePanelOverlay(); });
    }
    if (settingsBtn && settingsPanel) {
        settingsBtn.addEventListener('click', () => {
            settingsPanel.classList.toggle('open');
            updatePanelOverlay();
            if (settingsPanel.classList.contains('open')) loadModelSettings();
        });
    }
    if (settingsClose && settingsPanel) {
        settingsClose.addEventListener('click', () => {
            settingsPanel.classList.remove('open');
            updatePanelOverlay();
        });
    }
    if (modelSettingsSave) modelSettingsSave.addEventListener('click', saveModelProviderSettings);
    if (modelSettingsTest) modelSettingsTest.addEventListener('click', testModelConnections);
    if (chatModelSelector) chatModelSelector.addEventListener('change', () => {
        localStorage.setItem('edith_model_preference', chatModelSelector.value || 'auto');
        chatModelSelector.title = chatModelSelector.selectedOptions[0]?.title || 'Choose the model for this chat';
    });
    if (guideBtn) guideBtn.addEventListener('click', () => openGuide(0));
    if (guideClose) guideClose.addEventListener('click', closeGuide);
    if (guideBack) guideBack.addEventListener('click', () => { guidePageIndex -= 1; updateGuidePage(); });
    if (guideNext) guideNext.addEventListener('click', () => {
        if (guidePageIndex >= 1) closeGuide();
        else { guidePageIndex += 1; updateGuidePage(); }
    });
    if (guideModal) {
        guideModal.addEventListener('click', event => {
            if (event.target === guideModal) closeGuide();
            const command = event.target.closest('[data-guide-command]');
            if (command && messageInput) {
                messageInput.value = command.dataset.guideCommand || '';
                autoResizeInput();
                closeGuide();
            }
        });
    }
    if (toggleAutoActivity) {
        toggleAutoActivity.addEventListener('change', () => {
            settings.autoOpenActivity = toggleAutoActivity.checked;
            saveSettings();
        });
    }
    if (toggleAutoSearch) {
        toggleAutoSearch.addEventListener('change', () => {
            settings.autoOpenSearchResults = toggleAutoSearch.checked;
            saveSettings();
        });
    }
    if (toggleAutoApproveWork) {
        toggleAutoApproveWork.addEventListener('change', () => {
            settings.autoApproveSafeWork = toggleAutoApproveWork.checked;
            saveSettings();
        });
    }
    if (toggleThinkingSounds) {
        toggleThinkingSounds.addEventListener('change', () => {
            settings.thinkingSounds = toggleThinkingSounds.checked;
            saveSettings();
        });
    }
    if (toggleVoiceInterrupt) {
        toggleVoiceInterrupt.addEventListener('change', () => {
            settings.voiceInterrupt = toggleVoiceInterrupt.checked;
            saveSettings();
        });
    }
}

function timeAgo(unixSeconds) {
    const diffMs = Date.now() - unixSeconds * 1000;
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
}

async function loadHistoryList() {
    if (!historyList) return;
    historyList.innerHTML = '<div class="activity-empty">Loading...</div>';
    try {
        const r = await fetch(`${API}/chat/sessions`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        const sessions = data.sessions || [];
        if (sessions.length === 0) {
            historyList.innerHTML = '<div class="activity-empty" id="history-empty">No previous chats yet.</div>';
            return;
        }
        historyList.innerHTML = '';
        sessions.forEach(s => {
            const item = document.createElement('div');
            item.className = 'history-item' + (s.session_id === sessionId ? ' active' : '');
            const body = document.createElement('div');
            body.className = 'history-item-body';
            body.innerHTML = `
                <div class="history-item-preview">${escapeHtml(s.preview || '(empty chat)')}</div>
                <div class="history-item-meta">${s.turn_count || 0} message${s.turn_count === 1 ? '' : 's'} · ${timeAgo(s.updated_at)}</div>`;
            body.addEventListener('click', () => loadSession(s.session_id));
            const delBtn = document.createElement('button');
            delBtn.className = 'history-item-delete';
            delBtn.title = 'Delete this chat';
            delBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>';
            delBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                deleteSession(s.session_id, item);
            });
            item.appendChild(body);
            item.appendChild(delBtn);
            historyList.appendChild(item);
        });
    } catch (e) {
        historyList.innerHTML = '<div class="activity-empty">Could not load chat history.</div>';
        console.warn('[JARVIS] Failed to load sessions:', e);
    }
}

async function deleteSession(targetSessionId, itemEl) {
    try {
        const r = await fetch(`${API}/chat/sessions/${encodeURIComponent(targetSessionId)}`, { method: 'DELETE' });
        if (!r.ok && r.status !== 404) throw new Error(`HTTP ${r.status}`);
        if (itemEl && itemEl.parentNode) itemEl.parentNode.removeChild(itemEl);
        if (historyList && !historyList.querySelector('.history-item')) {
            historyList.innerHTML = '<div class="activity-empty" id="history-empty">No previous chats yet.</div>';
        }
        if (targetSessionId === sessionId) {
            newChat();
        }
    } catch (e) {
        showToast('Could not delete that chat.');
        console.warn('[JARVIS] Failed to delete session:', e);
    }
}

async function loadSession(targetSessionId) {
    if (!targetSessionId || isStreaming) return;
    try {
        const r = await fetch(`${API}/chat/history/${encodeURIComponent(targetSessionId)}`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        const turns = data.turns || [];

        if (ttsPlayer) ttsPlayer.stop();
        if (camStream) stopCamera();
        sessionId = targetSessionId;
        if (chatMessages) chatMessages.innerHTML = '';

        if (turns.length === 0) {
            chatMessages.appendChild(createWelcome());
        } else {
            turns.forEach(t => {
                if (t.user) addMessage('user', t.user);
                if (t.assistant) addMessage('assistant', t.assistant);
            });
        }

        if (historyPanel) { historyPanel.classList.remove('open'); updatePanelOverlay(); }
        if (activityList) {
            activityList.innerHTML = '<div class="activity-empty" id="activity-empty">Send a message to see the flow here.</div>';
        }
        scrollToBottom();
    } catch (e) {
        showToast('Could not load that conversation.');
        console.warn('[JARVIS] Failed to load session:', e);
    }
}

function openScrapeModal() {
    if (!scrapeModal) return;
    scrapeModal.classList.add('open');
    scrapeModal.setAttribute('aria-hidden', 'false');
    if (scrapeUrlInput) {
        scrapeUrlInput.value = '';
        setTimeout(() => scrapeUrlInput.focus(), 50);
    }
}

function closeScrapeModal() {
    if (!scrapeModal) return;
    scrapeModal.classList.remove('open');
    scrapeModal.setAttribute('aria-hidden', 'true');
}

function submitScrapeModal() {
    if (!scrapeUrlInput) return;
    let url = scrapeUrlInput.value.trim();
    if (!url) { showToast('Enter a URL to scrape.'); return; }
    if (!/^https?:\/\//i.test(url)) url = 'https://' + url;
    closeScrapeModal();
    if (!isStreaming) sendMessage(`Scrape ${url}`);
}

let intelActiveTab = 'watchlists';
let intelMissionPollTimer = null;
let intelRenderToken = 0;

function isCurrentIntelRender(tab, token) {
    return intelActiveTab === tab && intelRenderToken === token;
}

async function apiGet(path, timeoutMs = 20000) {
    const controller = new AbortController();
    const t = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const r = await fetch(`${API}${path}`, { signal: controller.signal });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return await r.json();
    } catch (e) {
        if (e.name === 'AbortError') throw new Error('Request timed out.');
        throw e;
    } finally {
        clearTimeout(t);
    }
}
async function apiPost(path, body, timeoutMs = 90000) {
    const controller = new AbortController();
    const t = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const r = await fetch(`${API}${path}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body || {}), signal: controller.signal,
        });
        if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${r.status}`); }
        return await r.json();
    } catch (e) {
        if (e.name === 'AbortError') throw new Error('Request timed out — the scraper may still be running in the background.');
        throw e;
    } finally {
        clearTimeout(t);
    }
}
async function apiDelete(path) {
    const r = await fetch(`${API}${path}`, { method: 'DELETE' });
    if (!r.ok && r.status !== 404) throw new Error(`HTTP ${r.status}`);
    return r.json().catch(() => ({}));
}

function openIntelDashboard() {
    if (!intelDashboard) return;
    intelDashboard.classList.add('open');
    intelDashboard.setAttribute('aria-hidden', 'false');
    switchIntelTab(intelActiveTab);
}
function closeIntelDashboard() {
    if (!intelDashboard) return;
    intelDashboard.classList.remove('open');
    intelDashboard.setAttribute('aria-hidden', 'true');
    if (intelMissionPollTimer) { clearInterval(intelMissionPollTimer); intelMissionPollTimer = null; }
}

function switchIntelTab(tab) {
    intelActiveTab = tab;
    const renderToken = ++intelRenderToken;
    if (intelMissionPollTimer) { clearInterval(intelMissionPollTimer); intelMissionPollTimer = null; }
    document.querySelectorAll('.intel-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    if (!intelTabContent) return;
    intelTabContent.innerHTML = '<div class="activity-empty">Loading...</div>';
    if (tab === 'watchlists') renderWatchlistsTab(renderToken);
    else if (tab === 'health') renderHealthTab(renderToken);
    else if (tab === 'feed') renderFeedTab(renderToken);
    else if (tab === 'research') renderResearchTab(renderToken);
    else if (tab === 'history') renderHistoryTab(renderToken);
    renderMetricsBar();
}

async function renderMetricsBar() {
    const bar = $('intel-metrics-bar');
    if (!bar) return;
    try {
        const s = await apiGet('/intelligence/summary');
        bar.innerHTML = `
            <div class="intel-metric"><span class="intel-metric-value">${s.monitored_entities}</span><span class="intel-metric-label">Entities</span></div>
            <div class="intel-metric"><span class="intel-metric-value">${s.active_sources}</span><span class="intel-metric-label">Sources</span></div>
            <div class="intel-metric"><span class="intel-metric-value" style="color:var(--success)">${s.runs_success}</span><span class="intel-metric-label">Successful runs</span></div>
            <div class="intel-metric"><span class="intel-metric-value" style="color:var(--danger)">${s.runs_failed}</span><span class="intel-metric-label">Failed runs</span></div>
            <div class="intel-metric"><span class="intel-metric-value">${s.changes_detected}</span><span class="intel-metric-label">Changes found</span></div>
            <div class="intel-metric"><span class="intel-metric-value">${s.missions_completed}</span><span class="intel-metric-label">Missions done</span></div>
            <div class="intel-metric"><span class="intel-metric-value" style="font-size:0.78rem;">${s.last_scan ? timeAgoShort(s.last_scan) : '—'}</span><span class="intel-metric-label">Last scan</span></div>`;
    } catch (e) {
        bar.innerHTML = '';
    }
}

function timeAgoShort(iso) {
    if (!iso) return '—';
    const ms = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(ms / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
}

// ---------- Watchlists tab ----------
async function renderWatchlistsTab(renderToken = intelRenderToken) {
    if (!isCurrentIntelRender('watchlists', renderToken)) return;
    try {
        const data = await apiGet('/watchlists');
        if (!isCurrentIntelRender('watchlists', renderToken)) return;
        const entries = data.watchlists || [];
        let html = `
            <div class="intel-toolbar">
                <button class="intel-btn" id="intel-scan-all-btn">Run All Watchlists</button>
            </div>
            <div class="intel-add-row">
                <input type="text" class="intel-input" id="intel-new-entity" placeholder="Entity name (e.g. NVIDIA)">
                <input type="text" class="intel-input" id="intel-new-categories" placeholder="Categories, comma separated (optional)">
                <button class="intel-btn" id="intel-add-watchlist-btn">Add</button>
            </div>
            <div id="intel-watchlist-list">`;
        if (entries.length === 0) {
            html += '<div class="intel-empty">No entities monitored yet. Add one above, or just say "Monitor NVIDIA" in chat.</div>';
        } else {
            entries.forEach(e => {
                html += `
                    <div class="intel-card" data-id="${escapeHtml(e.id)}">
                        <div class="intel-card-header">
                            <span class="intel-card-title">${escapeHtml(e.name)}</span>
                            <span class="intel-card-meta">${e.sources.length} source(s) · last scan ${timeAgoShort(e.last_scan)}</span>
                        </div>
                        <div class="intel-card-meta">Categories: ${escapeHtml(e.categories.join(', '))}</div>
                        <div class="intel-card-actions">
                            <button class="intel-btn scan-one-btn" data-id="${escapeHtml(e.id)}">Scan now</button>
                            <button class="intel-btn secondary history-one-btn" data-id="${escapeHtml(e.id)}">View history</button>
                            <a class="intel-btn secondary" href="${API}/watchlists/${encodeURIComponent(e.id)}/history" target="_blank" rel="noopener">View JSON</a>
                            <button class="intel-btn secondary remove-one-btn" data-id="${escapeHtml(e.id)}">Remove</button>
                        </div>
                        <div class="intel-card-detail" id="intel-detail-${escapeHtml(e.id)}"></div>
                    </div>`;
            });
        }
        html += '</div>';
        intelTabContent.innerHTML = html;

        $('intel-scan-all-btn')?.addEventListener('click', async (ev) => {
            ev.target.disabled = true; ev.target.textContent = 'Scanning (this can take up to a minute)...';
            try { const r = await apiPost('/watchlists/scan-all'); showToast('Scan complete.'); renderWatchlistsTab(); }
            catch (e) { showToast(e.message || 'Scan failed.'); ev.target.disabled = false; ev.target.textContent = 'Run All Watchlists'; }
        });
        $('intel-add-watchlist-btn')?.addEventListener('click', async (ev) => {
            const name = $('intel-new-entity').value.trim();
            if (!name) { showToast('Enter an entity name.'); return; }
            const catsRaw = $('intel-new-categories').value.trim();
            const categories = catsRaw ? catsRaw.split(',').map(c => c.trim()).filter(Boolean) : null;
            const btn = ev.currentTarget;
            btn.disabled = true;
            btn.textContent = 'Adding...';
            try {
                await apiPost('/watchlists', { name, categories }, 15000);
                showToast(`${name} is now monitored.`);
                await renderWatchlistsTab();
            } catch (e) {
                showToast(`Could not add ${name}: ${e.message || 'unknown error'}`);
                btn.disabled = false;
                btn.textContent = 'Add';
            }
        });
        document.querySelectorAll('.scan-one-btn').forEach(btn => btn.addEventListener('click', async () => {
            const id = btn.dataset.id;
            const detailEl = $(`intel-detail-${id}`);
            btn.disabled = true; btn.textContent = 'Scanning (up to ~1 min)...';
            if (detailEl) detailEl.innerHTML = '<div class="intel-card-meta" style="margin-top:8px;">Scraping — please wait...</div>';
            try {
                const result = await apiPost(`/watchlists/${encodeURIComponent(id)}/scan`);
                showToast('Scan complete.');
                if (detailEl && result.results) {
                    let inner = '';
                    result.results.forEach(r => {
                        if (r.status === 'no_source_found') {
                            inner += `<div class="intel-card-meta" style="margin-top:8px;"><strong>${escapeHtml(r.category)}</strong>: no source URL could be discovered (check TAVILY_API_KEY, or add a source manually).</div>`;
                            return;
                        }
                        inner += `<div class="intel-card-meta" style="margin-top:8px;"><strong>${escapeHtml(r.category)}</strong>: ${escapeHtml(r.status)} via ${escapeHtml(r.source || 'n/a')} — ${r.changes ? r.changes.length : 0} change(s)</div>`;
                    });
                    detailEl.innerHTML = inner;
                    detailEl.dataset.open = '1';
                    // Also pull the freshest snapshot content so the scrape result is actually visible.
                    for (const r of result.results) {
                        if (r.status !== 'no_source_found') {
                            appendSnapshotPreview(detailEl, entries.find(e => e.id === id)?.name || '', r.category);
                        }
                    }
                }
            } catch (e) {
                showToast(e.message || 'Scan failed.');
                if (detailEl) detailEl.innerHTML = `<div class="intel-card-meta" style="margin-top:8px; color: var(--danger);">Scan failed: ${escapeHtml(e.message || 'unknown error')}</div>`;
            } finally {
                btn.disabled = false; btn.textContent = 'Scan now';
            }
        }));
        document.querySelectorAll('.remove-one-btn').forEach(btn => btn.addEventListener('click', async () => {
            const id = btn.dataset.id;
            try { await apiDelete(`/watchlists/${encodeURIComponent(id)}`); renderWatchlistsTab(); }
            catch (e) { showToast('Could not remove entry.'); }
        }));
        document.querySelectorAll('.history-one-btn').forEach(btn => btn.addEventListener('click', async () => {
            const id = btn.dataset.id;
            const detailEl = $(`intel-detail-${id}`);
            if (!detailEl) return;
            if (detailEl.dataset.open === '1') { detailEl.innerHTML = ''; detailEl.dataset.open = '0'; return; }
            detailEl.innerHTML = '<div class="intel-card-meta">Loading history...</div>';
            try {
                const hist = await apiGet(`/watchlists/${encodeURIComponent(id)}/history`);
                let inner = '';
                for (const [cat, obj] of Object.entries(hist.history || {})) {
                    const snaps = obj.snapshots || [];
                    inner += `<div class="intel-card-meta" style="margin-top:8px;"><strong>${escapeHtml(cat)}</strong>: ${snaps.length} snapshot(s)`;
                    if (snaps.length) {
                        const latest = snaps[snaps.length - 1];
                        inner += ` · latest ${timeAgoShort(latest.timestamp)} (${escapeHtml(latest.scraper_id)})`;
                        const preview = latest.data && latest.data.text ? latest.data.text
                            : (Array.isArray(latest.data) ? JSON.stringify(latest.data.slice(0, 2), null, 2) : JSON.stringify(latest.data));
                        inner += `<div style="margin-top:4px; padding:8px 10px; background:rgba(0,0,0,0.25); border-radius:8px; white-space:pre-wrap; max-height:180px; overflow-y:auto; font-size:0.72rem;">${escapeHtml((preview || '(no content captured)').slice(0, 1200))}</div>`;
                    }
                    inner += '</div>';
                }
                detailEl.innerHTML = inner || '<div class="intel-card-meta">No snapshots yet.</div>';
                detailEl.dataset.open = '1';
            } catch (e) { detailEl.innerHTML = `<div class="intel-card-meta">Could not load history: ${escapeHtml(e.message || '')}</div>`; }
        }));
    } catch (e) {
        if (isCurrentIntelRender('watchlists', renderToken)) {
            intelTabContent.innerHTML = `<div class="intel-empty">Could not load watchlists: ${escapeHtml(e.message || 'request failed')}.</div>`;
        }
    }
}

async function appendSnapshotPreview(detailEl, entityName, category) {
    try {
        const hist = await apiGet(`/watchlists/${encodeURIComponent(entityName)}/history`);
        const snaps = (hist.history && hist.history[category] && hist.history[category].snapshots) || [];
        if (!snaps.length) return;
        const latest = snaps[snaps.length - 1];
        const preview = latest.data && latest.data.text ? latest.data.text
            : (Array.isArray(latest.data) ? JSON.stringify(latest.data.slice(0, 2), null, 2) : JSON.stringify(latest.data));
        const block = document.createElement('div');
        block.style.cssText = 'margin-top:4px; padding:8px 10px; background:rgba(0,0,0,0.25); border-radius:8px; white-space:pre-wrap; max-height:180px; overflow-y:auto; font-size:0.72rem;';
        block.textContent = (preview || '(no content captured)').slice(0, 1200);
        detailEl.appendChild(block);
    } catch (e) { /* silent — preview is best-effort */ }
}

// ---------- Scraper Health tab ----------
function stateBadgeClass(state) {
    return 'state-' + (state || 'healthy').toLowerCase();
}
async function renderHealthTab(renderToken = intelRenderToken) {
    if (!isCurrentIntelRender('health', renderToken)) return;
    try {
        const data = await apiGet('/scraper-health');
        if (!isCurrentIntelRender('health', renderToken)) return;
        const sources = data.sources || [];
        let html = `<div class="intel-toolbar">
            <button class="intel-btn secondary" id="intel-health-refresh">Refresh</button>
            <a class="intel-btn secondary" href="${API}/scraper-health" target="_blank" rel="noopener">View raw JSON</a>
        </div>`;
        if (sources.length === 0) {
            html += '<div class="intel-empty">No scraper runs yet. Add a watchlist entity and scan it to populate this board.</div>';
        } else {
            sources.forEach(s => {
                let originNote = '';
                if (s.recovered_by) originNote = `Recovered by: ${s.recovered_by}`;
                else if (s.detected_by && s.manual_intervention_required) originNote = `Detected by: ${s.detected_by} — manual intervention required`;
                else if (s.detected_by) originNote = `Detected by: ${s.detected_by}`;
                html += `
                    <div class="intel-card">
                        <div class="intel-card-header">
                            <span class="intel-card-title">${escapeHtml(s.entity)} — ${escapeHtml(s.category)}</span>
                            <span class="intel-badge ${stateBadgeClass(s.state)}">${escapeHtml(s.state)}</span>
                        </div>
                        <div class="intel-card-meta">
                            Last run: ${timeAgoShort(s.last_run)} · Last success: ${timeAgoShort(s.last_success)}<br>
                            Source: ${escapeHtml(s.collector_source || 'n/a')} · Fields extracted: ${s.fields_extracted ?? 0}
                            ${s.missing_fields && s.missing_fields.length ? ` · Missing: ${escapeHtml(s.missing_fields.join(', '))}` : ''}
                            ${s.error ? `<br>Error: ${escapeHtml(s.error)}` : ''}
                            ${originNote ? `<br>${escapeHtml(originNote)}` : ''}
                        </div>
                    </div>`;
            });
        }
        intelTabContent.innerHTML = html;
        $('intel-health-refresh')?.addEventListener('click', () => renderHealthTab());
    } catch (e) {
        if (isCurrentIntelRender('health', renderToken)) {
            intelTabContent.innerHTML = `<div class="intel-empty">Could not load scraper health: ${escapeHtml(e.message || 'request failed')}.</div>`;
        }
    }
}

// ---------- Live Feed tab ----------
async function renderFeedTab(renderToken = intelRenderToken) {
    if (!isCurrentIntelRender('feed', renderToken)) return;
    try {
        const data = await apiGet('/intelligence/feed?limit=40');
        if (!isCurrentIntelRender('feed', renderToken)) return;
        const changes = data.changes || [];
        let html = `<div class="intel-toolbar">
            <button class="intel-btn secondary" id="intel-feed-refresh">Refresh</button>
            <a class="intel-btn secondary" href="${API}/intelligence/feed?limit=200" target="_blank" rel="noopener">View raw JSON</a>
        </div>`;
        if (changes.length === 0) {
            html += '<div class="intel-empty">No changes detected yet. Scan your watchlist a couple of times to start building history.</div>';
        } else {
            html += '<div class="intel-card">';
            changes.forEach((c, idx) => {
                const t = c.detected_at ? new Date(c.detected_at) : null;
                const timeLabel = t ? t.toTimeString().slice(0, 5) : '';
                let detail = `${escapeHtml(c.change_type || 'change')} on ${escapeHtml(c.field || '')}`;
                if (c.before !== undefined || c.after !== undefined) {
                    detail += ` — ${escapeHtml(String(c.before))} → ${escapeHtml(String(c.after))}`;
                }
                if (c.percentage_change !== undefined && c.percentage_change !== null) {
                    detail += ` (${c.percentage_change > 0 ? '+' : ''}${c.percentage_change}%)`;
                }
                html += `
                    <div class="intel-change-row intel-change-clickable" data-idx="${idx}">
                        <div class="intel-change-time">${escapeHtml(timeLabel)}</div>
                        <div class="intel-change-body">
                            <div class="intel-change-entity">${escapeHtml(c.entity || 'Unknown')}${c.category ? ` <span class="intel-change-cat">· ${escapeHtml(c.category)}</span>` : ''}</div>
                            <div class="intel-change-detail">${detail}</div>
                            <div class="intel-change-expand" id="intel-change-expand-${idx}"></div>
                        </div>
                    </div>`;
            });
            html += '</div>';
        }
        intelTabContent.innerHTML = html;
        $('intel-feed-refresh')?.addEventListener('click', () => renderFeedTab());

        document.querySelectorAll('.intel-change-clickable').forEach(row => {
            row.addEventListener('click', async () => {
                const idx = parseInt(row.dataset.idx, 10);
                const change = changes[idx];
                const expandEl = $(`intel-change-expand-${idx}`);
                if (!expandEl) return;
                if (expandEl.dataset.open === '1') { expandEl.innerHTML = ''; expandEl.dataset.open = '0'; return; }

                let detailHtml = '<div class="intel-card-meta" style="margin-top:8px;">';
                if (change.source_url) detailHtml += `Source: ${escapeHtml(change.source_url)}<br>`;
                detailHtml += `Detected: ${escapeHtml(change.detected_at || 'unknown')}<br>`;
                detailHtml += `Before: ${escapeHtml(String(change.before))}<br>`;
                detailHtml += `After: ${escapeHtml(String(change.after))}`;
                detailHtml += '</div><div class="intel-card-meta" id="intel-change-explain-' + idx + '" style="margin-top:6px; font-style:italic;">Loading explanation...</div>';
                expandEl.innerHTML = detailHtml;
                expandEl.dataset.open = '1';

                try {
                    const resp = await apiPost('/intelligence/explain-change', change);
                    const explainEl = $(`intel-change-explain-${idx}`);
                    if (explainEl) { explainEl.style.fontStyle = 'normal'; explainEl.textContent = resp.explanation; }
                } catch (e) {
                    const explainEl = $(`intel-change-explain-${idx}`);
                    if (explainEl) explainEl.textContent = 'Could not load an explanation.';
                }
            });
        });
    } catch (e) {
        if (isCurrentIntelRender('feed', renderToken)) {
            intelTabContent.innerHTML = `<div class="intel-empty">Could not load the live feed: ${escapeHtml(e.message || 'request failed')}.</div>`;
        }
    }
}

// ---------- History tab ----------
async function renderHistoryTab(renderToken = intelRenderToken) {
    if (!isCurrentIntelRender('history', renderToken)) return;
    try {
        const data = await apiGet('/intelligence/history/unified?limit=80');
        if (!isCurrentIntelRender('history', renderToken)) return;
        const events = data.events || [];
        let html = `<div class="intel-toolbar">
            <button class="intel-btn secondary" id="intel-history-refresh">Refresh</button>
            <a class="intel-btn secondary" href="${API}/intelligence/history/unified?limit=300" target="_blank" rel="noopener">View raw JSON</a>
        </div>`;
        if (events.length === 0) {
            html += '<div class="intel-empty">No history yet — add a watchlist entity, run a scan, or start a research mission to populate this timeline.</div>';
        } else {
            html += '<div class="intel-card">';
            events.forEach(e => {
                const t = e.timestamp ? new Date(e.timestamp) : null;
                const timeLabel = t ? `${t.toLocaleDateString()} ${t.toTimeString().slice(0, 5)}` : '';
                html += `
                    <div class="intel-change-row">
                        <div class="intel-change-time" style="width:110px;">${escapeHtml(timeLabel)}</div>
                        <div class="intel-change-body">
                            <div class="intel-change-entity">${escapeHtml((e.type || '').replace(/_/g, ' '))}</div>
                            <div class="intel-change-detail">${escapeHtml(e.summary || '')}</div>
                        </div>
                    </div>`;
            });
            html += '</div>';
        }
        intelTabContent.innerHTML = html;
        $('intel-history-refresh')?.addEventListener('click', () => renderHistoryTab());
    } catch (e) {
        if (isCurrentIntelRender('history', renderToken)) {
            intelTabContent.innerHTML = `<div class="intel-empty">Could not load history: ${escapeHtml(e.message || 'request failed')}.</div>`;
        }
    }
}

// ---------- Research Missions tab ----------
async function renderResearchTab(renderToken = intelRenderToken) {
    if (!isCurrentIntelRender('research', renderToken)) return;
    try {
        const data = await apiGet('/research/missions');
        if (!isCurrentIntelRender('research', renderToken)) return;
        const missions = data.missions || [];
        let html = `
            <div class="intel-add-row">
                <input type="text" class="intel-input" id="intel-mission-input" placeholder="Research goal, e.g. 'Compare the major AI API providers'">
                <button class="intel-btn" id="intel-mission-start">Start Mission</button>
            </div>
            <div id="intel-mission-list">`;
        if (missions.length === 0) {
            html += '<div class="intel-empty">No research missions yet.</div>';
        } else {
            missions.forEach(m => {
                html += `
                    <div class="intel-card">
                        <div class="intel-card-header">
                            <span class="intel-card-title">${escapeHtml(m.query)}</span>
                            <span class="intel-badge ${m.status === 'completed' ? 'state-healthy' : m.status === 'failed' ? 'state-extraction_failed' : 'state-healing'}">${escapeHtml(m.status)}</span>
                        </div>
                        <div class="intel-card-meta">${escapeHtml(m.current_step || '')} · started ${timeAgoShort(m.started_at)} · ${(m.sources || []).length} source(s)</div>
                        ${m.findings ? `<div class="intel-card-meta" style="margin-top:8px; white-space:pre-wrap;">${escapeHtml(m.findings)}</div>` : ''}
                        <div class="intel-card-actions">
                            <a class="intel-btn secondary" href="${API}/research/missions/${encodeURIComponent(m.mission_id)}" target="_blank" rel="noopener">View JSON</a>
                        </div>
                    </div>`;
            });
        }
        html += '</div>';
        intelTabContent.innerHTML = html;

        $('intel-mission-start')?.addEventListener('click', async () => {
            const input = $('intel-mission-input');
            const query = input.value.trim();
            if (!query) { showToast('Enter a research goal.'); return; }
            input.value = '';
            try { await apiPost('/research/missions', { query }); renderResearchTab(); }
            catch (e) { showToast('Could not start mission.'); }
        });

        const anyRunning = missions.some(m => m.status === 'running');
        if (anyRunning && !intelMissionPollTimer) {
            intelMissionPollTimer = setInterval(() => {
                if (intelActiveTab === 'research') renderResearchTab();
                else { clearInterval(intelMissionPollTimer); intelMissionPollTimer = null; }
            }, 4000);
        }
    } catch (e) {
        if (isCurrentIntelRender('research', renderToken)) {
            intelTabContent.innerHTML = `<div class="intel-empty">Could not load research missions: ${escapeHtml(e.message || 'request failed')}.</div>`;
        }
    }
}

function autoResizeInput() {
    messageInput.style.height = 'auto';
    messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + 'px';
}

function updatePanelOverlay() {
    if (!panelOverlay) return;
    const anyOpen = (activityPanel && activityPanel.classList.contains('open')) ||
        (historyPanel && historyPanel.classList.contains('open')) ||
        (searchResultsWidget && searchResultsWidget.classList.contains('open')) ||
        (settingsPanel && settingsPanel.classList.contains('open')) ||
        (researchFilesPanel && researchFilesPanel.classList.contains('open'));
    panelOverlay.classList.toggle('visible', !!anyOpen);
}

function workspaceKey(mode = currentMode, researchBranch = currentResearchBranch) {
    if (mode !== 'research') return mode;
    return researchBranch === 'homework' ? 'homework' : 'research';
}

function getWorkspaceState(key) {
    if (!workspaceStates.has(key)) {
        workspaceStates.set(key, {
            sessionId: null,
            messages: null,
            activity: null,
            activityToggleDisplay: 'none',
            searchToggleDisplay: 'none',
            searchOpen: false,
            searchQuery: '',
            searchAnswer: '',
            searchResults: null,
        });
    }
    return workspaceStates.get(key);
}

function saveWorkspaceState(key) {
    if (!chatMessages) return;
    const state = getWorkspaceState(key);
    state.sessionId = sessionId;
    state.messages = document.createDocumentFragment();
    while (chatMessages.firstChild) state.messages.appendChild(chatMessages.firstChild);
    if (activityList) {
        state.activity = document.createDocumentFragment();
        while (activityList.firstChild) state.activity.appendChild(activityList.firstChild);
    }
    state.activityToggleDisplay = activityToggle?.style.display || '';
    state.searchToggleDisplay = searchResultsToggle?.style.display || '';
    state.searchOpen = !!searchResultsWidget?.classList.contains('open');
    state.searchQuery = searchResultsQuery?.textContent || '';
    state.searchAnswer = searchResultsAnswer?.textContent || '';
    if (searchResultsList) {
        state.searchResults = document.createDocumentFragment();
        while (searchResultsList.firstChild) state.searchResults.appendChild(searchResultsList.firstChild);
    }
}

function restoreWorkspaceState(key) {
    if (!chatMessages) return;
    const state = getWorkspaceState(key);
    sessionId = state.sessionId;
    chatMessages.replaceChildren();
    if (state.messages?.childNodes.length) chatMessages.appendChild(state.messages);
    else chatMessages.appendChild(createWelcome());
    if (activityList) {
        activityList.replaceChildren();
        if (state.activity?.childNodes.length) activityList.appendChild(state.activity);
        else activityList.innerHTML = '<div class="activity-empty" id="activity-empty">Send a message to see the flow here.</div>';
    }
    if (activityToggle) activityToggle.style.display = state.activityToggleDisplay;
    if (searchResultsToggle) searchResultsToggle.style.display = state.searchToggleDisplay;
    if (searchResultsWidget) searchResultsWidget.classList.toggle('open', state.searchOpen);
    if (searchResultsQuery) searchResultsQuery.textContent = state.searchQuery;
    if (searchResultsAnswer) searchResultsAnswer.textContent = state.searchAnswer;
    if (searchResultsList) {
        searchResultsList.replaceChildren();
        if (state.searchResults?.childNodes.length) searchResultsList.appendChild(state.searchResults);
    }
    scrollToBottom();
}

function shouldAutoOpenActivity() {
    return settings.autoOpenActivity && (currentMode !== 'research' || currentResearchBranch === 'research');
}

function setMode(mode, announce = true) {
    const supportedModes = new Set(['edit', 'work', 'research']);
    const nextMode = supportedModes.has(mode) ? mode : 'edit';
    const nextWorkspaceKey = workspaceKey(nextMode, currentResearchBranch);
    if (isStreaming && nextWorkspaceKey !== activeWorkspaceKey) {
        showToast('Please let the current response finish before switching modes.');
        return;
    }
    if (nextWorkspaceKey !== activeWorkspaceKey) {
        saveWorkspaceState(activeWorkspaceKey);
        activeWorkspaceKey = nextWorkspaceKey;
        restoreWorkspaceState(activeWorkspaceKey);
    }
    currentMode = nextMode;
    const appEl = document.querySelector('.app');
    const isWork = currentMode === 'work';
    const isResearch = currentMode === 'research';
    const isHomework = isResearch && currentResearchBranch === 'homework';

    if (btnJarvis) btnJarvis.classList.toggle('active', !isWork && !isResearch);
    if (btnScraper) btnScraper.classList.toggle('active', isWork);
    if (btnResearch) btnResearch.classList.toggle('active', isResearch);
    if (modeSlider) {
        modeSlider.classList.toggle('center', isWork);
        modeSlider.classList.toggle('right', isResearch);
    }
    if (appEl) appEl.classList.toggle('mode-work', isWork);
    if (appEl) appEl.classList.toggle('mode-research', isResearch);
    if (appEl) appEl.classList.toggle('mode-homework', isHomework);
    if (researchBranchSwitch) researchBranchSwitch.hidden = !isResearch;
    if (researchSourceControl) researchSourceControl.hidden = !isHomework;
    if (researchSourceManager) researchSourceManager.hidden = !isResearch;
    if (isResearch) loadResearchSources();
    else if (researchSourcesPopover) researchSourcesPopover.hidden = true;
    if (!isHomework && researchSourceForm) researchSourceForm.hidden = true;
    if (chatModelSelector) {
        chatModelSelector.hidden = false;
        chatModelSelector.title = isHomework
            ? 'Gemini is the Homework default when Auto is selected; choose any configured model to override it'
            : 'Choose one model or let Auto use provider failover';
    }
    if (homeworkSolutionBoard) homeworkSolutionBoard.hidden = !isHomework;
    if (homeworkLayoutDivider) homeworkLayoutDivider.hidden = !isHomework;
    if (isHomework) setHomeworkLayout(Number(localStorage.getItem('edith_homework_board_percent') || 75), false);
    else if (chatArea) chatArea.style.removeProperty('grid-template-columns');
    if (researchFilesToggle) researchFilesToggle.hidden = !isResearch;
    if (activityToggle && isResearch && !isHomework) activityToggle.style.display = '';
    if (!isResearch) closeResearchFiles();
    if (isHomework && activityPanel) {
        activityPanel.classList.remove('open');
        updatePanelOverlay();
    }
    if (messageInput) {
        messageInput.placeholder = isWork
            ? 'Describe the result you want E.D.I.T.H. to create...'
            : isResearch && currentResearchBranch === 'homework'
                ? 'Upload homework screenshots or type the problems to solve...'
                : isResearch
                    ? 'Research a topic or upload screenshots and documents...'
                    : 'Ask E.D.I.T.H. anything...';
    }
    refreshWelcomeForMode();
    if (announce) {
        const label = isWork ? 'Work Mode' : isResearch ? `Research Mode · ${currentResearchBranch}` : 'E.D.I.T.H. Mode';
        showToast(`${label} enabled`);
    }
}

let pluginCache = [];
let pluginStoreCache = [];
let pluginView = 'installed';
let configuringPluginId = null;

function closePluginManager() {
    if (!intelDashboard) return;
    intelDashboard.classList.remove('open');
    intelDashboard.setAttribute('aria-hidden', 'true');
}

async function openPluginManager() {
    if (!intelDashboard) return;
    intelDashboard.classList.add('open');
    intelDashboard.setAttribute('aria-hidden', 'false');
    await loadPlugins();
}

async function loadPlugins() {
    const list = $('plugin-list');
    if (!list) return;
    list.innerHTML = '<div class="activity-empty">Loading plugins...</div>';
    try {
        const response = await fetch(`${API}/plugins`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        pluginCache = (await response.json()).plugins || [];
        if (pluginView === 'store') await loadPluginStore();
        else renderPlugins($('plugin-search')?.value || '');
        const search = $('plugin-search');
        if (search && !search.dataset.bound) {
            search.dataset.bound = '1';
            search.addEventListener('input', () => pluginView === 'store' ? renderPluginStore(search.value) : renderPlugins(search.value));
        }
        bindPluginStoreControls();
    } catch (error) {
        list.innerHTML = `<div class="intel-empty">Could not load plugins: ${escapeHtml(error.message)}</div>`;
    }
}

async function loadPluginStore() {
    const list = $('plugin-list');
    if (list) list.innerHTML = '<div class="activity-empty">Loading the plugin store...</div>';
    const response = await fetch(`${API}/plugins/store`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    pluginStoreCache = (await response.json()).plugins || [];
    renderPluginStore($('plugin-search')?.value || '');
}

function setPluginView(view) {
    pluginView = view === 'store' ? 'store' : 'installed';
    $('plugin-installed-tab')?.classList.toggle('active', pluginView === 'installed');
    $('plugin-store-tab')?.classList.toggle('active', pluginView === 'store');
    if ($('plugin-manifest-row')) $('plugin-manifest-row').hidden = pluginView !== 'store';
    if ($('plugin-discovery-row')) $('plugin-discovery-row').hidden = pluginView !== 'store';
    if ($('plugin-search')) $('plugin-search').placeholder = pluginView === 'store' ? 'Search the plugin store...' : 'Search installed plugins...';
    if (pluginView === 'store') loadPluginStore().catch(error => { $('plugin-list').innerHTML = `<div class="intel-empty">Could not load store: ${escapeHtml(error.message)}</div>`; });
    else renderPlugins($('plugin-search')?.value || '');
}

function bindPluginStoreControls() {
    const installedTab = $('plugin-installed-tab');
    const storeTab = $('plugin-store-tab');
    const manifestInstall = $('plugin-manifest-install');
    if (installedTab && !installedTab.dataset.bound) {
        installedTab.dataset.bound = '1';
        installedTab.addEventListener('click', () => setPluginView('installed'));
    }
    if (storeTab && !storeTab.dataset.bound) {
        storeTab.dataset.bound = '1';
        storeTab.addEventListener('click', () => setPluginView('store'));
    }
    if (manifestInstall && !manifestInstall.dataset.bound) {
        manifestInstall.dataset.bound = '1';
        manifestInstall.addEventListener('click', installPluginManifest);
    }
    const configClose = $('plugin-config-close');
    const configCancel = $('plugin-config-cancel');
    const configForm = $('plugin-config-form');
    if (configClose && !configClose.dataset.bound) {
        configClose.dataset.bound = '1';
        configClose.addEventListener('click', closePluginConfiguration);
        configCancel?.addEventListener('click', closePluginConfiguration);
        configForm?.addEventListener('submit', savePluginConfiguration);
    }
}

function closePluginConfiguration() {
    configuringPluginId = null;
    $('plugin-config-modal')?.classList.remove('open');
    $('plugin-config-modal')?.setAttribute('aria-hidden', 'true');
}

async function openPluginConfiguration(pluginId) {
    try {
        const response = await fetch(`${API}/plugins/${encodeURIComponent(pluginId)}/configuration`, {cache: 'no-store'});
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
        configuringPluginId = pluginId;
        $('plugin-config-title').textContent = payload.title || 'Configure plugin';
        $('plugin-config-help').textContent = payload.help || '';
        $('plugin-config-fields').innerHTML = (payload.fields || []).map(field => `<div class="plugin-config-field">
            <label for="plugin-field-${escapeHtml(field.name)}">${escapeHtml(field.label)}${field.required ? ' *' : ''}</label>
            <input class="intel-input plugin-config-input" id="plugin-field-${escapeHtml(field.name)}" data-name="${escapeHtml(field.name)}" type="${field.secret ? 'password' : 'text'}" value="${field.secret ? '' : escapeHtml(field.value || '')}" placeholder="${field.secret && field.configured ? 'Saved — leave blank to keep it' : ''}" ${field.required && !field.configured ? 'required' : ''} autocomplete="off">
            ${field.secret && field.configured ? '<small>A value is already saved locally.</small>' : ''}
        </div>`).join('');
        $('plugin-config-modal').classList.add('open');
        $('plugin-config-modal').setAttribute('aria-hidden', 'false');
        $('plugin-config-fields').querySelector('input')?.focus();
    } catch (error) {
        showToast(error.message || 'Could not open plugin configuration.');
    }
}

async function savePluginConfiguration(event) {
    event.preventDefault();
    if (!configuringPluginId) return;
    const button = $('plugin-config-save');
    const values = {};
    $('plugin-config-fields').querySelectorAll('.plugin-config-input').forEach(input => { values[input.dataset.name] = input.value; });
    button.disabled = true;
    button.textContent = 'Saving...';
    try {
        const response = await fetch(`${API}/plugins/${encodeURIComponent(configuringPluginId)}/configuration`, {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({values}),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
        const pluginName = payload.plugin?.name || 'Plugin';
        closePluginConfiguration();
        showToast(`${pluginName} configuration saved locally.`);
        await loadPlugins();
    } catch (error) {
        showToast(error.message || 'Could not save plugin configuration.');
    } finally {
        button.disabled = false;
        button.textContent = 'Save configuration';
    }
}

async function installStorePlugin(pluginId, button) {
    button.disabled = true;
    button.textContent = 'Installing...';
    try {
        const response = await fetch(`${API}/plugins/store/${encodeURIComponent(pluginId)}/install`, { method: 'POST' });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
        showToast(`${payload.name || 'Plugin'} installed. It is now available to Work Mode.`);
        await loadPlugins();
        await loadPluginStore();
    } catch (error) {
        showToast(error.message || 'Plugin installation failed.');
        button.disabled = false;
        button.textContent = 'Install';
    }
}

async function installPluginManifest() {
    const input = $('plugin-manifest-url');
    const button = $('plugin-manifest-install');
    const url = input?.value.trim() || '';
    if (!url.startsWith('https://')) { showToast('Enter an HTTPS plugin manifest URL.'); return; }
    button.disabled = true;
    try {
        const response = await fetch(`${API}/plugins/store/install-manifest`, {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url}),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
        input.value = '';
        showToast(`${payload.name || 'External plugin'} installed safely.`);
        await loadPlugins();
        await loadPluginStore();
    } catch (error) {
        showToast(error.message || 'External plugin installation failed.');
    } finally {
        button.disabled = false;
    }
}

function renderPluginStore(query = '') {
    const list = $('plugin-list');
    if (!list) return;
    const needle = query.trim().toLowerCase();
    const plugins = pluginStoreCache.filter(plugin => !needle || `${plugin.name} ${plugin.description}`.toLowerCase().includes(needle));
    list.innerHTML = plugins.map(plugin => `<div class="intel-card plugin-card">
        <div class="intel-card-header"><span class="intel-card-title">${escapeHtml(plugin.name)}</span><span class="intel-badge ${plugin.installed ? 'state-healthy' : 'state-warning'}">${plugin.installed ? 'Installed' : 'Available'}</span></div>
        <div class="intel-card-meta">${escapeHtml(plugin.description || '')}</div>
        <div class="plugin-permissions"><span>✓ Manifest-only installation</span><span>✓ External changes still require confirmation</span></div>
        <div class="plugin-actions"><a class="intel-btn secondary plugin-website-link" href="${escapeAttr(plugin.homepage || '#')}" target="_blank" rel="noopener">Website</a>${plugin.installed ? '' : `<button class="intel-btn plugin-store-install" data-plugin="${escapeHtml(plugin.id)}">Install</button>`}</div>
    </div>`).join('') || '<div class="intel-empty">No matching store plugins.</div>';
    list.querySelectorAll('.plugin-store-install').forEach(button => button.addEventListener('click', () => installStorePlugin(button.dataset.plugin, button)));
}

function renderPlugins(query = '') {
    const list = $('plugin-list');
    if (!list) return;
    const needle = query.trim().toLowerCase();
    const plugins = pluginCache.filter(plugin => !needle || `${plugin.name} ${plugin.description}`.toLowerCase().includes(needle));
    list.innerHTML = plugins.map(plugin => {
        const status = plugin.connected ? (plugin.enabled ? 'Enabled' : 'Disabled') : (plugin.connect_url ? 'Ready to connect' : (plugin.configurable ? 'Setup needed' : 'Unavailable'));
        const configure = plugin.configurable ? `<button class="intel-btn secondary plugin-configure" data-plugin="${escapeHtml(plugin.id)}">Configure</button>` : '';
        const connect = !plugin.connected && plugin.connect_url ? `<button class="intel-btn plugin-connect" data-url="${escapeHtml(plugin.connect_url)}">Connect</button>` : '';
        const toggle = plugin.connected ? `<label class="toggle-switch"><input class="plugin-enable" data-plugin="${escapeHtml(plugin.id)}" type="checkbox" ${plugin.enabled ? 'checked' : ''}><span class="toggle-slider"></span></label>` : '';
        const action = `${configure}${connect}${toggle}`;
        return `<div class="intel-card plugin-card">
            <div class="intel-card-header"><span class="intel-card-title">${escapeHtml(plugin.name)}</span><span class="intel-badge ${plugin.connected ? 'state-healthy' : 'state-warning'}">${status}</span></div>
            <div class="intel-card-meta">${escapeHtml(plugin.description || '')}</div>
            <div class="plugin-permissions">${(plugin.permissions || []).map(p => `<span>✓ ${escapeHtml(p)}</span>`).join('')}</div>
            <div class="plugin-actions">${action}</div>
        </div>`;
    }).join('') || '<div class="intel-empty">No matching plugins.</div>';
    list.querySelectorAll('.plugin-connect').forEach(button => button.addEventListener('click', () => {
        window.open(`${API}${button.dataset.url}`, 'edith-google-oauth', 'width=600,height=760');
    }));
    list.querySelectorAll('.plugin-configure').forEach(button => button.addEventListener('click', () => openPluginConfiguration(button.dataset.plugin)));
    list.querySelectorAll('.plugin-enable').forEach(input => input.addEventListener('change', async () => {
        await fetch(`${API}/plugins/${encodeURIComponent(input.dataset.plugin)}`, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({enabled: input.checked})});
        await loadPlugins();
    }));
}

function newChat() {
    if (ttsPlayer) ttsPlayer.stop();
    if (camStream) stopCamera();
    clearPendingUpload();
    sessionId = null;
    if (chatMessages) chatMessages.innerHTML = '';
    resetHomeworkBoard();
    chatMessages.appendChild(createWelcome());
    messageInput.value = '';
    autoResizeInput();
    setGreeting();
    if (searchResultsWidget) searchResultsWidget.classList.remove('open');
    if (searchResultsToggle) searchResultsToggle.style.display = 'none';
    if (activityPanel) activityPanel.classList.remove('open');
    if (settingsPanel) settingsPanel.classList.remove('open');
    if (activityToggle) activityToggle.style.display = 'none';
    if (activityList) {
        activityList.innerHTML = '<div class="activity-empty" id="activity-empty">Send a message to see the flow here.</div>';
    }
    updatePanelOverlay();
}

function welcomeActionsForMode() {
    if (currentMode === 'research') return [];
    if (currentMode === 'work') {
        return [
            ['Create sample PPT', 'Create a polished sample five-slide PowerPoint presentation about modern AI.'],
            ['Create sample Excel', 'Create a formatted sample Excel sales tracker with formulas and a chart.'],
            ['Create sample PDF', 'Create a polished one-page sample PDF report about AI productivity.'],
            ['Create sample document', 'Create a professional sample Word document about workplace automation.'],
        ];
    }
    return [
        ['What can you do?', 'What can you do?'],
        ['Open YouTube', 'Open YouTube for me'],
        ['Fun fact', 'Tell me a fun fact'],
        ['Play music', 'Play some music'],
    ];
}

function createWelcome() {
    const g = indiaGreeting();
    const hour = indiaHour();
    const actions = welcomeActionsForMode();
    const chips = actions.length
        ? `<div class="welcome-chips">${actions.map(([label, message]) => `<button class="chip" data-msg="${escapeHtml(message)}">${escapeHtml(label)}</button>`).join('')}</div>`
        : '';
    const div = document.createElement('div');
    div.className = 'welcome-screen';
    div.id = 'welcome-screen';
    div.innerHTML = `
        <div class="welcome-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
        </div>
        <h2 class="welcome-title" id="welcome-title" data-india-hour="${hour}" data-time-zone="Asia/Kolkata">${g}</h2>
        <p class="welcome-sub">How may I assist you today?</p>
        ${chips}`;
    div.querySelectorAll('.chip').forEach(c => {
        c.addEventListener('click', () => { if (!isStreaming) sendMessage(c.dataset.msg); });
    });
    return div;
}

function refreshWelcomeForMode() {
    const current = document.getElementById('welcome-screen');
    if (!current) return;
    current.replaceWith(createWelcome());
}

function isUrlLike(str) {
    if (!str || typeof str !== 'string') return false;
    const s = str.trim();
    return s.length > 40 && (/^https?:\/\//i.test(s));
}

function friendlyUrlLabel(url) {
    if (!url || typeof url !== 'string') return 'View source';
    try {
        const u = new URL(url.startsWith('http') ? url : 'https://' + url);
        const host = u.hostname.replace(/^www\./, '');
        const path = u.pathname !== '/' ? u.pathname.slice(0, 20) + (u.pathname.length > 20 ? '…' : '') : '';
        return path ? host + path : host;
    } catch (_) {
        return url.length > 40 ? url.slice(0, 37) + '…' : url;
    }
}

function truncateSnippet(text, maxLen) {
    if (!text || typeof text !== 'string') return '';
    const t = text.trim();
    if (t.length <= maxLen) return t;
    return t.slice(0, maxLen).trim() + '…';
}

function renderSearchResults(payload) {
    if (!payload) return;
    if (searchResultsQuery) searchResultsQuery.textContent = (payload.query || '').trim() || 'Search';
    if (searchResultsAnswer) searchResultsAnswer.textContent = (payload.answer || '').trim() || '';
    if (!searchResultsList) return;
    searchResultsList.innerHTML = '';
    const results = payload.results || [];
    const maxContentLen = 220;
    for (const r of results) {
        let title = (r.title || '').trim();
        let content = (r.content || '').trim();
        const url = (r.url || '').trim();
        if (isUrlLike(title)) title = friendlyUrlLabel(url) || 'Source';
        if (!title) title = friendlyUrlLabel(url) || 'Source';
        if (isUrlLike(content)) content = '';
        content = truncateSnippet(content, maxContentLen);
        const score = r.score != null ? Math.round((r.score || 0) * 100) : null;
        const card = document.createElement('div');
        card.className = 'search-result-card';
        const urlDisplay = url ? escapeHtml(friendlyUrlLabel(url)) : '';
        const hrefSafe = safeUrlForHref(url);
        const urlMarkup = urlDisplay
            ? (hrefSafe ? `<a href="${escapeAttr(hrefSafe)}" target="_blank" rel="noopener" class="card-url" title="${escapeAttr(url)}">${urlDisplay}</a>` : `<span class="card-url">${urlDisplay}</span>`)
            : '';
        card.innerHTML = `
            <div class="card-title">${escapeHtml(title)}</div>
            ${content ? `<div class="card-content">${escapeHtml(content)}</div>` : ''}
            ${urlMarkup}
            ${score != null ? `<div class="card-score">Relevance: ${escapeHtml(String(score))}%</div>` : ''}`;
        searchResultsList.appendChild(card);
    }
}

function safeUrlForHref(url) {
    if (!url || typeof url !== 'string') return '';
    const u = url.trim();
    try {
        const parsed = new URL(u);
        return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.href : '';
    } catch (_) {
        return '';
    }
}

function escapeAttr(str) {
    if (typeof str !== 'string') return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

const ACTIVITY_STEPS = {
    query_detected:      { step: 1, label: 'Query detected' },
    decision:            { step: 2, label: 'Primary Brain' },
    intent_classified:   { step: 3, label: 'Task Brain' },
    routing:             { step: 4, label: 'Route selected' },
    tasks_executing:     { step: 0, label: 'Executing tasks' },
    tasks_completed:     { step: 0, label: 'Tasks completed' },
    actions_emitted:     { step: 0, label: 'Actions sent' },
    vision_analyzing:    { step: 0, label: 'Analyzing image' },
    streaming_started:   { step: 5, label: 'Streaming response' },
    extracting_query:    { step: 0, label: 'Extracting query' },
    searching_web:       { step: 0, label: 'Searching web' },
    search_completed:    { step: 0, label: 'Search completed' },
    context_retrieved:   { step: 0, label: 'Context retrieved' },
    background_dispatched: { step: 0, label: 'Background tasks' },
    scrape_triggered:    { step: 0, label: 'Web reader' },
    scrape_self_healing: { step: 0, label: 'Self-healing' },
    scrape_completed:    { step: 0, label: 'Scrape result' },
    watchlist_updated:   { step: 0, label: 'Watchlist' },
    scan_started:        { step: 0, label: 'Scan started' },
    scan_completed:      { step: 0, label: 'Scan completed' },
    mission_started:     { step: 0, label: 'Research mission' },
    research_route:      { step: 2, label: 'Research route' },
    snap_queued:         { step: 3, label: 'Snap queue' },
    screen_scan:         { step: 4, label: 'Screen scan' },
    web_research:        { step: 5, label: 'Web research' },
    sources_read:        { step: 6, label: 'Documents and sources' },
    reasoning:           { step: 7, label: 'Reasoning model' },
    batch_solved:        { step: 8, label: 'Batch solved' },
    first_chunk:         { step: 6, label: 'Core responded' },
    model_selected:      { step: 2, label: 'Model selected' },
    context_compacted:   { step: 2, label: 'Context compacted' },
};

function appendActivity(activity) {
    if (!activityList || !activity) return;
    const item = document.createElement('div');
    item.className = 'activity-item';
    item.setAttribute('data-event', activity.event || '');
    const stepInfo = ACTIVITY_STEPS[activity.event] || { step: 0, label: activity.event || 'Activity', icon: 'dot' };
    let detail = '';
    const addRouteClass = (route) => {
        if (route === 'general') item.classList.add('route-general');
        else if (route === 'realtime') item.classList.add('route-realtime');
        else if (route === 'vision' || route === 'camera') item.classList.add('route-vision');
        else if (route === 'task') item.classList.add('route-task');
        else if (route === 'mixed') item.classList.add('route-task');
        else if (route === 'chat') item.classList.add('route-chat');
        else if (route === 'research' || route === 'homework') item.classList.add('route-research');
    };
    if (activity.event === 'query_detected') {
        detail = activity.message || '';
    } else if (activity.event === 'decision') {
        const ms = activity.elapsed_ms;
        const timing = ms != null ? ` (${ms < 1000 ? ms + ' ms' : (ms / 1000).toFixed(2) + ' s'})` : '';
        const cat = (activity.query_type || '?').charAt(0).toUpperCase() + (activity.query_type || '').slice(1);
        detail = `${cat} — ${activity.reasoning || ''}${timing}`;
        addRouteClass(activity.query_type);
    } else if (activity.event === 'intent_classified') {
        detail = (activity.intent || '?').charAt(0).toUpperCase() + (activity.intent || '').slice(1);
        item.classList.add('activity-sub', 'route-task');
    } else if (activity.event === 'routing') {
        detail = `→ ${(activity.route || '?').charAt(0).toUpperCase() + (activity.route || '').slice(1)}`;
        addRouteClass(activity.route);
    } else if (activity.event === 'tasks_executing') {
        detail = activity.message || 'Running tasks...';
        item.classList.add('activity-sub', 'route-task');
    } else if (activity.event === 'tasks_completed') {
        detail = activity.message || 'Completed';
        item.classList.add('activity-sub', 'route-task');
    } else if (activity.event === 'actions_emitted') {
        detail = activity.message || 'Actions sent';
        item.classList.add('activity-sub');
    } else if (activity.event === 'vision_analyzing') {
        detail = activity.message || 'Analyzing image...';
        item.classList.add('activity-sub', 'route-vision');
    } else if (activity.event === 'streaming_started') {
        detail = `Generating via ${(activity.route || '?').charAt(0).toUpperCase() + (activity.route || '').slice(1)}`;
        addRouteClass(activity.route);
    } else if (activity.event === 'first_chunk') {
        const ms = activity.elapsed_ms;
        detail = ms != null ? `Core responded in ${ms < 1000 ? ms + ' ms' : (ms / 1000).toFixed(2) + ' s'}` : 'Response started';
        addRouteClass(activity.route);
    } else if (activity.event === 'model_selected') {
        detail = activity.message || 'Current model';
        item.classList.add('activity-sub');
    } else if (activity.event === 'extracting_query') {
        detail = activity.message || 'Parsing your question for search...';
        item.classList.add('activity-sub');
    } else if (activity.event === 'searching_web') {
        detail = activity.message || (activity.query ? `Query: "${activity.query}"` : 'Scanning Pulse...');
        item.classList.add('activity-sub', 'route-realtime');
    } else if (activity.event === 'search_completed') {
        detail = activity.message || 'Search completed';
        item.classList.add('activity-sub', 'route-realtime');
    } else if (activity.event === 'context_retrieved') {
        detail = activity.message || 'Knowledge base ready';
        item.classList.add('activity-sub', 'route-general');
    } else if (activity.event === 'scrape_triggered') {
        detail = activity.message || 'Reading the webpage...';
        item.classList.add('activity-sub', 'route-realtime');
    } else if (activity.event === 'scrape_self_healing') {
        detail = activity.message || 'Trying another webpage-reading method...';
        item.classList.add('activity-sub', 'route-vision');
    } else if (activity.event === 'scrape_completed') {
        detail = activity.message || 'Done';
        item.classList.add('activity-sub', 'route-realtime');
    } else if (activity.event === 'watchlist_updated' || activity.event === 'scan_started' ||
               activity.event === 'scan_completed' || activity.event === 'mission_started') {
        detail = activity.message || '';
        item.classList.add('activity-sub', 'route-realtime');
    } else {
        detail = activity.message || (typeof activity === 'object' ? JSON.stringify(activity) : String(activity));
        addRouteClass(activity.route);
        if (activity.event?.startsWith('research') || ['snap_queued', 'screen_scan', 'web_research', 'sources_read', 'reasoning', 'batch_solved', 'solution_repaired'].includes(activity.event)) {
            item.classList.add('activity-sub');
        }
    }
    const stepNum = stepInfo.step ? `<span class="activity-step">${stepInfo.step}</span>` : '';
    item.innerHTML = `
        <div class="activity-event">${stepNum}${escapeHtml(stepInfo.label)}</div>
        <div class="activity-detail">${escapeHtml(detail || '')}</div>`;
    const emptyEl = activityList.querySelector('.activity-empty');
    if (emptyEl) emptyEl.style.display = 'none';
    activityList.appendChild(item);
    activityList.scrollTop = activityList.scrollHeight;
}

function escapeHtml(str) {
    if (typeof str !== 'string') return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function hideWelcome() {
    const w = document.getElementById('welcome-screen');
    if (w) w.remove();
}

const AVATAR_ICON_USER = '<svg class="msg-avatar-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>';
const AVATAR_ICON_ASSISTANT = '<img class="msg-avatar-icon spider-mask-avatar" src="spider-mask-avatar.svg?v=20260823-2" alt="Spider-Man mask">';

function addMessage(role, text, imageDataUrl = '') {
    hideWelcome();
    const msg = document.createElement('div');
    msg.className = `message ${role}`;
    const avatar = document.createElement('div');
    avatar.className = 'msg-avatar';
    avatar.innerHTML = role === 'assistant' ? AVATAR_ICON_ASSISTANT : AVATAR_ICON_USER;
    const body = document.createElement('div');
    body.className = 'msg-body';
    const label = document.createElement('div');
    label.className = 'msg-label';
    label.textContent = role === 'assistant'
        ? `Edith  (${currentMode === 'research' ? (currentResearchBranch === 'homework' ? 'Homework' : 'Research') : currentMode === 'work' ? 'Work' : 'General'})`
        : 'You';
    const content = document.createElement('div');
    content.className = 'msg-content';
    if (role === 'assistant' && text) content.innerHTML = formatAssistantMarkdown(text, true);
    else content.textContent = text;
    if (role === 'user' && imageDataUrl) {
        const attachment = document.createElement('img');
        attachment.className = 'msg-upload-image';
        attachment.src = imageDataUrl;
        attachment.alt = 'Image attached to this message';
        content.appendChild(attachment);
    }
    body.appendChild(label);
    body.appendChild(content);
    msg.appendChild(avatar);
    msg.appendChild(body);
    chatMessages.appendChild(msg);
    scrollToBottom();
    return content;
}

function addTypingIndicator() {
    hideWelcome();
    const msg = document.createElement('div');
    msg.className = 'message assistant';
    msg.id = 'typing-msg';
    const avatar = document.createElement('div');
    avatar.className = 'msg-avatar';
    avatar.innerHTML = AVATAR_ICON_ASSISTANT;
    const body = document.createElement('div');
    body.className = 'msg-body';
    const label = document.createElement('div');
    label.className = 'msg-label';
    label.textContent = `Edith  (${currentMode === 'research' ? (currentResearchBranch === 'homework' ? 'Homework' : 'Research') : currentMode === 'work' ? 'Work' : 'General'})`;
    const content = document.createElement('div');
    content.className = 'msg-content';
    content.innerHTML = thinkingIndicatorMarkup();
    body.appendChild(label);
    body.appendChild(content);
    msg.appendChild(avatar);
    msg.appendChild(body);
    chatMessages.appendChild(msg);
    scrollToBottom();
    return content;
}

function removeTypingIndicator() {
    const t = document.getElementById('typing-msg');
    if (t) t.remove();
}

function finalizePendingAssistantIndicators() {
    removeTypingIndicator();
    document.querySelectorAll('.msg-content .edith-thinking').forEach(indicator => {
        const content = indicator.closest('.msg-content');
        indicator.remove();
        content?.querySelectorAll('.stream-progress').forEach(progress => progress.remove());
        const hasResult = !!content?.querySelector(
            '.msg-stream-text:not(.stream-placeholder), .browser-task-list, .bg-task-card, .artifact-list, ' +
            '.harness-approval-card, .harness-question, .harness-auth-card, .harness-retry-card'
        );
        if (content && !hasResult && !content.textContent.trim()) content.closest('.message')?.remove();
    });
}

function setStreamingControls(active) {
    isStreaming = active;
    updateStopTaskVisibility();
    if (!sendBtn) return;
    sendBtn.disabled = false;
    sendBtn.classList.toggle('streaming-stop', active);
    sendBtn.title = active ? 'Stop current turn' : 'Send message';
    sendBtn.setAttribute('aria-label', active ? 'Stop current turn' : 'Send message');
    sendBtn.innerHTML = active
        ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>'
        : '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>';
}

function updateStopTaskVisibility() {
    if (stopTaskButton) stopTaskButton.hidden = !(isStreaming || autoResumeTimer || autoResumeCountdown);
}

function clearScheduledAutoResume(message = '') {
    if (autoResumeTimer) clearTimeout(autoResumeTimer);
    if (autoResumeCountdown) clearInterval(autoResumeCountdown);
    autoResumeTimer = null;
    autoResumeCountdown = null;
    if (message && autoResumeCard) {
        const status = autoResumeCard.querySelector('[data-retry-status]');
        if (status) status.textContent = message;
        autoResumeCard.classList.add('cancelled');
    }
    autoResumeCard = null;
    updateStopTaskVisibility();
}

function isRateLimitMessage(value) {
    const text = String(value || '').toLowerCase();
    return text.includes('429') || text.includes('rate limit');
}

function scheduleHarnessAutoResume(details, container, delayOverride = null) {
    clearScheduledAutoResume();
    autoResumeAttempt += 1;
    const seconds = Math.max(5, Math.min(300, Number(delayOverride ?? details?.after_seconds ?? 60) || 60));
    let remaining = seconds;
    const card = document.createElement('div');
    card.className = 'harness-retry-card';
    card.innerHTML = '<strong>Rate limit pause</strong><span data-retry-status></span><small>The task will continue from its saved TrueForge session. Completed write actions will not be auto-approved.</small>';
    container.appendChild(card);
    autoResumeCard = card;
    const status = card.querySelector('[data-retry-status]');
    const renderCountdown = () => { status.textContent = `Automatically retrying in ${remaining}s…`; };
    renderCountdown();
    autoResumeCountdown = setInterval(() => {
        remaining -= 1;
        renderCountdown();
    }, 1000);
    autoResumeTimer = setTimeout(async () => {
        clearInterval(autoResumeCountdown);
        autoResumeCountdown = null;
        autoResumeTimer = null;
        updateStopTaskVisibility();
        status.textContent = 'Retrying now…';
        try {
            await streamHarnessContinuation('retry-rate-limit', {
                profile: details?.profile || activeHarnessProfile,
            });
            if (autoResumeTimer || autoResumeCountdown) {
                status.textContent = 'The limit is still active. A new retry is scheduled.';
            } else {
                status.textContent = 'Task resumed.';
                card.classList.add('resumed');
                autoResumeAttempt = 0;
            }
        } catch (error) {
            if (!userCancelledTurn && isRateLimitMessage(error?.message) && autoResumeAttempt < 4) {
                status.textContent = 'The limit is still active. Waiting again…';
                scheduleHarnessAutoResume(details, container, Math.min(seconds * 2, 300));
            } else if (!userCancelledTurn) {
                status.textContent = error?.message || 'Automatic resume failed.';
                card.classList.add('failed');
            }
        }
    }, seconds * 1000);
    updateStopTaskVisibility();
}

async function cancelActiveHarnessTurn() {
    if (!isStreaming && !autoResumeTimer && !autoResumeCountdown) return;
    userCancelledTurn = true;
    clearScheduledAutoResume('Automatic retry cancelled.');
    finalizePendingAssistantIndicators();
    setStreamingControls(false);
    if (messageInput) messageInput.disabled = false;
    if (orbContainer) orbContainer.classList.remove('active');
    if (activeTurnController) activeTurnController.abort();
    if (sessionId) {
        try {
            await fetch(`${API}/chat/sessions/${encodeURIComponent(sessionId)}/cancel-turn`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ profile: activeHarnessProfile }),
            });
        } catch (_) {}
    }
    showToast('Turn cancelled.');
}

async function submitHarnessApproval(call, allow, card) {
    card.querySelectorAll('button').forEach(button => { button.disabled = true; });
    try {
        await streamHarnessContinuation('approval', {
                profile: activeHarnessProfile,
                tool_call_id: call.tool_call_id,
                thread_id: call.thread_id || 'main',
                allow,
                reason: allow ? '' : 'Denied by user',
            }, allow ? 'Approved. The agent continued the task.' : 'Denied. No gated action was executed.');
        card.classList.add(allow ? 'approved' : 'denied');
    } catch (error) {
        showToast(error.message || 'Could not resume the turn.');
        card.querySelectorAll('button').forEach(button => { button.disabled = false; });
    }
}

async function streamHarnessContinuation(endpoint, payload, fallbackText = '') {
    const responseEl = addMessage('assistant', '');
    responseEl.innerHTML = thinkingIndicatorMarkup('Continuing the task');
    let output = '';
    let hasHarnessPrompt = false;
    const controller = new AbortController();
    userCancelledTurn = false;
    activeTurnController = controller;
    setStreamingControls(true);
    if (messageInput) messageInput.disabled = true;
    try {
        const res = await fetch(`${API}/trueforge/sessions/${encodeURIComponent(sessionId)}/${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            signal: controller.signal,
        });
        if (!res.ok || !res.body) throw new Error(`Could not continue (HTTP ${res.status})`);
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const records = buffer.split('\n\n');
            buffer = records.pop();
            for (const record of records) {
                if (!record.startsWith('data: ')) continue;
                const data = JSON.parse(record.slice(6));
                if (data.error) throw new Error(data.error);
                if ('chunk' in data) {
                    output += data.chunk || '';
                    revealStreamingText(responseEl, output);
                }
                if (data.activity) appendActivity(data.activity);
                if (data.artifacts) renderArtifacts(data.artifacts, responseEl);
                if (data.approval) { hasHarnessPrompt = true; renderHarnessApproval(data.approval, responseEl); }
                if (data.question) { hasHarnessPrompt = true; renderHarnessQuestion(data.question, responseEl); }
                if (data.auth_required) { hasHarnessPrompt = true; renderHarnessAuth(data.auth_required, responseEl); }
                if (data.auto_resume) {
                    hasHarnessPrompt = true;
                    scheduleHarnessAutoResume(data.auto_resume, responseEl);
                }
            }
        }
        if (output) revealStreamingText(responseEl, output, true);
        else if (hasHarnessPrompt) responseEl.querySelector('.edith-thinking')?.remove();
        else if (fallbackText) revealStreamingText(responseEl, fallbackText, true);
        else responseEl.querySelector('.edith-thinking')?.remove();
        return responseEl;
    } finally {
        if (activeTurnController === controller) activeTurnController = null;
        setStreamingControls(false);
        if (messageInput) messageInput.disabled = false;
    }
}

function renderHarnessApproval(approval, container) {
    for (const call of approval.calls || []) {
        const card = document.createElement('div');
        card.className = 'harness-approval-card';
        const title = document.createElement('strong');
        const summary = call.summary || {};
        title.textContent = `Approval required · ${summary.label || call.tool_name || 'tool'}`;
        const readable = document.createElement('div');
        readable.className = 'harness-approval-summary';
        for (const item of summary.items || []) {
            const row = document.createElement('div');
            row.className = 'harness-approval-meta';
            const label = document.createElement('span');
            label.textContent = `${item.label}:`;
            const value = document.createElement('b');
            value.textContent = item.value;
            row.append(label, value);
            readable.appendChild(row);
        }
        if (summary.preview) {
            const preview = document.createElement('p');
            preview.textContent = summary.preview;
            readable.appendChild(preview);
        }
        const details = document.createElement('details');
        details.className = 'harness-approval-details';
        const detailsTitle = document.createElement('summary');
        detailsTitle.textContent = 'Technical details';
        const args = document.createElement('pre');
        args.textContent = typeof call.arguments === 'string' ? call.arguments : JSON.stringify(call.arguments, null, 2);
        details.append(detailsTitle, args);
        const controls = document.createElement('div');
        controls.className = 'harness-approval-actions';
        const deny = document.createElement('button');
        deny.type = 'button';
        deny.textContent = 'Deny';
        const allow = document.createElement('button');
        allow.type = 'button';
        allow.className = 'primary';
        allow.textContent = 'Allow once';
        deny.addEventListener('click', () => submitHarnessApproval(call, false, card));
        allow.addEventListener('click', () => submitHarnessApproval(call, true, card));
        controls.append(deny, allow);
        card.append(title);
        if (readable.childElementCount) card.append(readable);
        card.append(details, controls);
        container.appendChild(card);
    }
}

function renderHarnessAuth(servers, container) {
    for (const server of servers || []) {
        const url = server.auth_url || server.authUrl;
        if (!url) continue;
        const card = document.createElement('div');
        card.className = 'harness-auth-card';
        const link = document.createElement('a');
        link.className = 'harness-auth-link';
        link.href = url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.textContent = `Connect ${server.name || 'service'} to continue`;
        const resume = document.createElement('button');
        resume.type = 'button';
        resume.textContent = 'I connected it — continue';
        resume.addEventListener('click', async () => {
            resume.disabled = true;
            try {
                await streamHarnessContinuation('resume-auth', { profile: activeHarnessProfile }, 'Connection checked. The agent continued.');
                card.classList.add('connected');
            } catch (error) {
                showToast(error.message || 'Could not resume after sign-in.');
                resume.disabled = false;
            }
        });
        card.append(link, resume);
        container.appendChild(card);
    }
}

async function submitHarnessQuestion(question, content, card) {
    const answer = String(content || '').trim();
    if (!answer) return;
    const previousMarkup = card.innerHTML;
    card.querySelectorAll('button, input').forEach(control => { control.disabled = true; });
    card.classList.add('answering');
    card.innerHTML = `<strong>Selected: ${escapeHtml(answer)}</strong><small>Continuing…</small>`;
    try {
        await streamHarnessContinuation('response', {
            profile: activeHarnessProfile,
            tool_call_id: question.tool_call_id,
            thread_id: question.thread_id || 'main',
            content: answer,
        }, 'Answer received. The agent continued the task.');
        card.remove();
    } catch (error) {
        showToast(error.message || 'Could not submit the answer.');
        card.innerHTML = previousMarkup;
        renderHarnessQuestionControls(question, card);
        card.classList.remove('answering');
        card.querySelectorAll('button, input').forEach(control => { control.disabled = false; });
    }
}

function renderHarnessQuestionControls(question, card) {
    card.replaceChildren();
        const title = document.createElement('strong');
        title.textContent = question.question || 'The agent needs more information.';
        const controls = document.createElement('div');
        controls.className = 'harness-question-actions';
        for (const option of question.options || []) {
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = option;
            button.addEventListener('click', () => submitHarnessQuestion(question, option, card));
            controls.appendChild(button);
        }
        const input = document.createElement('input');
        input.type = 'text';
        input.placeholder = 'Type your answer…';
        const submit = document.createElement('button');
        submit.type = 'button';
        submit.className = 'primary';
        submit.textContent = 'Continue';
        submit.addEventListener('click', () => submitHarnessQuestion(question, input.value, card));
        input.addEventListener('keydown', event => {
            if (event.key === 'Enter') submitHarnessQuestion(question, input.value, card);
        });
        controls.append(input, submit);
        card.append(title, controls);
}

function renderHarnessQuestion(payload, container) {
    for (const question of payload.questions || []) {
        const card = document.createElement('div');
        card.className = 'harness-question';
        renderHarnessQuestionControls(question, card);
        container.appendChild(card);
    }
}

function scrollToBottom() {
    requestAnimationFrame(() => {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    });
}

async function sendMessage(textOverride) {
    let text = (textOverride || messageInput.value).trim();
    const uploadedImages = pendingUploadImages.length
        ? [...pendingUploadImages]
        : (pendingUploadBase64 ? [pendingUploadBase64] : []);
    const uploadedImage = pendingUploadBase64;
    const uploadedTexts = pendingTextUploads.map(item => ({ ...item }));
    const homeworkBoardIntent = /\b(?:solve|calculate|compute|evaluate|determine|derive|prove|work\s+out|answer\s+(?:this|these|the)\s+questions?|homework|quiz)\b/i.test(text);
    homeworkResponseTarget = currentMode === 'research' && currentResearchBranch === 'homework' &&
        (uploadedImages.length || uploadedTexts.length || homeworkBoardIntent) ? 'board' : 'chat';
    const visionModeOn = camVisionModeInput && camVisionModeInput.checked;
    const wantsCamera = !uploadedImage && (visionModeOn || isCameraQuery(text) || (camStream && text));
    const hasResearchUpload = currentMode === 'research' && (uploadedImages.length || uploadedTexts.length);
    if (hasResearchUpload && !text) {
        showResearchUploadChooser();
        return;
    }
    if (currentMode === 'research' && !hasResearchUpload && isInstructionlessResearchContent(text)) {
        showResearchUploadChooser('', text);
        return;
    }
    if (currentMode === 'research' && currentResearchBranch === 'homework' && isBareYouTubeUrl(text) && !textOverride) {
        showResearchUploadChooser(text);
        return;
    }
    if (uploadedImage && !text) {
        text = 'Analyze this image.';
    }
    if (wantsCamera && !text) text = 'What do you see?';
    if (!text || isStreaming) return;
    if (autoResumeTimer || autoResumeCountdown) {
        clearScheduledAutoResume('Superseded by your new task.');
        autoResumeAttempt = 0;
    }
    if (currentMode !== 'work' && !uploadedImage && !wantsCamera) prepareExternalWindow(text);
    if (isListening) {
        pendingSendTranscript = null;
        clearTimeout(speechSendTimeout);
        speechSendTimeout = null;
        stopListening();
    }
    if ((isCameraQuery(text) || visionModeOn) && !camStream) {
        try {
            await startCamera();
            await new Promise((resolve) => {
                if (!camVideo) { resolve(); return; }
                if (camVideo.readyState >= 2 && camVideo.videoWidth > 0) { resolve(); return; }
                const onReady = () => { camVideo.removeEventListener('loadeddata', onReady); clearTimeout(t); resolve(); };
                const t = setTimeout(() => { camVideo.removeEventListener('loadeddata', onReady); resolve(); }, 3000);
                camVideo.addEventListener('loadeddata', onReady);
            });
        } catch (_) {
        }
    }
    let imgBase64 = uploadedImage || null;
    if (!imgBase64 && camStream && wantsCamera) {
        imgBase64 = await captureFrameAsBase64Safe();
        if (!imgBase64) showToast('Camera frame not ready. Please try again.');
    }
    if (currentMode === 'research' && currentResearchBranch === 'homework' && imgBase64) {
        homeworkResponseTarget = 'board';
    }
    messageInput.value = '';
    autoResizeInput();
    charCount.textContent = '';
    addMessage('user', text, pendingUploadPreview || (uploadedImage && !uploadedImage.startsWith('data:') ? `data:image/jpeg;base64,${uploadedImage}` : ''));
    if (uploadedImage || uploadedTexts.length) clearPendingUpload();
    const typingContent = addTypingIndicator();
    if (homeworkResponseTarget === 'board') typingContent?.closest('.message')?.classList.add('homework-board-only-response');
    userCancelledTurn = false;
    setStreamingControls(true);
    if (messageInput) messageInput.disabled = true;
    if (orbContainer) orbContainer.classList.add('active');
    if (ttsPlayer) { ttsPlayer.reset(); ttsPlayer.unlock(); }
    const messageToSend = imgBase64 ? (text + ' ' + CAM_BYPASS_TOKEN) : text;
    const endpoint = '/chat/jarvis/stream';
    if (activityList) {
        activityList.innerHTML = '<div class="activity-empty" id="activity-empty">Processing...</div>';
        if (activityToggle) activityToggle.style.display = '';
        if (activityPanel && shouldAutoOpenActivity()) { activityPanel.classList.add('open'); updatePanelOverlay(); }
    }
    let firstChunkReceived = false;
    let timeoutId = null;
    const controller = new AbortController();
    activeTurnController = controller;
    try {
        if (ttsPlayer?.enabled && settings.thinkingSounds && preStarterPlayer) {
            preStarterPlayer.play(() => {});
        }
        timeoutId = setTimeout(() => controller.abort(), 300000);
        const res = await fetch(`${API}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: messageToSend,
                session_id: sessionId,
                tts: !!(ttsPlayer && ttsPlayer.enabled),
                imgbase64: imgBase64 || null,
                imgbase64s: currentMode === 'research' || currentMode === 'work' ? uploadedImages : [],
                text_attachments: currentMode === 'research' ? uploadedTexts : [],
                mode: currentMode,
                research_branch: currentResearchBranch,
                homework_output: homeworkResponseTarget,
                auto_approve_safe_work: settings.autoApproveSafeWork,
                model_preference: chatModelSelector?.value || 'auto'
            }),
            signal: controller.signal,
        });
        if (!res.ok) {
            let errMsg = `HTTP ${res.status}`;
            try {
                const err = await res.json();
                errMsg = err.detail || (Array.isArray(err.detail) ? err.detail.map(d => d.msg || d.loc?.join('.')).join('; ') : err.message) || errMsg;
            } catch (_) {}
            throw new Error(errMsg);
        }
        removeTypingIndicator();
        const contentEl = addMessage('assistant', '');
        if (homeworkResponseTarget === 'board') contentEl?.closest('.message')?.classList.add('homework-board-only-response');
        contentEl.innerHTML = thinkingIndicatorMarkup();
        scrollToBottom();
        if (!res.body) throw new Error('No response body');
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let sseBuffer = '';
        let fullResponse = '';
        let hasHarnessPrompt = false;
        let streamDone = false;
        while (!streamDone) {
            const { done, value } = await reader.read();
            if (done) break;
            sseBuffer += decoder.decode(value, { stream: true });
            const lines = sseBuffer.split('\n\n');
            sseBuffer = lines.pop();
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.session_id) sessionId = data.session_id;
                    if (data.activity) {
                        if (data.activity.route === 'trueforge' && data.activity.profile) activeHarnessProfile = data.activity.profile;
                        updateThinkingState(contentEl, data.activity);
                        appendActivity(data.activity);
                        if (activityToggle) activityToggle.style.display = '';
                        if (activityPanel && shouldAutoOpenActivity()) { activityPanel.classList.add('open'); updatePanelOverlay(); }
                    }
                    if (data.search_results) {
                        renderSearchResults(data.search_results);
                        if (searchResultsToggle) searchResultsToggle.style.display = '';
                        if (searchResultsWidget && settings.autoOpenSearchResults) { searchResultsWidget.classList.add('open'); updatePanelOverlay(); }
                    }
                    if (data.actions) {
                        handleActions(data.actions, contentEl);
                    }
                    if (data.background_tasks) {
                        handleBackgroundTasks(data.background_tasks, contentEl);
                    }
                    if (data.artifacts) {
                        renderArtifacts(data.artifacts, contentEl);
                        if (researchFilesPanel?.classList.contains('open')) loadResearchFiles();
                    }
                    if (data.approval) { hasHarnessPrompt = true; renderHarnessApproval(data.approval, contentEl); }
                    if (data.auth_required) { hasHarnessPrompt = true; renderHarnessAuth(data.auth_required, contentEl); }
                    if (data.question) { hasHarnessPrompt = true; renderHarnessQuestion(data.question, contentEl); }
                    if (data.auto_resume) {
                        hasHarnessPrompt = true;
                        scheduleHarnessAutoResume(data.auto_resume, contentEl);
                    }
                    if ('chunk' in data) {
                        const chunkText = data.chunk || '';
                        if (chunkText && !firstChunkReceived) {
                            firstChunkReceived = true;
                            if (ttsPlayer) ttsPlayer.reset();
                        }
                        fullResponse += chunkText;
                        revealStreamingText(contentEl, fullResponse);
                        scrollToBottom();
                    }
                    if (data.audio && ttsPlayer) {
                        if (preStarterPlayer) preStarterPlayer.stop();
                        ttsPlayer.enqueue(data.audio);
                    }
                    if (data.error) throw new Error(data.error);
                    if (data.done) { streamDone = true; break; }
                } catch (parseErr) {
                    if (parseErr.message && !parseErr.message.includes('JSON'))
                        throw parseErr;
                }
            }
            if (streamDone) break;
        }
        if (fullResponse) revealStreamingText(contentEl, fullResponse, true);
        if (!fullResponse && hasHarnessPrompt) contentEl.querySelector('.edith-thinking')?.remove();
        else if (!fullResponse) revealStreamingText(contentEl, '(No response)', true);
        if (currentMode === 'research') loadResearchSources();
    } catch (err) {
        clearTimeout(timeoutId);
        removeTypingIndicator();
        let msg = 'Something went wrong. Please try again.';
        if (err.name === 'AbortError') {
            msg = userCancelledTurn ? 'Turn cancelled.' : 'Request timed out. Please try again.';
        } else if (err.message && err.message.includes('503')) {
            msg = 'Service temporarily unavailable. Please try again in a moment.';
        } else if (err.message && err.message.includes('429')) {
            msg = 'Rate limit reached. Please wait a moment before trying again.';
        } else if (err.message && err.message.length > 0) {
            msg = err.message.length > 100 ? err.message.slice(0, 97) + '...' : err.message;
        }
        addMessage('assistant', msg);
        showToast(msg, 6000);
    } finally {
        clearTimeout(timeoutId);
        finalizePendingAssistantIndicators();
        releaseUnusedExternalWindow();
        activeTurnController = null;
        setStreamingControls(false);
        if (messageInput) messageInput.disabled = false;
        if (orbContainer) orbContainer.classList.remove('active');
        homeworkResponseTarget = 'chat';
        maybeRestartListening();
    }
}

document.addEventListener('DOMContentLoaded', init);
