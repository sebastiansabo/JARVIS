/**
 * J.A.R.V.I.S. Custom Dialogs & Toasts
 * ====================================
 * Replaces native browser alert(), confirm(), prompt() with styled versions
 *
 * Usage:
 *   JarvisDialog.alert('Message here', { type: 'info' });
 *   JarvisDialog.confirm('Are you sure?').then(result => { ... });
 *   JarvisDialog.prompt('Enter value:').then(value => { ... });
 *   JarvisToast.success('Saved successfully!');
 */

const JarvisDialog = {
    /**
     * Show an alert dialog (replaces native alert())
     * @param {string} message - The message to display
     * @param {object} options - Optional configuration
     * @returns {Promise} Resolves when dialog is closed
     */
    alert(message, options = {}) {
        const config = {
            title: options.title || this._getDefaultTitle(options.type || 'info'),
            type: options.type || 'info',  // info, success, warning, error
            buttonText: options.buttonText || 'OK',
            buttonClass: options.buttonClass || 'jarvis-dialog-btn-primary',
            html: options.html || false  // If true, message is treated as HTML
        };

        // Convert newlines to <br> if not HTML mode
        const formattedMessage = config.html ? message : this._escapeHtml(message).replace(/\n/g, '<br>');

        return new Promise(resolve => {
            const overlay = this._createOverlay();
            const dialog = document.createElement('div');
            dialog.className = 'jarvis-dialog';
            dialog.innerHTML = `
                <div class="jarvis-dialog-header">
                    <div class="jarvis-dialog-icon ${config.type}">
                        <i class="bi ${this._getIcon(config.type)}"></i>
                    </div>
                    <h3 class="jarvis-dialog-title">${config.title}</h3>
                </div>
                <div class="jarvis-dialog-body">
                    <div class="jarvis-dialog-message">${formattedMessage}</div>
                </div>
                <div class="jarvis-dialog-footer">
                    <button class="jarvis-dialog-btn ${config.buttonClass}" data-action="ok">
                        ${config.buttonText}
                    </button>
                </div>
            `;

            overlay.appendChild(dialog);
            document.body.appendChild(overlay);

            // Focus the button
            setTimeout(() => {
                overlay.classList.add('show');
                dialog.querySelector('[data-action="ok"]').focus();
            }, 10);

            // Handle click
            const handleClose = () => {
                overlay.classList.remove('show');
                setTimeout(() => {
                    overlay.remove();
                    resolve();
                }, 200);
            };

            dialog.querySelector('[data-action="ok"]').addEventListener('click', handleClose);
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) handleClose();
            });

            // Handle Escape key
            const handleKey = (e) => {
                if (e.key === 'Escape' || e.key === 'Enter') {
                    handleClose();
                    document.removeEventListener('keydown', handleKey);
                }
            };
            document.addEventListener('keydown', handleKey);
        });
    },

    /**
     * Show a confirm dialog (replaces native confirm())
     * @param {string} message - The message to display
     * @param {object} options - Optional configuration
     * @returns {Promise<boolean>} Resolves with true (confirm) or false (cancel)
     */
    confirm(message, options = {}) {
        const config = {
            title: options.title || 'Confirm',
            type: options.type || 'confirm',
            confirmText: options.confirmText || 'Confirm',
            cancelText: options.cancelText || 'Cancel',
            confirmClass: options.confirmClass || 'jarvis-dialog-btn-primary',
            danger: options.danger || false
        };

        if (config.danger) {
            config.confirmClass = 'jarvis-dialog-btn-danger';
        }

        return new Promise(resolve => {
            const overlay = this._createOverlay();
            const dialog = document.createElement('div');
            dialog.className = 'jarvis-dialog';
            dialog.innerHTML = `
                <div class="jarvis-dialog-header">
                    <div class="jarvis-dialog-icon ${config.type}">
                        <i class="bi ${this._getIcon(config.type)}"></i>
                    </div>
                    <h3 class="jarvis-dialog-title">${config.title}</h3>
                </div>
                <div class="jarvis-dialog-body">
                    <p class="jarvis-dialog-message">${message}</p>
                </div>
                <div class="jarvis-dialog-footer">
                    <button class="jarvis-dialog-btn jarvis-dialog-btn-secondary" data-action="cancel">
                        ${config.cancelText}
                    </button>
                    <button class="jarvis-dialog-btn ${config.confirmClass}" data-action="confirm">
                        ${config.confirmText}
                    </button>
                </div>
            `;

            overlay.appendChild(dialog);
            document.body.appendChild(overlay);

            setTimeout(() => {
                overlay.classList.add('show');
                dialog.querySelector('[data-action="confirm"]').focus();
            }, 10);

            const handleClose = (result) => {
                overlay.classList.remove('show');
                setTimeout(() => {
                    overlay.remove();
                    resolve(result);
                }, 200);
            };

            dialog.querySelector('[data-action="confirm"]').addEventListener('click', () => handleClose(true));
            dialog.querySelector('[data-action="cancel"]').addEventListener('click', () => handleClose(false));
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) handleClose(false);
            });

            const handleKey = (e) => {
                if (e.key === 'Escape') {
                    handleClose(false);
                    document.removeEventListener('keydown', handleKey);
                } else if (e.key === 'Enter') {
                    handleClose(true);
                    document.removeEventListener('keydown', handleKey);
                }
            };
            document.addEventListener('keydown', handleKey);
        });
    },

    /**
     * Show a prompt dialog (replaces native prompt())
     * @param {string} message - The message to display
     * @param {object} options - Optional configuration
     * @returns {Promise<string|null>} Resolves with input value or null if cancelled
     */
    prompt(message, options = {}) {
        const config = {
            title: options.title || 'Input Required',
            type: options.type || 'info',
            placeholder: options.placeholder || '',
            defaultValue: options.defaultValue || '',
            confirmText: options.confirmText || 'Submit',
            cancelText: options.cancelText || 'Cancel'
        };

        return new Promise(resolve => {
            const overlay = this._createOverlay();
            const dialog = document.createElement('div');
            dialog.className = 'jarvis-dialog';
            dialog.innerHTML = `
                <div class="jarvis-dialog-header">
                    <div class="jarvis-dialog-icon ${config.type}">
                        <i class="bi ${this._getIcon(config.type)}"></i>
                    </div>
                    <h3 class="jarvis-dialog-title">${config.title}</h3>
                </div>
                <div class="jarvis-dialog-body">
                    <p class="jarvis-dialog-message">${message}</p>
                    <input type="text" class="jarvis-dialog-input"
                           placeholder="${config.placeholder}"
                           value="${config.defaultValue}">
                </div>
                <div class="jarvis-dialog-footer">
                    <button class="jarvis-dialog-btn jarvis-dialog-btn-secondary" data-action="cancel">
                        ${config.cancelText}
                    </button>
                    <button class="jarvis-dialog-btn jarvis-dialog-btn-primary" data-action="confirm">
                        ${config.confirmText}
                    </button>
                </div>
            `;

            overlay.appendChild(dialog);
            document.body.appendChild(overlay);

            const input = dialog.querySelector('.jarvis-dialog-input');

            setTimeout(() => {
                overlay.classList.add('show');
                input.focus();
                input.select();
            }, 10);

            const handleClose = (result) => {
                overlay.classList.remove('show');
                setTimeout(() => {
                    overlay.remove();
                    resolve(result);
                }, 200);
            };

            dialog.querySelector('[data-action="confirm"]').addEventListener('click', () => handleClose(input.value));
            dialog.querySelector('[data-action="cancel"]').addEventListener('click', () => handleClose(null));
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) handleClose(null);
            });

            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    handleClose(input.value);
                }
            });

            const handleKey = (e) => {
                if (e.key === 'Escape') {
                    handleClose(null);
                    document.removeEventListener('keydown', handleKey);
                }
            };
            document.addEventListener('keydown', handleKey);
        });
    },

    // Helper: Create overlay element
    _createOverlay() {
        const overlay = document.createElement('div');
        overlay.className = 'jarvis-dialog-overlay';
        return overlay;
    },

    // Helper: Get icon class based on type
    _getIcon(type) {
        const icons = {
            info: 'bi-info-circle-fill',
            success: 'bi-check-circle-fill',
            warning: 'bi-exclamation-triangle-fill',
            error: 'bi-x-circle-fill',
            confirm: 'bi-question-circle-fill'
        };
        return icons[type] || icons.info;
    },

    // Helper: Get default title based on type
    _getDefaultTitle(type) {
        const titles = {
            info: 'Information',
            success: 'Success',
            warning: 'Warning',
            error: 'Error',
            confirm: 'Confirm'
        };
        return titles[type] || 'Notice';
    },

    // Helper: Escape HTML to prevent XSS
    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
};

