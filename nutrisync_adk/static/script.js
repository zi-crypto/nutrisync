// NutriSync Chat Application
// Implements the Premium Glassmorphism UI logic and State Management

// Configure marked.js to open links in a new tab
if (typeof marked !== 'undefined') {
    const renderer = new marked.Renderer();
    const linkRenderer = renderer.link;
    renderer.link = (href, title, text) => {
        const html = linkRenderer.call(renderer, href, title, text);
        return html.replace(/^<a /, '<a target="_blank" rel="noopener noreferrer" ');
    };
    marked.setOptions({ renderer: renderer });
}

class ChatCache {
    constructor(userId) {
        this.userId = userId;
        this.dbName = `NutriSyncDB_${userId}`; // Scope DB by User ID
        this.storeName = 'chat_history';
        this.db = null;
    }

    async open() {
        if (!this.userId) return; // Cannot open without user ID
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(this.dbName, 1);

            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                if (!db.objectStoreNames.contains(this.storeName)) {
                    const store = db.createObjectStore(this.storeName, { keyPath: 'id' });
                    store.createIndex('created_at', 'created_at', { unique: false });
                }
            };

            request.onsuccess = (event) => {
                this.db = event.target.result;
                resolve(this.db);
            };

            request.onerror = (event) => {
                reject('IndexedDB Error: ' + event.target.error);
            };
        });
    }

    async saveMessages(messages) {
        if (!this.db) await this.open();
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([this.storeName], 'readwrite');
            const store = transaction.objectStore(this.storeName);

            messages.forEach(msg => {
                // Ensure we have an ID. If not, we can't cache effectively with keyPath 'id'
                // Supabase usually provides one.
                if (msg.id) {
                    store.put(msg);
                }
            });

            transaction.oncomplete = () => resolve();
            transaction.onerror = (e) => reject(e);
        });
    }

    async getAllMessages() {
        if (!this.db) await this.open();
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([this.storeName], 'readonly');
            const store = transaction.objectStore(this.storeName);
            const index = store.index('created_at');
            const request = index.getAll();

            request.onsuccess = () => resolve(request.result || []);
            request.onerror = (e) => reject(e);
        });
    }

    async getLatestTimestamp() {
        if (!this.db) await this.open();
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction([this.storeName], 'readonly');
            const store = transaction.objectStore(this.storeName);
            const index = store.index('created_at');
            const request = index.openCursor(null, 'prev');

            request.onsuccess = (event) => {
                const cursor = event.target.result;
                if (cursor) {
                    resolve(cursor.value.created_at);
                } else {
                    resolve(null);
                }
            };
            request.onerror = (e) => reject(e);
        });
    }
}

class ChatApp {
    constructor() {
        this.API_URL = "/api/chat";
        this.HISTORY_URL = "/api/history/";
        this.PROFILE_URL = "/api/profile/";
        this.FEEDBACK_URL = "/api/chat/feedback";

        // State
        this.userId = null; // Will be set by Auth
        this.currentImageBase64 = null;
        this.isTyping = false;
        this.activeFeedbackPopup = null; // Track open popup

        // DOM Elements
        this.chatHistory = document.getElementById('chat-history');
        this.userInput = document.getElementById('user-input');
        this.sendBtn = document.getElementById('send-btn');
        this.uploadBtn = document.getElementById('upload-btn');
        this.fileInput = document.getElementById('file-input');
        this.previewContainer = document.getElementById('image-preview-container');
        this.imagePreview = document.getElementById('image-preview');
        this.clearImageBtn = document.getElementById('clear-image');

        // Initialize
        this.init();
    }

    init() {
        // Event Listeners
        this.sendBtn.addEventListener('click', () => this.sendMessage());
        this.userInput.addEventListener('keydown', (e) => this.handleEnterKey(e));
        this.uploadBtn.addEventListener('click', () => this.fileInput.click());
        this.fileInput.addEventListener('change', (e) => this.handleFileSelect(e));
        this.clearImageBtn.addEventListener('click', () => this.clearImage());
        this.userInput.addEventListener('input', (e) => this.autoResizeInput(e.target));

        // Close feedback popup on outside click
        document.addEventListener('click', (e) => {
            if (this.activeFeedbackPopup && !e.target.closest('.feedback-popup') && !e.target.closest('.feedback-trigger')) {
                this.activeFeedbackPopup.remove();
                this.activeFeedbackPopup = null;
            }
        });
    }

    // Auth handled externally, this just sets ID
    setUserId(id) {
        this.userId = id;
    }

    scrollToBottom() {
        this.chatHistory.scrollTop = this.chatHistory.scrollHeight;
    }

    showTypingIndicator() {
        if (this.isTyping) return;
        this.isTyping = true;

        const typingDiv = document.createElement('div');
        typingDiv.className = 'typing-indicator';
        typingDiv.id = 'typing-indicator';
        typingDiv.innerHTML = `
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
        `;
        this.chatHistory.appendChild(typingDiv);
        typingDiv.style.display = 'block';
        this.scrollToBottom();
    }

