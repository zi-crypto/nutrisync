/**
 * NutriSync i18n Engine
 * Lightweight client-side internationalization with RTL support.
 * Default language: English. Supports: en, ar.
 */
(function () {
    'use strict';

    const SUPPORTED_LANGS = ['en', 'ar'];
    const DEFAULT_LANG = 'en';
    const STORAGE_KEY = 'nutrisync_lang';

    let _strings = {};       // current locale strings
    let _fallback = {};      // English fallback
    let _currentLang = DEFAULT_LANG;
    let _ready = false;
    let _readyCallbacks = [];

    // ── Public API ──────────────────────────────────────────────────────────

    /**
     * Translate a key, with optional {placeholder} interpolation.
     * @param {string} key  - dot-notation key e.g. "wizard.label.name"
     * @param {Object} [params] - interpolation map e.g. { name: "Ziad" }
     * @returns {string}
     */
    window.t = function (key, params) {
        let str = _strings[key] || _fallback[key] || key;
        if (params) {
            Object.keys(params).forEach(k => {
                str = str.replace(new RegExp('\\{' + k + '\\}', 'g'), params[k]);
            });
        }
        return str;
    };

    /**
     * Get current language code.
     */
    window.getLang = function () {
        return _currentLang;
    };

    /**
     * Get text direction for current language.
     */
    window.getDir = function () {
        return _strings.dir || 'ltr';
    };

    /**
     * Switch language at runtime. Reloads strings and re-applies DOM translations.
     * @param {string} lang - 'en' or 'ar'
     */
    window.setLang = async function (lang) {
        if (!SUPPORTED_LANGS.includes(lang)) lang = DEFAULT_LANG;
        _currentLang = lang;
        localStorage.setItem(STORAGE_KEY, lang);

        await _loadLocale(lang);
        _applyDirection();
        _translateDOM();

        // Dispatch event so other modules (script.js, workout_coach.js) can react
        window.dispatchEvent(new CustomEvent('languagechange', { detail: { lang, dir: window.getDir() } }));
    };

    /**
     * Register a callback to run when i18n is ready.
     */
    window.onI18nReady = function (cb) {
        if (_ready) cb();
        else _readyCallbacks.push(cb);
    };

    // ── Internal ────────────────────────────────────────────────────────────

    async function _loadLocale(lang) {
        try {
            const resp = await fetch(`/static/locales/${lang}.json?v=${Date.now()}`);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            _strings = await resp.json();
        } catch (e) {
            console.warn(`[i18n] Failed to load ${lang}.json, falling back to en`, e);
            _strings = _fallback;
        }
    }

    function _applyDirection() {
        const dir = _strings.dir || 'ltr';
        const html = document.documentElement;
        html.setAttribute('dir', dir);
        html.setAttribute('lang', _currentLang);
    }

    /**
     * Walk the DOM and translate elements with data-i18n attributes:
     *   data-i18n="key"                → textContent
     *   data-i18n-placeholder="key"    → placeholder attribute
     *   data-i18n-title="key"          → title attribute
     *   data-i18n-html="key"           → innerHTML (use sparingly)
     */
    function _translateDOM() {
        // textContent
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            if (key) el.textContent = window.t(key);
        });

        // placeholder
        document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
            const key = el.getAttribute('data-i18n-placeholder');
            if (key) el.placeholder = window.t(key);
        });

        // title (tooltip)
        document.querySelectorAll('[data-i18n-title]').forEach(el => {
            const key = el.getAttribute('data-i18n-title');
            if (key) el.title = window.t(key);
        });

        // innerHTML (for select options with HTML entities, etc.)
        document.querySelectorAll('[data-i18n-html]').forEach(el => {
            const key = el.getAttribute('data-i18n-html');
            if (key) el.innerHTML = window.t(key);
        });
    }

    // ── Bootstrap ───────────────────────────────────────────────────────────

    async function _init() {
        // Determine initial language: localStorage > navigator > default
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored && SUPPORTED_LANGS.includes(stored)) {
            _currentLang = stored;
        } else {
            // Check browser language
            const browserLang = (navigator.language || '').slice(0, 2);
            _currentLang = SUPPORTED_LANGS.includes(browserLang) ? browserLang : DEFAULT_LANG;
        }

        // Always load English as fallback
        try {
            const enResp = await fetch(`/static/locales/en.json?v=${Date.now()}`);
            if (enResp.ok) _fallback = await enResp.json();
        } catch (e) {
            console.warn('[i18n] Could not load English fallback');
        }

        // Load active locale
        if (_currentLang !== 'en') {
            await _loadLocale(_currentLang);
        } else {
            _strings = _fallback;
        }

        _applyDirection();

        // Translate DOM once it's ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                _translateDOM();
                _markReady();
            });
        } else {
            _translateDOM();
            _markReady();
        }
    }

    function _markReady() {
        _ready = true;
        _readyCallbacks.forEach(cb => cb());
        _readyCallbacks = [];
    }

    // Start immediately (script is loaded in <head> or before body scripts)
    _init();
})();
