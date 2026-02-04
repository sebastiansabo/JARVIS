/**
 * J.A.R.V.I.S. Filter Presets
 * ============================
 * Reusable preset manager for saving/loading filter states per page.
 *
 * Usage:
 *   new JarvisPresets({
 *       pageKey: 'accounting',
 *       containerId: 'presetContainer',
 *       onSave: () => ({ filters: {...}, columns: {...}, ... }),
 *       onApply: (data) => { // set filters, columns, etc. },
 *       onAfterApply: () => { // reload data }
 *   });
 */

class JarvisPresets {
    constructor(options) {
        this.pageKey = options.pageKey;
        this.containerId = options.containerId;
        this.onSave = options.onSave;
        this.onApply = options.onApply;
        this.onAfterApply = options.onAfterApply || (() => {});

        this.presets = [];
        this.activePresetId = null;
        this.container = document.getElementById(this.containerId);

        if (this.container) {
            this.init();
        }
    }

    async init() {
        await this.loadPresets();
        this.render();
        this.applyDefault();
    }

    async loadPresets() {
        try {
            const resp = await fetch(`/api/presets?page=${encodeURIComponent(this.pageKey)}`);
            if (resp.ok) {
                this.presets = await resp.json();
            }
        } catch (e) {
            console.warn('Failed to load presets:', e);
        }
    }

    applyDefault() {
        const defaultPreset = this.presets.find(p => p.is_default);
        if (defaultPreset) {
            this.applyPreset(defaultPreset);
        }
    }

    applyPreset(preset) {
        this.activePresetId = preset.id;
        let data = null;
        if (preset.preset_data && this.onApply) {
            data = typeof preset.preset_data === 'string'
                ? JSON.parse(preset.preset_data)
                : preset.preset_data;
            this.onApply(data);
        }
        this.render();
        this.onAfterApply(data);
    }

    render() {
        const activePreset = this.presets.find(p => p.id === this.activePresetId);
        const hasActive = !!activePreset;

        const presetOptions = this.presets.map(p => {
            const star = p.is_default ? ' \u2605' : '';
            const selected = p.id === this.activePresetId ? ' selected' : '';
            return `<option value="${p.id}"${selected}>${this._escapeHtml(p.name)}${star}</option>`;
        }).join('');

        const isDefault = activePreset?.is_default;
        const starFill = isDefault ? '-fill' : '';
        const defaultStyle = isDefault
            ? 'background-color: var(--bs-warning); color: #000;'
            : '';

        this.container.innerHTML = `
            <div class="jarvis-presets-toolbar d-flex align-items-center gap-1">
                <i class="bi bi-bookmark text-muted" style="font-size: 0.85rem;" title="Filter Presets"></i>
                <select class="form-select form-select-sm jarvis-preset-select"
                        style="width: auto; min-width: 130px; font-size: 0.8rem;">
                    <option value="">-- No Preset --</option>
                    ${presetOptions}
                </select>
                <button class="btn btn-outline-secondary btn-sm jarvis-preset-save"
                        title="Save current state to selected preset"
                        ${hasActive ? '' : 'disabled'}
                        style="font-size: 0.75rem; padding: 0.15rem 0.4rem;">
                    <i class="bi bi-save"></i>
                </button>
                <button class="btn btn-outline-primary btn-sm jarvis-preset-save-as"
                        title="Save as new preset"
                        style="font-size: 0.75rem; padding: 0.15rem 0.4rem;">
                    <i class="bi bi-plus-lg"></i>
                </button>
                <button class="btn btn-outline-warning btn-sm jarvis-preset-default"
                        title="${isDefault ? 'Remove as default' : 'Set as default preset'}"
                        ${hasActive ? '' : 'disabled'}
                        style="font-size: 0.75rem; padding: 0.15rem 0.4rem; ${defaultStyle}">
                    <i class="bi bi-star${starFill}"></i>
                </button>
                <button class="btn btn-outline-danger btn-sm jarvis-preset-delete"
                        title="Delete selected preset"
                        ${hasActive ? '' : 'disabled'}
                        style="font-size: 0.75rem; padding: 0.15rem 0.4rem;">
                    <i class="bi bi-trash3"></i>
                </button>
            </div>
        `;

        this._attachEventListeners();
    }