/**
 * Toast Notifications
 */
const JarvisToast = {
    container: null,

    // Ensure container exists
    _ensureContainer() {
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.className = 'jarvis-toast-container';
            document.body.appendChild(this.container);
        }
        return this.container;
    },

    /**
     * Show a toast notification
     * @param {string} message - The message to display
     * @param {object} options - Configuration options
     */
    show(message, options = {}) {
        const config = {
            type: options.type || 'info',
            title: options.title || this._getDefaultTitle(options.type || 'info'),
            duration: options.duration !== undefined ? options.duration : 4000, // 0 = no auto-dismiss
            closable: options.closable !== false
        };

        const container = this._ensureContainer();
        const toast = document.createElement('div');
        toast.className = 'jarvis-toast';
        toast.style.position = 'relative';

        toast.innerHTML = `
            <div class="jarvis-toast-icon ${config.type}">
                <i class="bi ${this._getIcon(config.type)}"></i>
            </div>
            <div class="jarvis-toast-content">
                <p class="jarvis-toast-title">${config.title}</p>
                <p class="jarvis-toast-message">${message}</p>
            </div>
            ${config.closable ? '<button class="jarvis-toast-close"><i class="bi bi-x"></i></button>' : ''}
            ${config.duration > 0 ? `<div class="jarvis-toast-progress" style="animation-duration: ${config.duration}ms;"></div>` : ''}
        `;

        container.appendChild(toast);

        // Show with animation
        setTimeout(() => toast.classList.add('show'), 10);

        // Close handler
        const closeToast = () => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        };

        // Close button
        if (config.closable) {
            toast.querySelector('.jarvis-toast-close').addEventListener('click', closeToast);
        }

        // Auto dismiss
        if (config.duration > 0) {
            setTimeout(closeToast, config.duration);
        }

        return { close: closeToast };
    },

    // Convenience methods
    info(message, options = {}) {
        return this.show(message, { ...options, type: 'info' });
    },

    success(message, options = {}) {
        return this.show(message, { ...options, type: 'success' });
    },

    warning(message, options = {}) {
        return this.show(message, { ...options, type: 'warning' });
    },

    error(message, options = {}) {
        return this.show(message, { ...options, type: 'error' });
    },

    // Helper: Get icon class
    _getIcon(type) {
        const icons = {
            info: 'bi-info-circle-fill',
            success: 'bi-check-circle-fill',
            warning: 'bi-exclamation-triangle-fill',
            error: 'bi-x-circle-fill'
        };
        return icons[type] || icons.info;
    },

    // Helper: Get default title
    _getDefaultTitle(type) {
        const titles = {
            info: 'Info',
            success: 'Success',
            warning: 'Warning',
            error: 'Error'
        };
        return titles[type] || 'Notice';
    }
};

// Export for global access
window.JarvisDialog = JarvisDialog;
window.JarvisToast = JarvisToast;