    hideTypingIndicator() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) {
            indicator.remove();
        }
        this.isTyping = false;
    }

    appendMessage(role, text, chartData = null, imageBase64 = null, messageId = null) {
        const msgDiv = document.createElement('div');
        msgDiv.classList.add('message');
        msgDiv.classList.add(role === 'user' ? 'user-message' : 'bot-message');

        // Store message ID for feedback
        if (messageId) {
            msgDiv.setAttribute('data-message-id', messageId);
        }

        let contentHtml = "";

        // Image
        if (imageBase64) {
            contentHtml += `<img src="${imageBase64}" style="max-width: 200px; border-radius: 12px; display: block; margin-bottom: 8px; border: 1px solid rgba(255,255,255,0.1);">`;
        }

        // Markdown
        // Check if marked is available
        if (typeof marked !== 'undefined' && text) {
            contentHtml += marked.parse(text);
        } else {
            contentHtml += `<p>${text || ""}</p>`;
        }

        msgDiv.innerHTML = contentHtml;

        // Render LaTeX (KaTeX)
        try {
            if (typeof renderMathInElement !== 'undefined') {
                renderMathInElement(msgDiv, {
                    delimiters: [
                        { left: '$$', right: '$$', display: true },
                        { left: '$', right: '$', display: false },
                        { left: '\\(', right: '\\)', display: false },
                        { left: '\\[', right: '\\]', display: true }
                    ],
                    throwOnError: false
                });
            }
        } catch (e) {
            console.warn("KaTeX rendering failed:", e);
        }

        this.chatHistory.appendChild(msgDiv);

        // Add feedback trigger for bot messages with a message ID
        if (role !== 'user' && messageId) {
            this.createFeedbackTrigger(msgDiv, messageId);
        }

        // Chart
        if (chartData && chartData.image_base64) {
            this.appendChart(chartData);
        }

        this.scrollToBottom();
    }

    appendChart(chartData) {
        const chartContainer = document.createElement('div');
        chartContainer.classList.add('chart-container');

        const img = document.createElement('img');
        img.src = `data:image/png;base64,${chartData.image_base64}`;
        img.alt = chartData.caption || "Chart";
        img.style.maxWidth = "100%";
        img.style.borderRadius = "8px";

        chartContainer.appendChild(img);

        if (chartData.caption) {
            const caption = document.createElement('div');
            caption.style.color = '#8b949e';
            caption.style.fontSize = '0.85rem';
            caption.style.marginTop = '8px';
            caption.style.textAlign = 'center';
            caption.innerText = chartData.caption;
            chartContainer.appendChild(caption);
        }

        this.chatHistory.appendChild(chartContainer);
    }

    async sendMessage() {
        const text = this.userInput.value.trim();
        const image = this.currentImageBase64;

        if (!text && !image) return;

        // Optimistic UI
        this.appendMessage('user', text, null, image);

        // Clear UI
        this.userInput.value = '';
        this.userInput.style.height = 'auto'; // Reset height
        this.clearImage();

        this.showTypingIndicator();

        try {
            const payload = {
                guest_id: this.userId,
                message: text,
                image: image
            };

            const response = await fetch(this.API_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();

            this.hideTypingIndicator();
            this.appendMessage('model', data.text, data.chart, null, data.message_id);

            // ── PostHog: Track chat message sent ──
            if (typeof posthog !== 'undefined') {
                posthog.capture('chat_message_sent', {
                    message_length: text.length,
                    has_image: !!image,
                    has_chart_response: !!data.chart,
                    response_length: (data.text || '').length,
                });
            }

        } catch (error) {
            console.error('Send Error:', error);
            this.hideTypingIndicator();
            this.appendMessage('model', `**Error**: Failed to communicate with the server. (${error.message})`);
            // ── PostHog: Track chat error ──
            if (typeof posthog !== 'undefined') {
                posthog.capture('chat_message_error', { error: error.message });
            }
        }
    }

    handleEnterKey(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            this.sendMessage();
        }
    }

    handleFileSelect(e) {
        const file = e.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (e) => {
            this.currentImageBase64 = e.target.result;
            this.imagePreview.src = this.currentImageBase64;
            this.previewContainer.style.display = 'inline-block';
        };
        reader.readAsDataURL(file);
    }

    clearImage() {
        this.fileInput.value = '';
        this.currentImageBase64 = null;
        this.previewContainer.style.display = 'none';
    }

    autoResizeInput(element) {
        element.style.height = 'auto';
        element.style.height = (element.scrollHeight) + 'px';
    }

    async loadHistory() {
        if (!this.userId) return;

        try {
            // 1. Initialize Cache with user ID
            this.cache = new ChatCache(this.userId);
            await this.cache.open();

            // 2. Load and render cached messages immediately
            const cachedMessages = await this.cache.getAllMessages();
            if (cachedMessages.length > 0) {
                this.chatHistory.innerHTML = '';
                this.renderMessages(cachedMessages);
            }

            // 3. Check for new messages
            const lastTimestamp = await this.cache.getLatestTimestamp();
            let url = `${this.HISTORY_URL}${this.userId}`;
            if (lastTimestamp) {
                url += `?after=${encodeURIComponent(lastTimestamp)}`;
            }

            const response = await fetch(url);
            if (!response.ok) throw new Error("History fetch failed");

            const newMessages = await response.json();

            // 4. Save and append new messages
            if (newMessages.length > 0) {
                await this.cache.saveMessages(newMessages);

                // If we had no cache, clear the "welcome" text
                if (cachedMessages.length === 0) {
                    this.chatHistory.innerHTML = '';
                }

                this.renderMessages(newMessages);
            }

            this.scrollToBottom();

        } catch (error) {
            console.error("History Load Error:", error);
        }
    }

    renderMessages(messages) {
        messages.forEach(msg => {
            let chartData = null;
            let userImageBase64 = null;

            // Image Handling
            if (msg.image_data) {
                userImageBase64 = msg.image_data;
            } else if (msg.tool_calls) {
                // Legacy Fallback
                let tools = msg.tool_calls;
                if (typeof tools === 'string') {
                    try { tools = JSON.parse(tools); } catch (e) { }
                }

                if (Array.isArray(tools)) {
                    // User Image
                    const userImg = tools.find(t => t.name === 'user_image');
                    if (userImg) {
                        userImageBase64 = `data:${userImg.mime_type || 'image/jpeg'};base64,${userImg.image_base64}`;
                    }
                }
            }

            // Chart Parsing
            if (msg.tool_calls) {
                let tools = msg.tool_calls;
                if (typeof tools === 'string') {
                    try { tools = JSON.parse(tools); } catch (e) { }
                }

                if (Array.isArray(tools)) {
                    // Chart
                    const chartTool = tools.find(t => {
                        if (!t.response) return false;
                        let r = t.response;
                        if (typeof r === 'string') {
                            try { r = JSON.parse(r); } catch (e) { return false; }
                        }
                        return r && r.image_base64;
                    });

                    if (chartTool) {
                        let resp = chartTool.response;
                        if (typeof resp === 'string') {
                            try { resp = JSON.parse(resp); } catch (e) { }
                        }
                        chartData = {
                            image_base64: resp.image_base64,
                            caption: resp.caption
                        };
                    }
                }
            }

            this.appendMessage(msg.role, msg.content, chartData, userImageBase64, msg.id);
        });
    }

    clearChat() {
        this.chatHistory.innerHTML = '';
        const welcome = document.createElement('div');
        welcome.className = 'message bot-message';
        welcome.innerText = "Hello! I'm your NutriSync coach. How can I help you today?";
        this.chatHistory.appendChild(welcome);
    }

    // --- Feedback System ---

    createFeedbackTrigger(msgDiv, messageId) {
        const trigger = document.createElement('button');
        trigger.className = 'feedback-trigger';
        trigger.setAttribute('data-message-id', messageId);
        trigger.title = 'Give feedback';
        trigger.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                <line x1="9" y1="10" x2="9" y2="10"></line>
                <line x1="12" y1="10" x2="12" y2="10"></line>
                <line x1="15" y1="10" x2="15" y2="10"></line>
            </svg>
        `;
        trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            this.showFeedbackPopup(msgDiv, messageId);
        });
        msgDiv.appendChild(trigger);
    }

    showFeedbackPopup(msgDiv, messageId) {
        // Close any existing popup
        if (this.activeFeedbackPopup) {
            this.activeFeedbackPopup.remove();
            this.activeFeedbackPopup = null;
        }

        const popup = document.createElement('div');
        popup.className = 'feedback-popup';
        popup.setAttribute('data-message-id', messageId);

        // Check existing feedback state from the trigger
        const trigger = msgDiv.querySelector('.feedback-trigger');
        const existingValue = trigger ? trigger.getAttribute('data-feedback-value') : null;

        popup.innerHTML = `
            <div class="feedback-header">Rate this response</div>
            <div class="feedback-buttons">
                <button class="feedback-btn feedback-btn-like ${existingValue === '1' ? 'active' : ''}" data-value="1" title="Like">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z"></path>
                        <path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"></path>
                    </svg>
                    <span>Like</span>
                </button>
                <button class="feedback-btn feedback-btn-dislike ${existingValue === '-1' ? 'active' : ''}" data-value="-1" title="Dislike">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10z"></path>
                        <path d="M17 2h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3"></path>
                    </svg>
                    <span>Dislike</span>
                </button>
            </div>
            <div class="feedback-comment-section" style="display: none;">
                <textarea class="feedback-textarea" placeholder="Tell us what was helpful or what went wrong..." minlength="10"></textarea>
                <div class="feedback-comment-footer">
                    <span class="feedback-char-count">0 / 10 min</span>
                    <button class="feedback-submit-btn" disabled>Submit</button>
                </div>
                <div class="feedback-error" style="display: none;"></div>
            </div>
            <div class="feedback-confirmation" style="display: none;">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                    <polyline points="22 4 12 14.01 9 11.01"></polyline>
                </svg>
                <span>Thanks for your feedback!</span>
            </div>
        `;

        // Wire up like/dislike buttons
        let selectedValue = existingValue ? parseInt(existingValue) : null;
        const likeBtn = popup.querySelector('.feedback-btn-like');
        const dislikeBtn = popup.querySelector('.feedback-btn-dislike');
        const commentSection = popup.querySelector('.feedback-comment-section');
        const textarea = popup.querySelector('.feedback-textarea');
        const charCount = popup.querySelector('.feedback-char-count');
        const submitBtn = popup.querySelector('.feedback-submit-btn');
        const errorDiv = popup.querySelector('.feedback-error');

        const selectFeedback = (value) => {
            selectedValue = value;
            likeBtn.classList.toggle('active', value === 1);
            dislikeBtn.classList.toggle('active', value === -1);
            commentSection.style.display = 'block';
            textarea.focus();
        };

        likeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            selectFeedback(1);
        });

        dislikeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            selectFeedback(-1);
        });

        // If there was previous feedback, show comment section immediately
        if (existingValue) {
            commentSection.style.display = 'block';
        }

        // Character counter and validation
        textarea.addEventListener('input', () => {
            const len = textarea.value.trim().length;
            charCount.textContent = `${len} / 10 min`;
            submitBtn.disabled = len < 10;
            if (len >= 10) {
                charCount.classList.add('valid');
            } else {
                charCount.classList.remove('valid');
            }
            errorDiv.style.display = 'none';
        });

        // Submit
        submitBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const comment = textarea.value.trim();
            if (comment.length < 10) {
                errorDiv.textContent = 'Please write at least 10 characters.';
                errorDiv.style.display = 'block';
                return;
            }
            if (!selectedValue) return;

            submitBtn.disabled = true;
            submitBtn.textContent = 'Sending...';

            const success = await this.submitFeedback(messageId, selectedValue, comment);

            if (success) {
                // Show confirmation
                popup.querySelector('.feedback-buttons').style.display = 'none';
                commentSection.style.display = 'none';
                popup.querySelector('.feedback-confirmation').style.display = 'flex';

                // Update trigger icon color
                if (trigger) {
                    trigger.setAttribute('data-feedback-value', selectedValue.toString());
                    trigger.classList.add(selectedValue === 1 ? 'feedback-liked' : 'feedback-disliked');
                    trigger.classList.remove(selectedValue === 1 ? 'feedback-disliked' : 'feedback-liked');
                }

                // Auto-close after 1.5s
                setTimeout(() => {
                    popup.remove();
                    this.activeFeedbackPopup = null;
                }, 1500);
            } else {
                errorDiv.textContent = 'Failed to save feedback. Please try again.';
                errorDiv.style.display = 'block';
                submitBtn.disabled = false;
                submitBtn.textContent = 'Submit';
            }
        });

        msgDiv.appendChild(popup);
        this.activeFeedbackPopup = popup;
    }

    async submitFeedback(messageId, feedbackValue, feedbackComment) {
        try {
            const response = await fetch(this.FEEDBACK_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message_id: messageId,
                    guest_id: this.userId,
                    feedback_value: feedbackValue,
                    feedback_comment: feedbackComment
                })
            });
            // ── PostHog: Track message feedback ──
            if (response.ok && typeof posthog !== 'undefined') {
                posthog.capture('message_feedback_submitted', {
                    feedback_value: feedbackValue === 1 ? 'like' : 'dislike',
                    comment_length: feedbackComment.length,
                });
            }
            return response.ok;
        } catch (error) {
            console.error('Feedback Error:', error);
            return false;
        }
    }
}

// Auth & App Initialization
document.addEventListener('DOMContentLoaded', async () => {
    // SUPABASE CONFIGURATION
    const SUPABASE_URL = 'https://yxudijlpccuwszvaimec.supabase.co';
    const SUPABASE_ANON_KEY = 'sb_publishable_m6AFUpWRwLDOlak4MuqL-w_ljz3-lrF';

    if (typeof supabase === 'undefined') {
        console.error("Supabase Client not loaded.");
        return;
    }

    const sbClient = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

    // Explicitly parse URL hash tokens on initial load (crucial for email redirects)
    await sbClient.auth.getSession();

    window.app = new ChatApp();

    // DOM Elements - Auth & Wizard
    const authOverlay = document.getElementById('auth-overlay');
    const authForm = document.getElementById('auth-form');
    const emailInput = document.getElementById('email');
    const passwordInput = document.getElementById('password');
    const authSubmitBtn = document.getElementById('auth-submit-btn');
    const authToggleBtn = document.getElementById('auth-toggle-btn');
    const authToggleText = document.getElementById('auth-toggle-text');
    const authTitle = document.getElementById('auth-title');
    const authMessage = document.getElementById('auth-message');

    const onboardingOverlay = document.getElementById('onboarding-overlay');
    const onboardingForm = document.getElementById('onboarding-form');
    const wizardNextBtn = document.getElementById('wizard-next-btn');
    const wizardBackBtn = document.getElementById('wizard-back-btn');
    const wizardSubmitBtn = document.getElementById('wizard-submit-btn');
    const wizardTitle = document.getElementById('wizard-title');
    const wizardSubtitle = document.getElementById('wizard-subtitle');

    // Live Coach Elements
    const liveCoachToggleBtn = document.getElementById('live-coach-toggle-btn');
    const liveCoachOverlay = document.getElementById('live-coach-overlay');
    const closeCoachBtn = document.getElementById('close-coach-btn');
    const startCoachBtn = document.getElementById('start-coach-btn');
    const stopCoachBtn = document.getElementById('stop-coach-btn');
    const coachVideo = document.getElementById('coach-video');
    const coachCanvas = document.getElementById('coach-canvas');
    const coachExerciseSelect = document.getElementById('coach-exercise-select');

    const logoutBtn = document.createElement('button'); // Create Logout Button
    logoutBtn.innerHTML = `
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
            <polyline points="16 17 21 12 16 7"></polyline>
            <line x1="21" y1="12" x2="9" y2="12"></line>
        </svg>
    `;
    logoutBtn.title = "Sign Out";
    logoutBtn.style.marginLeft = "auto";
    logoutBtn.addEventListener('click', handleLogout);
    document.querySelector('header').appendChild(logoutBtn);

    // --- Live Coach Logic ---
    let liveCoachSystem = null;
    let coachSetsLogged = 0;

    // Live Coach exercise logging elements
    const logExerciseBtn = document.getElementById('log-exercise-btn');
    const logExerciseBtnText = document.getElementById('log-exercise-btn-text');
    const coachSessionStats = document.getElementById('coach-session-stats');
    const coachSessionSets = document.getElementById('coach-session-sets');
    const coachSessionRepsDisplay = document.getElementById('coach-session-reps-display');
    const coachToast = document.getElementById('coach-toast');

    const COACH_EXERCISE_LABELS = {
        'squat': 'Bodyweight Squat',
        'pushup': 'Push-up',
        'pullup': 'Pull-up'
    };

    function getCoachReps() {
        if (!liveCoachSystem || !liveCoachSystem.exerciseEngine) return 0;
        const profile = liveCoachSystem.exerciseEngine.currentProfile;
        return profile ? profile.reps : 0;
    }

    function updateLogButton() {
        const reps = getCoachReps();
        const exKey = coachExerciseSelect ? coachExerciseSelect.value : 'squat';
        const exLabel = COACH_EXERCISE_LABELS[exKey] || exKey;

        if (reps > 0) {
            logExerciseBtn.classList.remove('hidden');
            logExerciseBtn.disabled = false;
            logExerciseBtnText.textContent = `Log ${reps} rep${reps !== 1 ? 's' : ''} — ${exLabel}`;
        } else {
            logExerciseBtnText.textContent = 'Log Exercise';
            logExerciseBtn.disabled = true;
        }
    }

    function showCoachToast(message, isSuccess = true) {
        coachToast.textContent = message;
        coachToast.className = `coach-toast ${isSuccess ? 'coach-toast-success' : 'coach-toast-error'}`;
        coachToast.classList.remove('hidden');
        setTimeout(() => coachToast.classList.add('hidden'), 4000);
    }

    if (liveCoachToggleBtn) {
        liveCoachToggleBtn.addEventListener('click', () => {
            liveCoachOverlay.classList.remove('hidden');

            // Initialize system if not already done
            if (!liveCoachSystem && window.LiveCoachController) {
                const cameraManager = new window.CameraManager(coachVideo, 640, 480);
                const poseService = new window.PoseEstimationService();
                const uiRenderer = new window.UIRenderer(coachCanvas);
                const exerciseEngine = new window.ExerciseEngine();
                liveCoachSystem = new window.LiveCoachController(cameraManager, poseService, uiRenderer, exerciseEngine);
            }

            // Reset session stats when opening
            coachSetsLogged = 0;
            if (coachSessionStats) coachSessionStats.classList.add('hidden');
            if (coachSessionSets) coachSessionSets.textContent = 'Sets logged: 0';
            updateLogButton();
        });
    }

    if (closeCoachBtn) {
        closeCoachBtn.addEventListener('click', () => {
            if (liveCoachSystem) {
                liveCoachSystem.stop();
            }
            startCoachBtn.classList.remove('hidden');
            stopCoachBtn.classList.add('hidden');
            logExerciseBtn.classList.add('hidden');
            liveCoachOverlay.classList.add('hidden');
        });
    }

    if (startCoachBtn) {
        startCoachBtn.addEventListener('click', () => {
            if (liveCoachSystem) {
                liveCoachSystem.start();
                startCoachBtn.classList.add('hidden');
                stopCoachBtn.classList.remove('hidden');
                // ── PostHog: Track live coach start ──
                if (typeof posthog !== 'undefined') {
                    posthog.capture('live_coach_started', {
                        exercise: coachExerciseSelect ? coachExerciseSelect.value : 'squat',
                    });
                }
            }
        });
    }

    if (stopCoachBtn) {
        stopCoachBtn.addEventListener('click', () => {
            if (liveCoachSystem) {
                liveCoachSystem.stop();
                startCoachBtn.classList.remove('hidden');
                stopCoachBtn.classList.add('hidden');
                updateLogButton();
                // ── PostHog: Track live coach stop ──
                if (typeof posthog !== 'undefined') {
                    posthog.capture('live_coach_stopped', {
                        exercise: coachExerciseSelect ? coachExerciseSelect.value : 'squat',
                        sets_logged: coachSetsLogged,
                    });
                }
            }
        });
    }

    if (coachExerciseSelect) {
        coachExerciseSelect.addEventListener('change', (e) => {
            if (liveCoachSystem && liveCoachSystem.exerciseEngine) {
                liveCoachSystem.exerciseEngine.setExercise(e.target.value);
                logExerciseBtn.classList.add('hidden');
                logExerciseBtn.disabled = true;
                coachSetsLogged = 0;
                if (coachSessionStats) coachSessionStats.classList.add('hidden');
                if (coachSessionSets) coachSessionSets.textContent = 'Sets logged: 0';
            }
        });
    }

    // Log Exercise button handler
    if (logExerciseBtn) {
        logExerciseBtn.addEventListener('click', async () => {
            const reps = getCoachReps();
            const exKey = coachExerciseSelect ? coachExerciseSelect.value : 'squat';
            const userId = window.app ? window.app.userId : null;

            if (!userId) {
                showCoachToast('Not signed in. Please sign in first.', false);
                return;
            }
            if (reps <= 0) {
                showCoachToast('No reps to log. Do some reps first!', false);
                return;
            }

            logExerciseBtn.disabled = true;
            logExerciseBtnText.textContent = 'Logging...';

            try {
                const resp = await fetch('/api/live-coach/log', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        user_id: userId,
                        exercise_key: exKey,
                        reps: reps,
                    })
                });

                const data = await resp.json();

                if (resp.ok && data.success) {
                    coachSetsLogged++;
                    const prMsg = data.is_pr
                        ? ` 🏆 NEW ${data.pr_type.toUpperCase()} PR!`
                        : '';
                    showCoachToast(
                        `Set ${data.set_number} logged: ${data.reps} reps × ${data.weight_kg}kg${prMsg}`,
                        true
                    );
                    // ── PostHog: Track live coach exercise logged ──
                    if (typeof posthog !== 'undefined') {
                        posthog.capture('live_coach_exercise_logged', {
                            exercise: data.exercise_name,
                            set_number: data.set_number,
                            reps: data.reps,
                            weight_kg: data.weight_kg,
                            is_pr: data.is_pr,
                            pr_type: data.pr_type,
                        });
                    }

                    // Update session stats
                    coachSessionStats.classList.remove('hidden');
                    coachSessionSets.textContent = `Sets logged: ${coachSetsLogged}`;
                    coachSessionRepsDisplay.textContent = `Last: ${data.reps} reps`;

                    // Reset rep counter for next set
                    if (liveCoachSystem && liveCoachSystem.exerciseEngine && liveCoachSystem.exerciseEngine.currentProfile) {
                        liveCoachSystem.exerciseEngine.currentProfile.reps = 0;
                        liveCoachSystem.exerciseEngine.currentProfile.feedback = "Ready";
                        if (liveCoachSystem.exerciseEngine.currentProfile.state !== 'SETUP') {
                            liveCoachSystem.exerciseEngine.currentProfile.state = 'UP';
                        }
                    }

                    logExerciseBtnText.textContent = 'Log Exercise';
                    logExerciseBtn.disabled = true;
                } else {
                    showCoachToast(data.detail || 'Failed to log exercise.', false);
                    updateLogButton();
                }
            } catch (err) {
                showCoachToast('Network error. Please try again.', false);
                updateLogButton();
            }
        });
    }

    // --- Auth Logic ---
    let isSignUp = false;

    // Toggle Sign In / Sign Up
    authToggleBtn.addEventListener('click', () => {
        isSignUp = !isSignUp;
        if (isSignUp) {
            authTitle.innerText = "Create Account";
            authSubmitBtn.innerText = "Sign Up";
            authToggleText.innerText = "Already have an account?";
            authToggleBtn.innerText = "Sign In";
        } else {
            authTitle.innerText = "Welcome Back";
            authSubmitBtn.innerText = "Sign In";
            authToggleText.innerText = "Don't have an account?";
            authToggleBtn.innerText = "Sign Up";
        }
        authMessage.innerText = "";
    });

    // Handle Form Submit
    authForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = emailInput.value;
        const password = passwordInput.value;

        authMessage.innerText = "Processing...";
        authMessage.className = "auth-message";

        try {
            if (isSignUp) {
                // Validate Password Strength briefly (client side)
                if (password.length < 8) {
                    throw new Error("Password must be at least 8 characters");
                }
                const { data, error } = await sbClient.auth.signUp({
                    email: email,
                    password: password
                });
                if (error) throw error;
                // ── PostHog: Track sign up ──
                if (typeof posthog !== 'undefined') posthog.capture('user_signed_up', { method: 'email' });
                // If email confirmation is enabled, user needs to check their email.
                // If disabled (e.g. during beta), session is returned immediately.
                if (data.session) {
                    // Auto-confirmed — onAuthStateChange will handle the rest
                    authMessage.innerText = "Account created! Signing you in...";
                } else {
                    authMessage.innerText = "Check your email for the confirmation link!";
                }
                authMessage.classList.add("success");
            } else {
                const { data, error } = await sbClient.auth.signInWithPassword({
                    email: email,
                    password: password
                });
                if (error) throw error;
                // ── PostHog: Track sign in ──
                if (typeof posthog !== 'undefined') posthog.capture('user_signed_in', { method: 'email' });
                // Success - onAuthStateChange will handle the rest
            }
        } catch (error) {
            authMessage.innerText = error.message;
            authMessage.classList.add("error");
        }
    });

    async function handleLogout() {
        const { error } = await sbClient.auth.signOut();
        if (error) console.error("Sign out error", error);
        // Clean cache handled by onAuthStateChange logic partially, 
        // but we explicitly remove LocalStorage
        localStorage.removeItem('nutrisync_user_id');
        window.location.reload(); // Hard reload to clear everything
    }

    // --- Onboarding Logic ---
    let currentStep = 1;
    const totalSteps = 6; // Updated to 6 (Sport/Split added)

    // Split Templates
    const splitTemplates = {
        "PPL": ["Push", "Pull", "Legs", "Rest"],
        "Bro Split": ["Chest", "Back", "Legs", "Shoulders", "Arms", "Rest", "Rest"],
        "Upper Lower": ["Upper", "Lower", "Rest", "Upper", "Lower", "Rest", "Rest"],
        "Full Body": ["Full Body A", "Rest", "Full Body B", "Rest", "Full Body A", "Rest", "Rest"],
        "Arnold Split": ["Chest & Back", "Shoulders & Arms", "Legs", "Chest & Back", "Shoulders & Arms", "Legs", "Rest"],
        "PPL x2": ["Push", "Pull", "Legs", "Push", "Pull", "Legs", "Rest"],
        "Custom": ["Day 1"]
    };

    function showStep(step) {
        document.querySelectorAll('.wizard-step').forEach(el => el.classList.add('hidden'));
        document.querySelector(`.wizard-step[data-step="${step}"]`).classList.remove('hidden');

        // Buttons
        if (step === 1) {
            wizardBackBtn.classList.add('hidden');
        } else {
            wizardBackBtn.classList.remove('hidden');
        }

        if (step === totalSteps) {
            wizardNextBtn.classList.add('hidden');
            wizardSubmitBtn.classList.remove('hidden');
        } else {
            wizardNextBtn.classList.remove('hidden');
            wizardSubmitBtn.classList.add('hidden');
        }

        wizardSubtitle.innerText = `Step ${step} of ${totalSteps}`;
    }

    // Split Editor Functions
    function renderSplitEditor(days) {
        const container = document.getElementById('split-editor-container');
        const addBtn = document.getElementById('add-split-day-btn');
        container.innerHTML = '';

        days.forEach((day, index) => {
            const row = document.createElement('div');
            row.style.display = 'flex';
            row.style.gap = '8px';
            row.style.alignItems = 'center';

            const input = document.createElement('input');
            input.type = 'text';
            input.value = day;
            input.className = 'split-day-input';
            input.placeholder = `Day ${index + 1}`;
            input.style.flex = '1';

            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.innerText = '×';
            removeBtn.className = 'secondary-btn';
            removeBtn.style.padding = '4px 8px';
            removeBtn.style.color = '#f85149';
            removeBtn.style.borderColor = 'rgba(248, 81, 73, 0.4)';
            removeBtn.onclick = () => {
                row.remove();
                checkSplitLimit();
            };

            row.appendChild(input);
            row.appendChild(removeBtn);
            container.appendChild(row);
        });
        checkSplitLimit();
    }

    function checkSplitLimit() {
        const container = document.getElementById('split-editor-container');
        const addBtn = document.getElementById('add-split-day-btn');
        if (container.children.length >= 7) {
            addBtn.disabled = true;
            addBtn.innerText = "Max 7 Days Reached";
        } else {
            addBtn.disabled = false;
            addBtn.innerText = "+ Add Day";
        }
    }

    // --- 1RM Editor Functions ---
    function renderRMEditor(records = []) {
        const container = document.getElementById('rm-editor-container');
        container.innerHTML = '';
        records.forEach(record => {
            addRMRow(record.exercise_name, record.weight_kg);
        });
    }

    function addRMRow(exerciseName = "", weightKg = "") {
        const container = document.getElementById('rm-editor-container');

        const row = document.createElement('div');
        row.className = 'rm-record-row';
        row.style.display = 'flex';
        row.style.gap = '8px';
        row.style.alignItems = 'center';

        const nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.value = exerciseName;
        nameInput.className = 'rm-exercise-input';
        nameInput.placeholder = `Exercise (e.g. Squat)`;
        nameInput.style.flex = '2';

        const weightInput = document.createElement('input');
        weightInput.type = 'number';
        weightInput.value = weightKg;
        weightInput.className = 'rm-weight-input';
        weightInput.placeholder = `Weight (kg)`;
        weightInput.step = '0.5';
        weightInput.style.flex = '1';

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.innerText = '×';
        removeBtn.className = 'secondary-btn';
        removeBtn.style.padding = '4px 8px';
        removeBtn.style.color = '#f85149';
        removeBtn.style.borderColor = 'rgba(248, 81, 73, 0.4)';
        removeBtn.onclick = () => {
            row.remove();
        };

        row.appendChild(nameInput);
        row.appendChild(weightInput);
        row.appendChild(removeBtn);
        container.appendChild(row);
    }

    const addRMBtn = document.getElementById('add-rm-btn');
    if (addRMBtn) {
        addRMBtn.addEventListener('click', () => {
            addRMRow();
        });
    }

    // Event Listeners for Split/Sport
    const profileSport = document.getElementById('profile-sport');
    const gymOptions = document.getElementById('gym-options');

    // ── Equipment Preset Data (researched from comprehensive gym equipment lists) ──
    const EQUIPMENT_PRESETS = {
        "Gym": {
            "Chest & Arms Machines": [
                "Chest Press Machine", "Chest Fly / Pec Deck", "Seated Dip Machine",
                "Arm Curl Machine", "Arm Extension Machine", "Tricep Press Machine",
                "Preacher Curl Bench"
            ],
            "Shoulder Machines": [
                "Shoulder Press Machine", "Lateral Raise Machine"
            ],
            "Back Machines": [
                "Lat Pulldown Machine", "Seated Cable Row", "Back Extension / Roman Chair",
                "GHD Machine", "T-Bar Row Machine"
            ],
            "Leg Machines": [
                "Leg Press Machine", "Hack Squat Machine", "Leg Extension Machine",
                "Leg Curl Machine", "Hip Abductor / Adductor", "Seated Calf Raise",
                "Standing Calf Raise", "Glute Kickback Machine"
            ],
            "Core Machines": [
                "Ab Crunch Machine", "Rotary Torso Machine", "Leg Raise / Dip Tower",
                "Abdominal Bench"
            ],
            "Multi-Station & Cables": [
                "Cable Crossover Machine", "Functional Trainer", "Smith Machine",
                "Power Rack / Squat Rack"
            ],
            "Free Weights": [
                "Barbell (Olympic)", "EZ-Curl Bar", "Dumbbells (Fixed)",
                "Adjustable Dumbbells", "Kettlebells", "Weight Plates",
                "Trap Bar / Hex Bar"
            ],
            "Benches": [
                "Flat Bench", "Adjustable Bench (Incline/Decline)", "Olympic Weight Bench",
                "Decline Bench"
            ],
            "Cardio Machines": [
                "Treadmill", "Elliptical / Cross Trainer", "Stationary Bike (Upright)",
                "Recumbent Bike", "Spin Bike", "Rowing Machine", "Stair Climber / StepMill",
                "Air Bike", "Ski Erg", "Vertical Climber"
            ],
            "Accessories": [
                "Resistance Bands", "Pull-Up Bar", "Dip Station", "Ab Roller",
                "Battle Ropes", "Suspension Trainer (TRX)", "Medicine Ball",
                "Stability / Swiss Ball", "Foam Roller", "Plyometric Box",
                "Jump Rope", "Gymnastic Rings", "Landmine Attachment",
                "Weighted Vest", "Ankle Weights"
            ]
        },
        "Home": {
            "Free Weights": [
                "Dumbbells (Fixed)", "Adjustable Dumbbells", "Kettlebells",
                "Barbell (Olympic)", "EZ-Curl Bar", "Weight Plates"
            ],
            "Benches & Racks": [
                "Adjustable Bench (Incline/Decline)", "Flat Bench", "Power Rack / Squat Rack",
                "Smith Machine"
            ],
            "Cardio": [
                "Treadmill", "Stationary Bike (Upright)", "Spin Bike",
                "Rowing Machine", "Elliptical / Cross Trainer", "Air Bike", "Jump Rope"
            ],
            "Bodyweight & Accessories": [
                "Pull-Up Bar", "Dip Station", "Resistance Bands",
                "Suspension Trainer (TRX)", "Ab Roller", "Plyometric Box",
                "Stability / Swiss Ball", "Medicine Ball", "Foam Roller",
                "Gymnastic Rings", "Push-Up Bars", "Weighted Vest", "Battle Ropes"
            ]
        },
        "Bodyweight": {
            "Bodyweight Equipment": [
                "Pull-Up Bar", "Dip Station", "Gymnastic Rings",
                "Push-Up Bars", "Ab Roller", "Plyometric Box"
            ],
            "Accessories": [
                "Resistance Bands", "Suspension Trainer (TRX)", "Jump Rope",
                "Foam Roller", "Stability / Swiss Ball", "Weighted Vest",
                "Ankle Weights", "Yoga Mat"
            ]
        }
    };

    // ── Equipment Chip Rendering ──
    let selectedEquipment = new Set();

    function renderEquipmentChips(tier) {
        const container = document.getElementById('equipment-chips-container');
        if (!container) return;
        container.innerHTML = '';
        const presets = EQUIPMENT_PRESETS[tier] || EQUIPMENT_PRESETS["Gym"];

        Object.entries(presets).forEach(([category, items]) => {
            const block = document.createElement('div');
            block.className = 'equip-category-block';

            const label = document.createElement('span');
            label.className = 'equip-category-label';
            label.textContent = category;
            block.appendChild(label);

            const chipsWrap = document.createElement('div');
            chipsWrap.className = 'equip-category-chips';

            items.forEach(name => {
                const chip = document.createElement('span');
                chip.className = 'equip-chip' + (selectedEquipment.has(name) ? ' selected' : '');
                chip.textContent = name;
                chip.dataset.name = name;
                chip.dataset.category = category;
                chip.addEventListener('click', () => {
                    if (selectedEquipment.has(name)) {
                        selectedEquipment.delete(name);
                        chip.classList.remove('selected');
                    } else {
                        selectedEquipment.add(name);
                        chip.classList.add('selected');
                    }
                    updateSelectAllBtnState(tier);
                });
                chipsWrap.appendChild(chip);
            });

            block.appendChild(chipsWrap);
            container.appendChild(block);
        });

        // Re-render any custom chips that are not in presets
        const allPresetNames = new Set(Object.values(presets).flat());
        selectedEquipment.forEach(name => {
            if (!allPresetNames.has(name)) {
                addCustomChipToDOM(name);
            }
        });

        updateSelectAllBtnState(tier);
    }

    function addCustomChipToDOM(name) {
        const container = document.getElementById('equipment-chips-container');
        // Check if a "Custom" category block exists, if not create one
        let customBlock = container.querySelector('.equip-category-block[data-custom="true"]');
        if (!customBlock) {
            customBlock = document.createElement('div');
            customBlock.className = 'equip-category-block';
            customBlock.dataset.custom = "true";
            const label = document.createElement('span');
            label.className = 'equip-category-label';
            label.textContent = 'Custom';
            customBlock.appendChild(label);
            const chipsWrap = document.createElement('div');
            chipsWrap.className = 'equip-category-chips';
            customBlock.appendChild(chipsWrap);
            container.appendChild(customBlock);
        }
        const chipsWrap = customBlock.querySelector('.equip-category-chips');

        const chip = document.createElement('span');
        chip.className = 'equip-chip custom-chip selected';
        chip.dataset.name = name;
        chip.dataset.category = 'Custom';

        const textSpan = document.createElement('span');
        textSpan.textContent = name;
        chip.appendChild(textSpan);

        const removeBtn = document.createElement('span');
        removeBtn.className = 'remove-custom';
        removeBtn.textContent = '×';
        removeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            selectedEquipment.delete(name);
            chip.remove();
            // Clean up empty custom block
            if (chipsWrap.children.length === 0) customBlock.remove();
        });
        chip.appendChild(removeBtn);

        chip.addEventListener('click', () => {
            if (selectedEquipment.has(name)) {
                selectedEquipment.delete(name);
                chip.classList.remove('selected');
            } else {
                selectedEquipment.add(name);
                chip.classList.add('selected');
            }
        });

        chipsWrap.appendChild(chip);
    }

    function getAllPresetNamesForTier(tier) {
        const presets = EQUIPMENT_PRESETS[tier] || EQUIPMENT_PRESETS["Gym"];
        return new Set(Object.values(presets).flat());
    }

    function updateSelectAllBtnState(tier) {
        const btn = document.getElementById('equip-select-all-btn');
        if (!btn) return;
        const allNames = getAllPresetNamesForTier(tier);
        const allSelected = [...allNames].every(n => selectedEquipment.has(n));
        btn.textContent = allSelected ? '✅ All Selected' : '✅ Select All';
    }

    // ── Equipment Event Listeners ──
    const equipSelectAllBtn = document.getElementById('equip-select-all-btn');
    if (equipSelectAllBtn) {
        equipSelectAllBtn.addEventListener('click', () => {
            const tier = document.getElementById('profile-equipment').value;
            const allNames = getAllPresetNamesForTier(tier);
            allNames.forEach(n => selectedEquipment.add(n));
            renderEquipmentChips(tier);
        });
    }

    const equipDeselectAllBtn = document.getElementById('equip-deselect-all-btn');
    if (equipDeselectAllBtn) {
        equipDeselectAllBtn.addEventListener('click', () => {
            const tier = document.getElementById('profile-equipment').value;
            const allNames = getAllPresetNamesForTier(tier);
            // Only clear preset items for current tier; keep custom items
            allNames.forEach(n => selectedEquipment.delete(n));
            renderEquipmentChips(tier);
        });
    }

    const equipCustomAddBtn = document.getElementById('equip-custom-add-btn');
    const equipCustomInput = document.getElementById('equip-custom-input');
    if (equipCustomAddBtn && equipCustomInput) {
        const addCustomEquipment = () => {
            const name = equipCustomInput.value.trim();
            if (name && !selectedEquipment.has(name)) {
                selectedEquipment.add(name);
                addCustomChipToDOM(name);
            }
            equipCustomInput.value = '';
        };
        equipCustomAddBtn.addEventListener('click', addCustomEquipment);
        equipCustomInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                addCustomEquipment();
            }
        });
    }

    // Re-render chips when equipment tier changes
    const profileEquipmentSelect = document.getElementById('profile-equipment');
    if (profileEquipmentSelect) {
        profileEquipmentSelect.addEventListener('change', () => {
            // Keep custom items, clear preset selections, render new tier
            const newTier = profileEquipmentSelect.value;
            // Clear all preset from ALL tiers, keep only custom
            const allKnown = new Set();
            Object.values(EQUIPMENT_PRESETS).forEach(tierObj => {
                Object.values(tierObj).forEach(items => items.forEach(n => allKnown.add(n)));
            });
            const customItems = [...selectedEquipment].filter(n => !allKnown.has(n));
            selectedEquipment.clear();
            customItems.forEach(n => selectedEquipment.add(n));
            renderEquipmentChips(newTier);
        });
    }

    // Initial render of equipment chips
    renderEquipmentChips(profileEquipmentSelect ? profileEquipmentSelect.value : 'Gym');

    if (profileSport) {
        profileSport.addEventListener('change', () => {
            if (profileSport.value === 'Gym') {
                gymOptions.style.display = 'block';
            } else {
                gymOptions.style.display = 'none';
            }
        });
    }

    const profileSplitTemplate = document.getElementById('profile-split-template');
    if (profileSplitTemplate) {
        profileSplitTemplate.addEventListener('change', () => {
            const template = profileSplitTemplate.value;
            if (splitTemplates[template]) {
                const days = splitTemplates[template].slice(0, 7); // Ensure template respects limit
                renderSplitEditor(days);
            }
        });
    }

    const profileGoal = document.getElementById('profile-goal');
    const targetWeightContainer = document.getElementById('target-weight-container');
    if (profileGoal && targetWeightContainer) {
        profileGoal.addEventListener('change', () => {
            if (profileGoal.value === 'Maintain') {
                targetWeightContainer.classList.add('hidden');
            } else {
                targetWeightContainer.classList.remove('hidden');
            }
        });
    }

    const addSplitDayBtn = document.getElementById('add-split-day-btn');
    if (addSplitDayBtn) {
        addSplitDayBtn.addEventListener('click', () => {
            const container = document.getElementById('split-editor-container');
            if (container.children.length >= 7) return;

            const count = container.children.length + 1;

            const row = document.createElement('div');
            row.style.display = 'flex';
            row.style.gap = '8px';
            row.style.alignItems = 'center';

            const input = document.createElement('input');
            input.type = 'text';
            input.value = `Day ${count}`;
            input.className = 'split-day-input';
            input.style.flex = '1';

            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.innerText = '×';
            removeBtn.className = 'secondary-btn';
            removeBtn.style.padding = '4px 8px';
            removeBtn.style.color = '#f85149';
            removeBtn.style.borderColor = 'rgba(248, 81, 73, 0.4)';
            removeBtn.onclick = () => {
                row.remove();
                checkSplitLimit();
            };

            row.appendChild(input);
            row.appendChild(removeBtn);
            container.appendChild(row);
            checkSplitLimit();
        });
    }

    // Initialize Split Editor with default
    if (document.getElementById('split-editor-container')) {
        renderSplitEditor(splitTemplates['PPL']);
    }

    // Auto-Calculate Typical Calories (Mifflin-St Jeor)
    function estimateCalories() {
        const gender = document.getElementById('profile-gender').value;
        const weight = parseFloat(document.getElementById('profile-weight').value);
        const height = parseInt(document.getElementById('profile-height').value);
        const dobStr = document.getElementById('profile-dob').value;
        const caloriesInput = document.getElementById('profile-calories');

        if (weight && height && dobStr) {
            const dob = new Date(dobStr);
            const today = new Date();
            let age = today.getFullYear() - dob.getFullYear();
            const m = today.getMonth() - dob.getMonth();
            if (m < 0 || (m === 0 && today.getDate() < dob.getDate())) {
                age--;
            }

            let bmr;
            if (gender === 'Male') {
                bmr = (10 * weight) + (6.25 * height) - (5 * age) + 5;
            } else {
                bmr = (10 * weight) + (6.25 * height) - (5 * age) - 161;
            }

            // Assume Sedentary/Light Active for "Typical" baseline if unknown, 
            // or use the days to estimate TDEE
            const days = parseInt(document.getElementById('profile-days').value) || 3;
            let multiplier = 1.2;
            if (days >= 3) multiplier = 1.375;
            if (days >= 5) multiplier = 1.55;

            const measuredTDEE = Math.round(bmr * multiplier);
            caloriesInput.value = measuredTDEE;
        }
    }

    // Listeners for Auto-Calc
    ['profile-gender', 'profile-weight', 'profile-height', 'profile-dob', 'profile-days'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('change', estimateCalories);
    });

    wizardNextBtn.addEventListener('click', () => {
        // Validate Step
        const stepEl = document.querySelector(`.wizard-step[data-step="${currentStep}"]`);
        const inputs = stepEl.querySelectorAll('input, select');
        let valid = true;
        inputs.forEach(input => {
            if (input.hasAttribute('required') && !input.value) {
                valid = false;
                input.style.borderColor = '#f85149';
            } else {
                input.style.borderColor = '';
            }
        });

        if (!valid) return;

        // Validation per step
        if (currentStep === 2) {
            const dobStr = document.getElementById('profile-dob').value;
            const height = parseFloat(document.getElementById('profile-height').value);
            const weight = parseFloat(document.getElementById('profile-weight').value);

            if (dobStr) {
                const dob = new Date(dobStr);
                const today = new Date();
                if (dob >= today) {
                    alert("Date of birth cannot be in the future.");
                    return;
                }
                const age = today.getFullYear() - dob.getFullYear();
                if (age < 10 || age > 120) {
                    alert("Please enter a valid date of birth (Age 10-120).");
                    return;
                }
            }
            if (height && (height < 50 || height > 300)) {
                alert("Please enter a valid height in cm (50-300).");
                return;
            }
            if (weight && (weight < 20 || weight > 500)) {
                alert("Please enter a valid weight in kg (20-500).");
                return;
            }
        }

        if (currentStep === 3) {
            const goal = document.getElementById('profile-goal').value;
            const targetWeightInput = document.getElementById('profile-target-weight');
            const targetWeight = parseFloat(targetWeightInput.value);
            const currentWeight = parseFloat(document.getElementById('profile-weight').value);

            // Require target weight for everything EXCEPT "Maintain"
            if (goal !== 'Maintain' && targetWeightInput.hasAttribute('required') && !targetWeight) {
                targetWeightInput.style.borderColor = '#f85149';
                valid = false;
                alert("Please enter a Target Weight for your goal.");
                return;
            }

            if (goal === 'Lose Weight' && targetWeight && currentWeight) {
                if (targetWeight >= currentWeight) {
                    alert("For 'Lose Weight', your target must be lower than your current weight.");
                    return;
                }
            }
            if (goal === 'Build Muscle' && targetWeight && currentWeight) {
                if (targetWeight <= currentWeight) {
                    alert("For 'Build Muscle', your target must be higher than your current weight.");
                    return;
                }
            }
        }

        if (currentStep === 5) {
            const sport = document.getElementById('profile-sport').value;
            if (sport === 'Gym') {
                const targetDays = parseInt(document.getElementById('profile-days').value) || 0;
                // Only validate if we have input fields (some sports might not)
                const inputs = document.querySelectorAll('.split-day-input');
                if (inputs.length > 0) {
                    let workoutCount = 0;
                    inputs.forEach(input => {
                        const dayName = input.value.trim().toLowerCase();
                        if (dayName && dayName !== 'rest' && dayName !== 'rest day') {
                            workoutCount++;
                        }
                    });

                    if (workoutCount !== targetDays) {
                        alert(`You selected ${targetDays} workout days per week, but your schedule defines ${workoutCount} workouts.\n\nPlease ensure you have exactly ${targetDays} workout days defined (mark others as "Rest").`);
                        return;
                    }
                }
            }
        }

        if (currentStep < totalSteps) {
            currentStep++;
            showStep(currentStep);
            // ── PostHog: Track onboarding step ──
            if (typeof posthog !== 'undefined') {
                posthog.capture('onboarding_step_viewed', { step: currentStep, total_steps: totalSteps });
            }
            // Trigger calc if moving to step 6
            if (currentStep === 6) estimateCalories();
        }
    });

    wizardBackBtn.addEventListener('click', () => {
        if (currentStep > 1) {
            currentStep--;
            showStep(currentStep);
        }
    });

    onboardingForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        // Final Validation (Step 6)
        const calories = parseInt(document.getElementById('profile-calories').value);
        if (calories && (calories < 500 || calories > 10000)) {
            alert("Please enter a realistic daily calorie estimate (500 - 10,000).");
            return;
        }

        const userId = window.app.userId;
        if (!userId) return;

        // Collect Split Data
        const splitInputs = document.querySelectorAll('.split-day-input');
        const splitSchedule = Array.from(splitInputs).map(input => input.value).filter(val => val.trim() !== "");

        // Collect 1RM Data
        const rmRows = document.querySelectorAll('.rm-record-row');
        const oneRmRecords = [];
        rmRows.forEach(row => {
            const exercise = row.querySelector('.rm-exercise-input').value.trim();
            const weight = parseFloat(row.querySelector('.rm-weight-input').value);
            if (exercise && !isNaN(weight)) {
                oneRmRecords.push({
                    exercise_name: exercise,
                    weight_kg: weight
                });
            }
        });

        const formData = {
            user_id: userId,
            name: document.getElementById('profile-name').value,
            gender: document.getElementById('profile-gender').value,
            dob: document.getElementById('profile-dob').value,
            height_cm: parseInt(document.getElementById('profile-height').value),
            weight_kg: parseFloat(document.getElementById('profile-weight').value),
            target_weight_kg: parseFloat(document.getElementById('profile-target-weight').value) || null,
            fitness_goal: document.getElementById('profile-goal').value,
            experience_level: document.getElementById('profile-experience').value,
            workout_days_per_week: parseInt(document.getElementById('profile-days').value),

            // New Fields
            sport_type: document.getElementById('profile-sport').value,
            equipment_access: document.getElementById('profile-equipment').value, // Might be hidden but value remains
            equipment_list: [...selectedEquipment],
            split_schedule: splitSchedule,
            one_rm_records: oneRmRecords,

            typical_diet_type: document.getElementById('profile-diet-type').value,
            typical_daily_calories: parseInt(document.getElementById('profile-calories').value),
            allergies: document.getElementById('profile-allergies').value || "None"
        };

        // If not Gym, wipe split schedule? Or keep as generic?
        if (formData.sport_type !== 'Gym') {
            formData.split_schedule = [];
            formData.equipment_list = [];
            // User requested "equipment is significant only in gym sports". 
            // So we can clear it or set based on logic. Let's keep it simple.
        }

        try {
            wizardSubmitBtn.innerText = "Saving...";
            const response = await fetch('/api/profile', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData)
            });

            if (!response.ok) throw new Error("Failed to save profile");

            const resData = await response.json();

            // Success
            onboardingOverlay.classList.add('hidden');

            // ── PostHog: Track onboarding/profile save completed ──
            if (typeof posthog !== 'undefined') {
                posthog.capture('onboarding_completed', {
                    fitness_goal: formData.fitness_goal,
                    experience_level: formData.experience_level,
                    sport_type: formData.sport_type,
                    equipment_access: formData.equipment_access,
                    workout_days: formData.workout_days_per_week,
                    has_1rm_records: (formData.one_rm_records || []).length > 0,
                    equipment_count: (formData.equipment_list || []).length,
                    diet_type: formData.typical_diet_type,
                });
                // Set person properties for segmentation
                posthog.setPersonProperties({
                    name: formData.name,
                    fitness_goal: formData.fitness_goal,
                    experience_level: formData.experience_level,
                    sport_type: formData.sport_type,
                    equipment_access: formData.equipment_access,
                });
            }

            let msg = `Profile saved! Welcome, ${formData.name}.`;
            if (resData.targets) {
                msg += `\nCalorie Target: ${resData.targets.daily_calorie_target} kcal`;
            }
            alert(msg);

        } catch (error) {
            console.error("Profile Save Error:", error);
            alert("Error saving profile: " + error.message);
            wizardSubmitBtn.innerText = "Finish";
        }
    });

    async function checkProfile(userId) {
        try {
            const res = await fetch(`/api/profile/${userId}`);
            const profile = await res.json();

            // If empty or missing name, show onboarding
            if (!profile || !profile.name) {
                console.log("Profile incomplete, showing onboarding.");
                onboardingOverlay.classList.remove('hidden');
                currentStep = 1;
                showStep(1);
                // Init split editor
                renderSplitEditor(splitTemplates['PPL']);
            } else {
                console.log("Profile found:", profile.name);
                // Update Header
                const headerUsername = document.getElementById('header-username');
                const profileSection = document.getElementById('profile-section');
                if (headerUsername && profileSection) {
                    headerUsername.innerText = profile.name;
                    profileSection.classList.remove('hidden');
                    profileSection.style.display = 'flex';
                }
            }
        } catch (e) {
            console.error("Error checking profile:", e);
        }
    }

    // Settings Button Logic
    const settingsBtn = document.getElementById('settings-btn');
    if (settingsBtn) {
        settingsBtn.addEventListener('click', async () => {
            const userId = window.app.userId;
            if (!userId) return;
            // ── PostHog: Track profile settings opened ──
            if (typeof posthog !== 'undefined') posthog.capture('profile_settings_opened');

            try {
                // Fetch current data
                const res = await fetch(`/api/profile/${userId}`);
                const profile = await res.json();

                if (profile) {
                    // Populate Form
                    document.getElementById('profile-name').value = profile.name || "";
                    document.getElementById('profile-gender').value = profile.gender || "Male";
                    document.getElementById('profile-dob').value = profile.dob || "";
                    document.getElementById('profile-height').value = profile.height_cm || "";
                    document.getElementById('profile-weight').value = profile.weight_kg || ""; // Note: this might be old weight, but ok for profile edit
                    document.getElementById('profile-target-weight').value = profile.target_weight_kg || "";
                    document.getElementById('profile-goal').value = profile.fitness_goal || "Maintain";
                    document.getElementById('profile-experience').value = profile.experience_level || "Beginner";
                    document.getElementById('profile-days').value = profile.workout_days_per_week || 3;

                    document.getElementById('profile-sport').value = profile.sport_type || "Gym";
                    // Trigger change to show/hide options
                    profileSport.dispatchEvent(new Event('change'));

                    if (profile.sport_type === 'Gym') {
                        document.getElementById('profile-equipment').value = profile.equipment_access || "Gym";

                        // Pre-fill Equipment Chips
                        selectedEquipment.clear();
                        if (profile.equipment_list && profile.equipment_list.length > 0) {
                            profile.equipment_list.forEach(name => selectedEquipment.add(name));
                        }
                        renderEquipmentChips(profile.equipment_access || "Gym");

                        // Pre-fill RM Editor
                        if (profile.one_rm_records) {
                            renderRMEditor(profile.one_rm_records);
                        } else {
                            renderRMEditor([]);
                        }

                        // Pre-fill Split Editor
                        if (profile.split_schedule && profile.split_schedule.length > 0) {
                            document.getElementById('profile-split-template').value = "Custom";
                            renderSplitEditor(profile.split_schedule);
                        } else {
                            renderSplitEditor(splitTemplates['PPL']);
                        }
                    }

                    document.getElementById('profile-diet-type').value = profile.typical_diet_type || "Balanced";
                    document.getElementById('profile-calories').value = profile.typical_daily_calories || "";
                    document.getElementById('profile-allergies').value = profile.allergies || "";

                    // Show Wizard
                    document.getElementById('wizard-title').innerText = "Update Profile";
                    onboardingOverlay.classList.remove('hidden');
                    currentStep = 1;
                    showStep(1);
                }
            } catch (e) {
                console.error("Error fetching profile for edit:", e);
            }
        });
    }

    // Auth State Listener
    let lastUserId = null;
    sbClient.auth.onAuthStateChange((event, session) => {
        console.log("Auth Event:", event);

        if (session) {
            // Only trigger full reload if the user actually changed or just initialized
            if (lastUserId !== session.user.id) {
                lastUserId = session.user.id;

                // ── PostHog: Identify user on auth ──
                if (typeof posthog !== 'undefined') {
                    posthog.identify(session.user.id, {
                        email: session.user.email,
                        auth_provider: session.user.app_metadata?.provider || 'email',
                    });
                }

                // User is signed in
                authOverlay.classList.add('hidden');
                window.app.setUserId(session.user.id);
                localStorage.setItem('nutrisync_user_id', session.user.id);

                // Load history for this user
                window.app.loadHistory();
                logoutBtn.style.display = "flex";
                if (liveCoachToggleBtn) liveCoachToggleBtn.classList.remove('hidden');

                // Check Profile for Onboarding
                checkProfile(session.user.id);
            }
        } else {
            // User is signed out
            if (lastUserId !== null) {
                // ── PostHog: Reset on logout ──
                if (typeof posthog !== 'undefined') posthog.reset();
                lastUserId = null;
                authOverlay.classList.remove('hidden');
                window.app.setUserId(null);
                window.app.clearChat();
                logoutBtn.style.display = "none";
                if (liveCoachToggleBtn) liveCoachToggleBtn.classList.add('hidden');
                // Also hide onboarding if user logs out mid-wizard
                onboardingOverlay.classList.add('hidden');
                // Hide workout tracker on logout
                const wtOverlay = document.getElementById('workout-tracker-overlay');
                if (wtOverlay) wtOverlay.classList.add('hidden');
            }
        }
    });

    // ═══════════════════════════════════════════════════════════════════════════
    // WORKOUT TRACKER MODULE
    // ═══════════════════════════════════════════════════════════════════════════
    const workoutTrackerToggleBtn = document.getElementById('workout-tracker-toggle-btn');
    const workoutTrackerOverlay = document.getElementById('workout-tracker-overlay');
    const closeTrackerBtn = document.getElementById('close-tracker-btn');

    class WorkoutTracker {
        constructor() {
            this.userId = null;
            this.planData = null;       // { split_name, plan: [...] }
            this.currentDay = null;     // active split day tab name
            this.progressData = null;   // cached per-exercise progress
            this.allProgressData = null; // cached all-exercises summary
            this.muscleVolumeData = null;
            this.weekOffset = 0;
            this.e1rmChart = null;      // Chart.js instance
            this.volumeChart = null;    // Chart.js instance
            this.exerciseHistory = {};  // cache: { exerciseName: [...sets] }

            this._bindTabs();
            this._bindPlanControls();
            this._bindProgressControls();
            this._bindVolumeControls();
        }

        setUserId(id) {
            this.userId = id;
        }

        // ── Tab Navigation ──────────────────────────────────────────────────
        _bindTabs() {
            document.querySelectorAll('.wt-tab').forEach(tab => {
                tab.addEventListener('click', () => {
                    document.querySelectorAll('.wt-tab').forEach(t => t.classList.remove('active'));
                    document.querySelectorAll('.wt-tab-content').forEach(c => c.classList.remove('active'));
                    tab.classList.add('active');
                    const target = tab.getAttribute('data-tab');
                    document.getElementById(`wt-${target}-tab`).classList.add('active');
                    // Lazy-load data on tab switch
                    // ── PostHog: Track workout tracker tab switch ──
                    if (typeof posthog !== 'undefined') {
                        posthog.capture('workout_tracker_tab_viewed', { tab: target });
                    }
                    if (target === 'plan') this.loadPlan();
                    if (target === 'progress') this.loadProgress();
                    if (target === 'volume') this.loadMuscleVolume();
                });
            });
        }

        // ═══════════════════ PLAN TAB ═══════════════════

        _bindPlanControls() {
            const regenBtn = document.getElementById('wt-regenerate-btn');
            if (regenBtn) {
                regenBtn.addEventListener('click', () => {
                    // Send a message to the AI coach asking to regenerate
                    if (window.app && window.app.userId) {
                        workoutTrackerOverlay.classList.add('hidden');
                        const input = document.getElementById('user-input');
                        if (input) {
                            input.value = 'Please regenerate my workout plan for all split days based on my current profile, equipment, and 1RM records.';
                            window.app.sendMessage();
                        }
                    }
                });
            }
        }

        async loadPlan() {
            if (!this.userId) return;
            try {
                const res = await fetch(`/api/workout-plan/${this.userId}`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                this.planData = await res.json();
                this._renderDayTabs();
            } catch (e) {
                console.error('WorkoutTracker: loadPlan failed', e);
            }
        }

        _renderDayTabs() {
            const tabsContainer = document.getElementById('wt-day-tabs');
            tabsContainer.innerHTML = '';

            if (!this.planData || !this.planData.plan || this.planData.plan.length === 0) {
                document.getElementById('wt-exercise-list').innerHTML = `
                    <div class="wt-empty-state">
                        <p>No workout plan yet.</p>
                        <p style="color:#8b949e;font-size:0.85rem;">Ask the AI coach to generate a plan for you, or click Regenerate Plan.</p>
                    </div>`;
                document.getElementById('wt-volume-summary').style.display = 'none';
                return;
            }

            // Extract unique day names preserving order
            const days = [];
            const seen = new Set();
            this.planData.plan.forEach(ex => {
                if (!seen.has(ex.split_day_name)) {
                    seen.add(ex.split_day_name);
                    days.push(ex.split_day_name);
                }
            });

            days.forEach((day, idx) => {
                const btn = document.createElement('button');
                btn.className = 'wt-day-tab' + (idx === 0 ? ' active' : '');
                btn.textContent = day;
                btn.addEventListener('click', () => {
                    tabsContainer.querySelectorAll('.wt-day-tab').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    this.currentDay = day;
                    this._renderExercises(day);
                });
                tabsContainer.appendChild(btn);
            });

            this.currentDay = days[0];
            this._renderExercises(days[0]);
        }

        _renderExercises(dayName) {
            const list = document.getElementById('wt-exercise-list');
            const summaryEl = document.getElementById('wt-volume-summary');
            const exercises = this.planData.plan.filter(e => e.split_day_name === dayName);

            if (exercises.length === 0) {
                list.innerHTML = '<div class="wt-empty-state"><p>No exercises for this day.</p></div>';
                summaryEl.style.display = 'none';
                return;
            }

            list.innerHTML = '';
            const muscleSetCount = {};  // Muscle → total sets

            // Group by superset_group
            let currentSuperset = null;

            exercises.forEach(ex => {
                const card = document.createElement('div');
                card.className = 'wt-exercise-card';
                card.setAttribute('data-exercise', ex.exercise_name);

                const isCompound = (ex.exercise_type || '').toLowerCase() === 'compound';
                const typeLabel = isCompound ? '🏋️ Compound' : '🎯 Isolation';
                const typeClass = isCompound ? 'wt-ex-type-compound' : 'wt-ex-type-isolation';

                const muscles = (ex.target_muscles || []).join(', ');
                const repRange = `${ex.sets}×${ex.rep_range_low}-${ex.rep_range_high}`;
                const loadText = ex.load_percentage ? ` @ ${Math.round(ex.load_percentage * 100)}% 1RM` : '';
                const restText = ex.rest_seconds ? `Rest: ${ex.rest_seconds >= 120 ? (ex.rest_seconds / 60) + ' min' : ex.rest_seconds + 's'}` : '';

                // Superset badge
                let supersetHtml = '';
                if (ex.superset_group != null) {
                    supersetHtml = `<span class="wt-superset-badge">🔗 Superset ${ex.superset_group}</span>`;
                }

                card.innerHTML = `
                    <div class="wt-ex-top-row">
                        <span class="wt-ex-order">${ex.exercise_order}</span>
                        <span class="wt-ex-name">${ex.exercise_name}</span>
                        <span class="wt-ex-type-badge ${typeClass}">${typeLabel}</span>
                    </div>
                    <div class="wt-ex-detail-row">
                        <span class="wt-ex-detail"><strong>${repRange}</strong>${loadText}</span>
                        ${restText ? `<span class="wt-ex-detail">${restText}</span>` : ''}
                        ${supersetHtml}
                    </div>
                    <div class="wt-ex-muscles">Muscles: <span>${muscles}</span></div>
                    ${ex.notes ? `<div class="wt-ex-detail" style="margin-top:4px;font-size:0.8rem;color:rgba(255,255,255,0.4);">📝 ${ex.notes}</div>` : ''}
                    <div class="wt-ex-ghost">
                        <div class="wt-ex-ghost-title">Last Session</div>
                        <div class="wt-ex-ghost-sets" data-exercise-ghost="${ex.exercise_name}">Loading...</div>
                    </div>
                `;

                // Tap to expand (show ghost data / previous session)
                card.addEventListener('click', () => {
                    const wasExpanded = card.classList.contains('expanded');
                    // Collapse all
                    list.querySelectorAll('.wt-exercise-card').forEach(c => c.classList.remove('expanded'));
                    if (!wasExpanded) {
                        card.classList.add('expanded');
                        this._loadGhostData(ex.exercise_name, card.querySelector(`[data-exercise-ghost="${ex.exercise_name}"]`));
                    }
                });

                list.appendChild(card);

                // Count volume
                (ex.target_muscles || []).forEach(m => {
                    const normalize = m.replace(/_/g, ' ').trim();
                    muscleSetCount[normalize] = (muscleSetCount[normalize] || 0) + (ex.sets || 0);
                });
            });

            // Volume summary
            if (Object.keys(muscleSetCount).length > 0) {
                const parts = Object.entries(muscleSetCount)
                    .map(([m, s]) => `<strong>${this._capitalize(m)}</strong> ${s} sets`)
                    .join(' &nbsp;|&nbsp; ');
                summaryEl.innerHTML = `📊 Volume Summary: ${parts}`;
                summaryEl.style.display = 'block';
            } else {
                summaryEl.style.display = 'none';
            }
        }

        async _loadGhostData(exerciseName, el) {
            if (!this.userId || !el) return;
            // Check cache
            if (this.exerciseHistory[exerciseName]) {
                this._renderGhostSets(this.exerciseHistory[exerciseName], el);
                return;
            }
            try {
                const res = await fetch(`/api/progress/${this.userId}?exercise=${encodeURIComponent(exerciseName)}&weeks=4`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                // Pick the latest week's data from weekly_trend
                if (data.weekly_trend && data.weekly_trend.length > 0) {
                    this.exerciseHistory[exerciseName] = data;
                    this._renderGhostSets(data, el);
                } else {
                    el.textContent = 'No previous session data.';
                }
            } catch (e) {
                el.textContent = 'Could not load history.';
                console.error('Ghost load error:', e);
            }
        }

        _renderGhostSets(data, el) {
            if (!data || !data.weekly_trend || data.weekly_trend.length === 0) {
                el.textContent = 'No previous session data.';
                return;
            }
            const latest = data.weekly_trend[data.weekly_trend.length - 1];
            const parts = [];
            if (latest.best_weight) parts.push(`Best: ${latest.best_weight}kg`);
            if (latest.best_reps) parts.push(`× ${latest.best_reps} reps`);
            if (latest.total_volume) parts.push(`Vol: ${Math.round(latest.total_volume).toLocaleString()}kg`);
            if (latest.total_sets) parts.push(`${latest.total_sets} sets`);
            el.textContent = parts.length > 0 ? parts.join(' · ') : 'No data.';
        }

        // ═══════════════════ PROGRESS TAB ═══════════════════

        _bindProgressControls() {
            const exerciseSelect = document.getElementById('wt-exercise-select');
            const weeksSelect = document.getElementById('wt-progress-weeks');

            if (exerciseSelect) {
                exerciseSelect.addEventListener('change', () => this.loadProgress());
            }
            if (weeksSelect) {
                weeksSelect.addEventListener('change', () => this.loadProgress());
            }
        }

        async loadProgress() {
            if (!this.userId) return;
            const exercise = document.getElementById('wt-exercise-select').value;
            const weeks = parseInt(document.getElementById('wt-progress-weeks').value) || 8;

            try {
                let url = `/api/progress/${this.userId}?weeks=${weeks}`;
                if (exercise) url += `&exercise=${encodeURIComponent(exercise)}`;

                const res = await fetch(url);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();

                if (exercise) {
                    this.progressData = data;
                    document.getElementById('wt-single-exercise-view').style.display = 'block';
                    document.getElementById('wt-all-exercises-view').style.display = 'none';
                    this._renderE1RMChart(data);
                    this._renderVolumeChart(data);
                    this._renderSessionHistory(data);
                    this._renderPRRecords(data);
                } else {
                    this.allProgressData = data;
                    document.getElementById('wt-single-exercise-view').style.display = 'none';
                    document.getElementById('wt-all-exercises-view').style.display = 'block';
                    this._renderAllExercises(data);
                    this._populateExerciseDropdown(data);
                }
            } catch (e) {
                console.error('WorkoutTracker: loadProgress failed', e);
            }
        }

        _populateExerciseDropdown(data) {
            const select = document.getElementById('wt-exercise-select');
            const currentValue = select.value;
            // Preserve "All" option
            const existingOptions = new Set();
            select.querySelectorAll('option').forEach(o => existingOptions.add(o.value));

            if (data.exercises && data.exercises.length > 0) {
                data.exercises.forEach(ex => {
                    if (!existingOptions.has(ex.exercise)) {
                        const opt = document.createElement('option');
                        opt.value = ex.exercise;
                        opt.textContent = ex.exercise;
                        select.appendChild(opt);
                    }
                });
            }
            select.value = currentValue;
        }

        _renderE1RMChart(data) {
            const canvas = document.getElementById('wt-e1rm-chart');
            if (!canvas) return;

            if (this.e1rmChart) {
                this.e1rmChart.destroy();
                this.e1rmChart = null;
            }

            const trend = data.weekly_trend || [];
            if (trend.length === 0) {
                canvas.parentElement.style.display = 'none';
                return;
            }
            canvas.parentElement.style.display = 'block';

            const labels = trend.map(w => w.week_start || '');
            const e1rmValues = trend.map(w => w.best_e1rm || 0);

            this.e1rmChart = new Chart(canvas, {
                type: 'line',
                data: {
                    labels,
                    datasets: [{
                        label: 'Est. 1RM (kg)',
                        data: e1rmValues,
                        borderColor: '#58a6ff',
                        backgroundColor: 'rgba(88,166,255,0.1)',
                        borderWidth: 2.5,
                        pointBackgroundColor: '#58a6ff',
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        tension: 0.3,
                        fill: true,
                    }]
                },
                options: this._chartOptions('kg')
            });
        }

        _renderVolumeChart(data) {
            const canvas = document.getElementById('wt-volume-chart');
            if (!canvas) return;

            if (this.volumeChart) {
                this.volumeChart.destroy();
                this.volumeChart = null;
            }

            const trend = data.weekly_trend || [];
            if (trend.length === 0) {
                canvas.parentElement.style.display = 'none';
                return;
            }
            canvas.parentElement.style.display = 'block';

            const labels = trend.map(w => w.week_start || '');
            const volValues = trend.map(w => w.total_volume || 0);

            this.volumeChart = new Chart(canvas, {
                type: 'bar',
                data: {
                    labels,
                    datasets: [{
                        label: 'Volume (kg)',
                        data: volValues,
                        backgroundColor: 'rgba(63,185,80,0.5)',
                        borderColor: '#3fb950',
                        borderWidth: 1.5,
                        borderRadius: 6,
                    }]
                },
                options: this._chartOptions('kg')
            });
        }

        _chartOptions(unit) {
            return {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(22,27,34,0.95)',
                        titleColor: '#c9d1d9',
                        bodyColor: '#8b949e',
                        borderColor: 'rgba(255,255,255,0.1)',
                        borderWidth: 1,
                        cornerRadius: 8,
                        padding: 10,
                    }
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(255,255,255,0.04)' },
                        ticks: { color: '#8b949e', font: { size: 11 } }
                    },
                    y: {
                        grid: { color: 'rgba(255,255,255,0.04)' },
                        ticks: {
                            color: '#8b949e',
                            font: { size: 11 },
                            callback: (v) => `${v}${unit}`
                        }
                    }
                }
            };
        }

        _renderSessionHistory(data) {
            const container = document.getElementById('wt-session-history');
            if (!container) return;

            const trend = data.weekly_trend || [];
            if (trend.length === 0) {
                container.innerHTML = '';
                return;
            }

            // Show last 5 weeks of data as "sessions"
            const recentWeeks = trend.slice(-5).reverse();
            let html = '<h3 class="wt-chart-title" style="margin-bottom:10px;">📅 Session History</h3>';

            recentWeeks.forEach(w => {
                const prHtml = w.has_pr ? ' <span class="wt-all-ex-pr-badge">🏆 PR</span>' : '';
                html += `
                    <div class="wt-session-card">
                        <div class="wt-session-date">Week of ${w.week_start}${prHtml}</div>
                        <div class="wt-session-sets">
                            <span class="wt-set-pill${w.has_pr ? ' wt-pr-set' : ''}">Best: ${w.best_weight || 0}kg × ${w.best_reps || 0}</span>
                            <span class="wt-set-pill">Vol: ${Math.round(w.total_volume || 0).toLocaleString()}kg</span>
                            <span class="wt-set-pill">${w.total_sets || 0} sets</span>
                            ${w.best_e1rm ? `<span class="wt-set-pill">e1RM: ${w.best_e1rm}kg</span>` : ''}
                        </div>
                    </div>`;
            });

            container.innerHTML = html;
        }

        _renderPRRecords(data) {
            const container = document.getElementById('wt-pr-records');
            if (!container) return;

            const pr = data.all_time_pr;
            if (!pr || (!pr.best_weight && !pr.best_volume_set && !pr.best_e1rm)) {
                container.style.display = 'none';
                return;
            }
            container.style.display = 'block';

            let html = '<div class="wt-pr-title">🏆 Personal Records</div>';

            if (pr.best_e1rm) {
                html += `<div class="wt-pr-item"><span class="wt-pr-label">Best Est. 1RM:</span> <span class="wt-pr-value">${pr.best_e1rm}kg</span></div>`;
            }
            if (pr.best_weight) {
                html += `<div class="wt-pr-item"><span class="wt-pr-label">Best Set:</span> <span class="wt-pr-value">${pr.best_weight.weight_kg}kg × ${pr.best_weight.reps}</span></div>`;
            }
            if (pr.best_volume_set) {
                html += `<div class="wt-pr-item"><span class="wt-pr-label">Best Volume (set):</span> <span class="wt-pr-value">${Math.round(pr.best_volume_set.volume_load || 0).toLocaleString()}kg</span></div>`;
            }

            container.innerHTML = html;
        }

        _renderAllExercises(data) {
            const container = document.getElementById('wt-all-exercises-list');
            if (!container) return;

            const exercises = data.exercises || [];
            if (exercises.length === 0) {
                container.innerHTML = `
                    <div class="wt-empty-state">
                        <p>No exercise data yet.</p>
                        <p style="color:#8b949e;font-size:0.85rem;">Start logging sets via the AI coach to see your progress.</p>
                    </div>`;
                return;
            }

            container.innerHTML = '';
            exercises.forEach(ex => {
                const card = document.createElement('div');
                card.className = 'wt-all-ex-card';

                const prBadge = ex.pr_count > 0
                    ? `<span class="wt-all-ex-pr-badge">🏆 ${ex.pr_count}</span>`
                    : '';

                card.innerHTML = `
                    <div class="wt-all-ex-name">${ex.exercise}${prBadge}</div>
                    <div class="wt-all-ex-stats">
                        <div class="wt-all-ex-stat">
                            <span class="wt-all-ex-stat-val">${ex.total_sets}</span>
                            sets
                        </div>
                        <div class="wt-all-ex-stat">
                            <span class="wt-all-ex-stat-val">${Math.round(ex.total_volume).toLocaleString()}</span>
                            vol (kg)
                        </div>
                        <div class="wt-all-ex-stat">
                            <span class="wt-all-ex-stat-val">${ex.best_weight}kg</span>
                            best
                        </div>
                    </div>
                `;

                // Click to filter to this exercise
                card.addEventListener('click', () => {
                    const select = document.getElementById('wt-exercise-select');
                    // Ensure option exists
                    let found = false;
                    select.querySelectorAll('option').forEach(o => {
                        if (o.value === ex.exercise) found = true;
                    });
                    if (!found) {
                        const opt = document.createElement('option');
                        opt.value = ex.exercise;
                        opt.textContent = ex.exercise;
                        select.appendChild(opt);
                    }
                    select.value = ex.exercise;
                    this.loadProgress();
                });

                container.appendChild(card);
            });
        }

        // ═══════════════════ VOLUME HEATMAP TAB ═══════════════════

        _bindVolumeControls() {
            const prevBtn = document.getElementById('wt-week-prev');
            const nextBtn = document.getElementById('wt-week-next');

            if (prevBtn) {
                prevBtn.addEventListener('click', () => {
                    this.weekOffset++;
                    this.loadMuscleVolume();
                });
            }
            if (nextBtn) {
                nextBtn.addEventListener('click', () => {
                    if (this.weekOffset > 0) {
                        this.weekOffset--;
                        this.loadMuscleVolume();
                    }
                });
            }
        }

        async loadMuscleVolume() {
            if (!this.userId) return;
            this._updateWeekLabel();

            try {
                const res = await fetch(`/api/muscle-volume/${this.userId}?week_offset=${this.weekOffset}`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                this.muscleVolumeData = await res.json();
                this._renderMuscleBars();
            } catch (e) {
                console.error('WorkoutTracker: loadMuscleVolume failed', e);
            }
        }

        _updateWeekLabel() {
            const label = document.getElementById('wt-week-label');
            if (!label) return;
            if (this.weekOffset === 0) label.textContent = 'This Week';
            else if (this.weekOffset === 1) label.textContent = 'Last Week';
            else label.textContent = `${this.weekOffset}w ago`;
        }

        _renderMuscleBars() {
            const container = document.getElementById('wt-muscle-bars');
            if (!container) return;

            const volumes = (this.muscleVolumeData && this.muscleVolumeData.muscle_volumes) || [];
            if (volumes.length === 0) {
                container.innerHTML = `
                    <div class="wt-empty-state">
                        <p>No volume data yet.</p>
                        <p style="color:#8b949e;font-size:0.85rem;">Log exercise sets to see your weekly muscle volume.</p>
                    </div>`;
                return;
            }

            // Get volume targets from user experience level
            const targets = this._getVolumeTargets();
            container.innerHTML = '';

            // Sort muscles largest target first
            const sortedMuscles = this._getAllMuscleGroups();
            const volumeMap = {};
            volumes.forEach(v => {
                const key = (v.muscle_group || '').toLowerCase().replace(/\s+/g, '_');
                volumeMap[key] = v.completed_sets || 0;
            });

            sortedMuscles.forEach(muscle => {
                const completed = volumeMap[muscle] || 0;
                const target = targets[muscle] || targets.default || 12;
                const pct = Math.min((completed / target) * 100, 100);
                const overPct = completed > target ? 100 : pct;

                let colorClass = 'wt-vol-green';
                if (completed > target) colorClass = 'wt-vol-over';
                else if (pct < 50) colorClass = 'wt-vol-red';
                else if (pct < 80) colorClass = 'wt-vol-yellow';

                const row = document.createElement('div');
                row.className = 'wt-muscle-row';
                row.innerHTML = `
                    <span class="wt-muscle-name">${this._capitalize(muscle.replace(/_/g, ' '))}</span>
                    <div class="wt-muscle-bar-track">
                        <div class="wt-muscle-bar-fill ${colorClass}" style="width:${overPct}%"></div>
                    </div>
                    <span class="wt-muscle-count">${completed}/${target} sets</span>
                `;
                container.appendChild(row);
            });
        }

        _getVolumeTargets() {
            // Default to intermediate targets. Could be enhanced to fetch user's experience level.
            return {
                default: 12,
                chest: 16, back: 18, quads: 16, hamstrings: 12,
                shoulders: 14, front_delts: 8, side_delts: 10, rear_delts: 8,
                biceps: 12, triceps: 12, glutes: 14, calves: 8, core: 10,
                forearms: 6, traps: 8
            };
        }

        _getAllMuscleGroups() {
            return [
                'chest', 'back', 'quads', 'hamstrings', 'shoulders',
                'biceps', 'triceps', 'glutes', 'calves', 'core',
                'front_delts', 'side_delts', 'rear_delts', 'forearms', 'traps'
            ];
        }

        // ── Utilities ────────────────────────────────────────────────────────
        _capitalize(str) {
            return str.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
        }

        // Public: called when overlay opens
        async open() {
            if (!this.userId) return;
            // Load the active tab's data
            const activeTab = document.querySelector('.wt-tab.active');
            const tab = activeTab ? activeTab.getAttribute('data-tab') : 'plan';
            if (tab === 'plan') await this.loadPlan();
            else if (tab === 'progress') await this.loadProgress();
            else if (tab === 'volume') await this.loadMuscleVolume();
        }
    }

    // Initialize the tracker
    const tracker = new WorkoutTracker();
    window.workoutTracker = tracker;

    // Bind overlay open/close
    if (workoutTrackerToggleBtn) {
        workoutTrackerToggleBtn.addEventListener('click', () => {
            tracker.setUserId(window.app.userId);
            workoutTrackerOverlay.classList.remove('hidden');
            tracker.open();
            // ── PostHog: Track workout tracker opened ──
            if (typeof posthog !== 'undefined') posthog.capture('workout_tracker_opened');
        });
    }
    if (closeTrackerBtn) {
        closeTrackerBtn.addEventListener('click', () => {
            workoutTrackerOverlay.classList.add('hidden');
        });
    }

    // Show workout tracker button when auth succeeds (same pattern as live coach)
    const origAuthCheck = sbClient.auth.onAuthStateChange;
    // The button visibility is already handled above in the auth state listener,
    // but we need to ensure it shows. Patch into the existing logic:
    const wtBtnRef = document.getElementById('workout-tracker-toggle-btn');
    if (wtBtnRef) {
        // Observe auth state for button visibility
        const observer = new MutationObserver(() => {
            if (liveCoachToggleBtn && !liveCoachToggleBtn.classList.contains('hidden')) {
                wtBtnRef.classList.remove('hidden');
            } else {
                wtBtnRef.classList.add('hidden');
            }
        });
        observer.observe(liveCoachToggleBtn, { attributes: true, attributeFilter: ['class'] });
    }
});
