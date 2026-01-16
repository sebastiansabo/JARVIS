/**
 * J.A.R.V.I.S. Theme System
 * Applies theme settings including logo customization and dark/light mode across all pages
 */

(function() {
    'use strict';

    // Theme storage key (unified across all pages)
    const THEME_STORAGE_KEY = 'jarvisTheme';

    // Default logo settings
    const defaultLogo = {
        type: 'svg',
        svgUrl: '/static/img/jarvis-icon.svg',
        icon: 'bi-cpu',
        text: 'J.A.R.V.I.S.',
        imageUrl: ''
    };

    /**
     * Apply logo settings to the navbar brand element
     * @param {Object} logo - Logo settings object
     */
    function applyLogo(logo) {
        const navbarLogo = document.getElementById('navbarLogo');
        if (!navbarLogo) return;

        const settings = logo || defaultLogo;
        let html = '';

        switch (settings.type) {
            case 'svg':
                const svgUrl = settings.svgUrl || defaultLogo.svgUrl;
                html = `<span class="navbar-logo-icon" style="background-image: url('${svgUrl}');"></span> ${settings.text}`;
                break;
            case 'icon':
                html = `<i class="bi ${settings.icon}"></i> ${settings.text}`;
                break;
            case 'text':
                html = settings.text;
                break;
            case 'image':
                if (settings.imageUrl) {
                    html = `<img src="${settings.imageUrl}" alt="${settings.text}" style="max-height: 32px; vertical-align: middle;"> ${settings.text}`;
                } else {
                    html = settings.text;
                }
                break;
            default:
                html = `<span class="navbar-logo-icon"></span> ${defaultLogo.text}`;
        }

        navbarLogo.innerHTML = html;
    }

    /**
     * Load theme settings from API and apply logo
     */
    async function loadAndApplyTheme() {
        try {
            const res = await fetch('/api/themes/active');
            if (!res.ok) {
                console.warn('Could not load theme settings, using defaults');
                applyLogo(defaultLogo);
                return;
            }

            const data = await res.json();
            if (data.theme && data.theme.settings && data.theme.settings.logo) {
                applyLogo(data.theme.settings.logo);
            } else {
                applyLogo(defaultLogo);
            }
        } catch (err) {
            console.warn('Error loading theme:', err);
            applyLogo(defaultLogo);
        }
    }

    /**
     * Initialize dark/light theme toggle
     */
    function initThemeToggle() {
        const themeToggle = document.getElementById('themeToggle');
        if (!themeToggle) return;

        // Load saved theme preference and sync toggle state
        const savedTheme = localStorage.getItem(THEME_STORAGE_KEY);
        if (savedTheme === 'dark') {
            document.body.classList.add('dark-theme');
            themeToggle.checked = true;
        } else {
            document.body.classList.remove('dark-theme');
            themeToggle.checked = false;
        }

        // Theme toggle handler
        themeToggle.addEventListener('change', () => {
            if (themeToggle.checked) {
                document.body.classList.add('dark-theme');
                localStorage.setItem(THEME_STORAGE_KEY, 'dark');
            } else {
                document.body.classList.remove('dark-theme');
                localStorage.setItem(THEME_STORAGE_KEY, 'light');
            }
        });
    }

    /**
     * Apply saved theme immediately (before DOMContentLoaded for faster rendering)
     */
    function applyInitialTheme() {
        const savedTheme = localStorage.getItem(THEME_STORAGE_KEY);
        if (savedTheme === 'dark') {
            document.body.classList.add('dark-theme');
        }
    }

    // Apply theme immediately if body exists
    if (document.body) {
        applyInitialTheme();
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            applyInitialTheme();
            initThemeToggle();
            loadAndApplyTheme();
        });
    } else {
        initThemeToggle();
        loadAndApplyTheme();
    }

    // Expose functions globally for settings page to use
    window.JarvisTheme = {
        applyLogo: applyLogo,
        loadAndApplyTheme: loadAndApplyTheme,
        initThemeToggle: initThemeToggle,
        THEME_STORAGE_KEY: THEME_STORAGE_KEY
    };
})();