    _attachEventListeners() {
        const select = this.container.querySelector('.jarvis-preset-select');
        const saveBtn = this.container.querySelector('.jarvis-preset-save');
        const saveAsBtn = this.container.querySelector('.jarvis-preset-save-as');
        const defaultBtn = this.container.querySelector('.jarvis-preset-default');
        const deleteBtn = this.container.querySelector('.jarvis-preset-delete');

        select?.addEventListener('change', (e) => {
            const id = parseInt(e.target.value);
            if (id) {
                const preset = this.presets.find(p => p.id === id);
                if (preset) this.applyPreset(preset);
            } else {
                // "No Preset" selected — refresh page to reset all filters
                this.activePresetId = null;
                window.location.href = window.location.pathname;
            }
        });

        saveBtn?.addEventListener('click', () => this.saveCurrentPreset());
        saveAsBtn?.addEventListener('click', () => this.saveAsNewPreset());
        defaultBtn?.addEventListener('click', () => this.toggleDefault());
        deleteBtn?.addEventListener('click', () => this.deleteCurrentPreset());
    }

    async saveCurrentPreset() {
        if (!this.activePresetId) return;
        const presetData = this.onSave();
        try {
            const resp = await fetch(`/api/presets/${this.activePresetId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ preset_data: presetData })
            });
            const result = await resp.json();
            if (result.success) {
                if (typeof JarvisToast !== 'undefined') JarvisToast.success('Preset saved');
                const p = this.presets.find(p => p.id === this.activePresetId);
                if (p) p.preset_data = presetData;
            } else {
                if (typeof JarvisToast !== 'undefined') JarvisToast.error(result.error || 'Failed to save');
            }
        } catch (e) {
            if (typeof JarvisToast !== 'undefined') JarvisToast.error('Failed to save preset');
        }
    }

    async saveAsNewPreset() {
        let name;
        if (typeof JarvisDialog !== 'undefined') {
            name = await JarvisDialog.prompt('Enter a name for this preset:', {
                title: 'Save Preset',
                placeholder: 'e.g., Monthly Review, Q1 Filters...',
                confirmText: 'Save'
            });
        } else {
            name = prompt('Enter a name for this preset:');
        }
        if (!name || !name.trim()) return;

        const trimmedName = name.trim();
        const presetData = this.onSave();
        const isFirstPreset = this.presets.length === 0;

        try {
            const resp = await fetch('/api/presets', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    page_key: this.pageKey,
                    name: trimmedName,
                    preset_data: presetData,
                    is_default: isFirstPreset
                })
            });
            const result = await resp.json();
            if (result.success) {
                if (typeof JarvisToast !== 'undefined') {
                    JarvisToast.success(`Preset "${trimmedName}" created${isFirstPreset ? ' (set as default)' : ''}`);
                }
                await this.loadPresets();
                this.activePresetId = result.id;
                this.render();
            } else {
                if (typeof JarvisToast !== 'undefined') JarvisToast.error(result.error || 'Failed to create preset');
            }
        } catch (e) {
            if (typeof JarvisToast !== 'undefined') JarvisToast.error('Failed to create preset');
        }
    }

    async toggleDefault() {
        if (!this.activePresetId) return;
        const preset = this.presets.find(p => p.id === this.activePresetId);
        if (!preset) return;

        const newDefault = !preset.is_default;
        try {
            const resp = await fetch(`/api/presets/${this.activePresetId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_default: newDefault })
            });
            const result = await resp.json();
            if (result.success) {
                this.presets.forEach(p => p.is_default = false);
                if (newDefault) {
                    preset.is_default = true;
                    if (typeof JarvisToast !== 'undefined') JarvisToast.success(`"${preset.name}" set as default`);
                } else {
                    if (typeof JarvisToast !== 'undefined') JarvisToast.info('Default preset cleared');
                }
                this.render();
            }
        } catch (e) {
            if (typeof JarvisToast !== 'undefined') JarvisToast.error('Failed to update default');
        }
    }

    async deleteCurrentPreset() {
        if (!this.activePresetId) return;
        const preset = this.presets.find(p => p.id === this.activePresetId);
        if (!preset) return;

        let confirmed;
        if (typeof JarvisDialog !== 'undefined') {
            confirmed = await JarvisDialog.confirm(
                `Delete preset "${preset.name}"?`,
                { danger: true, title: 'Delete Preset' }
            );
        } else {
            confirmed = confirm(`Delete preset "${preset.name}"?`);
        }
        if (!confirmed) return;

        try {
            const resp = await fetch(`/api/presets/${this.activePresetId}`, { method: 'DELETE' });
            const result = await resp.json();
            if (result.success) {
                if (typeof JarvisToast !== 'undefined') JarvisToast.success(`Preset "${preset.name}" deleted`);
                this.activePresetId = null;
                await this.loadPresets();
                this.render();
            }
        } catch (e) {
            if (typeof JarvisToast !== 'undefined') JarvisToast.error('Failed to delete preset');
        }
    }

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

window.JarvisPresets = JarvisPresets;
