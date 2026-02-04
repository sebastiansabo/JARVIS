// J.A.R.V.I.S. Core Tagging System
// Reusable tag manager for filter dropdown, tag badges, tag picker, and bulk tagging.

class JarvisTags {
    constructor(options) {
        this.entityType = options.entityType;
        this.containerId = options.containerId;
        this.onFilterChange = options.onFilterChange || (() => {});

        this.tags = [];
        this.groups = [];
        this.selectedTagIds = [];
        this.container = document.getElementById(this.containerId);

        if (this.container) this.init();
    }

    async init() {
        await this.loadTags();
        this.renderFilterDropdown();
    }

    async loadTags() {
        try {
            const [tagsRes, groupsRes] = await Promise.all([
                fetch('/api/tags'),
                fetch('/api/tag-groups')
            ]);
            this.tags = await tagsRes.json();
            this.groups = await groupsRes.json();
        } catch (e) {
            console.error('Failed to load tags:', e);
        }
    }

    renderFilterDropdown() {
        if (!this.container) return;

        const grouped = {};
        const ungrouped = [];
        for (const tag of this.tags) {
            if (tag.group_name) {
                if (!grouped[tag.group_name]) grouped[tag.group_name] = [];
                grouped[tag.group_name].push(tag);
            } else {
                ungrouped.push(tag);
            }
        }

        const count = this.selectedTagIds.length;
        const badgeHtml = count > 0 ? `<span class="badge bg-primary ms-1">${count}</span>` : '';

        let menuHtml = `<input type="text" class="form-control form-control-sm mb-2 jarvis-tag-search" placeholder="Search tags...">`;

        // Grouped tags
        for (const [groupName, tags] of Object.entries(grouped)) {
            menuHtml += `<h6 class="dropdown-header px-2 mt-1 mb-0" style="font-size:0.75rem">${this._esc(groupName)}</h6>`;
            for (const tag of tags) {
                const checked = this.selectedTagIds.includes(tag.id) ? ' checked' : '';
                menuHtml += `<label class="dropdown-item py-1 px-2 d-flex align-items-center gap-2" style="font-size:0.85rem; cursor:pointer">
                    <input type="checkbox" value="${tag.id}" class="jarvis-tag-filter-cb"${checked}>
                    <span style="color:${this._esc(tag.color)}">&#9679;</span> ${this._esc(tag.name)}
                </label>`;
            }
        }

        // Ungrouped tags
        if (ungrouped.length > 0) {
            if (Object.keys(grouped).length > 0) menuHtml += '<div class="dropdown-divider my-1"></div>';
            for (const tag of ungrouped) {
                const checked = this.selectedTagIds.includes(tag.id) ? ' checked' : '';
                menuHtml += `<label class="dropdown-item py-1 px-2 d-flex align-items-center gap-2" style="font-size:0.85rem; cursor:pointer">
                    <input type="checkbox" value="${tag.id}" class="jarvis-tag-filter-cb"${checked}>
                    <span style="color:${this._esc(tag.color)}">&#9679;</span> ${this._esc(tag.name)}
                </label>`;
            }
        }

        if (this.tags.length === 0) {
            menuHtml += '<div class="text-muted text-center py-2" style="font-size:0.8rem">No tags yet</div>';
        }

        // Clear button
        if (count > 0) {
            menuHtml += `<div class="dropdown-divider my-1"></div>
                <button class="dropdown-item text-center py-1 jarvis-tag-clear-filter" style="font-size:0.8rem">
                    <i class="bi bi-x-circle"></i> Clear filter
                </button>`;
        }

        this.container.innerHTML = `
            <div class="dropdown">
                <button class="btn btn-outline-secondary btn-sm dropdown-toggle" type="button"
                        data-bs-toggle="dropdown" data-bs-auto-close="outside" title="Filter by tags">
                    <i class="bi bi-tags"></i> Tags${badgeHtml}
                </button>
                <div class="dropdown-menu p-2" style="min-width:240px; max-height:320px; overflow-y:auto">
                    ${menuHtml}
                </div>
            </div>`;

        // Event listeners
        this.container.querySelectorAll('.jarvis-tag-filter-cb').forEach(cb => {
            cb.addEventListener('change', () => this._onCheckboxChange());
        });

        const searchInput = this.container.querySelector('.jarvis-tag-search');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                const q = e.target.value.toLowerCase();
                this.container.querySelectorAll('.dropdown-item').forEach(item => {
                    if (item.querySelector('.jarvis-tag-filter-cb')) {
                        const text = item.textContent.toLowerCase();
                        item.style.display = text.includes(q) ? '' : 'none';
                    }
                });
            });
        }

        const clearBtn = this.container.querySelector('.jarvis-tag-clear-filter');
        if (clearBtn) {
            clearBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.selectedTagIds = [];
                this.renderFilterDropdown();
                this.onFilterChange(this.selectedTagIds);
            });
        }
    }

    _onCheckboxChange() {
        this.selectedTagIds = [];
        this.container.querySelectorAll('.jarvis-tag-filter-cb:checked').forEach(cb => {
            this.selectedTagIds.push(parseInt(cb.value));
        });
        this.renderFilterDropdown();
        this.onFilterChange(this.selectedTagIds);
    }

    getSelectedTags() {
        return [...this.selectedTagIds];
    }

    setSelectedTags(ids) {
        this.selectedTagIds = Array.isArray(ids) ? ids.map(Number) : [];
        this.renderFilterDropdown();
    }

    // Static: render tag badges HTML for a table cell
    static renderTagBadges(tags, options = {}) {
        if (!tags || tags.length === 0) {
            if (options.editable) {
                return `<button class="jarvis-tag-add-btn" onclick="JarvisTags.openTagPicker('${options.entityType}', ${options.entityId})" title="Add tags">
                    <i class="bi bi-plus"></i>
                </button>`;
            }
            return '';
        }
        let html = tags.map(tag => {
            const rgb = JarvisTags._hexToRgb(tag.color || '#0d6efd');
            const bg = `rgba(${rgb.r},${rgb.g},${rgb.b},0.15)`;
            const border = `rgba(${rgb.r},${rgb.g},${rgb.b},0.3)`;
            const label = tag.group_name ? `${tag.group_name}: ${tag.name}` : tag.name;
            let removeBtn = '';
            if (options.editable) {
                removeBtn = `<span class="jarvis-tag-remove" onclick="event.stopPropagation(); JarvisTags.removeTagFromEntity(${tag.id}, '${options.entityType}', ${options.entityId})" title="Remove">&times;</span>`;
            }
            return `<span class="jarvis-tag-badge" style="background-color:${bg}; color:${tag.color}; border:1px solid ${border}" title="${JarvisTags._esc(label)}">
                ${tag.icon ? `<i class="bi bi-${JarvisTags._esc(tag.icon)}"></i> ` : ''}${JarvisTags._esc(tag.name)}${removeBtn}
            </span>`;
        }).join(' ');

        if (options.editable) {
            html += ` <button class="jarvis-tag-add-btn" onclick="JarvisTags.openTagPicker('${options.entityType}', ${options.entityId})" title="Add tags">
                <i class="bi bi-plus"></i>
            </button>`;
        }
        return html;
    }

    // Static: open tag picker for an entity
    static async openTagPicker(entityType, entityId) {
        // Load current tags for this entity + all available tags
        const [entityTagsRes, allTagsRes, groupsRes] = await Promise.all([
            fetch(`/api/entity-tags?entity_type=${entityType}&entity_id=${entityId}`),
            fetch('/api/tags'),
            fetch('/api/tag-groups')
        ]);
        const entityTags = await entityTagsRes.json();
        const allTags = await allTagsRes.json();
        const groups = await groupsRes.json();

        const entityTagIds = new Set(entityTags.map(t => t.id));

        // Build grouped tag list
        const grouped = {};
        const ungrouped = [];
        for (const tag of allTags) {
            if (tag.group_name) {
                if (!grouped[tag.group_name]) grouped[tag.group_name] = [];
                grouped[tag.group_name].push(tag);
            } else {
                ungrouped.push(tag);
            }
        }

        let bodyHtml = '<div class="jarvis-tag-picker-search mb-2"><input type="text" class="form-control form-control-sm" placeholder="Search tags..."></div>';
        bodyHtml += '<div class="jarvis-tag-picker-list" style="max-height:250px; overflow-y:auto">';

        for (const [groupName, tags] of Object.entries(grouped)) {
            bodyHtml += `<div class="fw-bold text-muted small px-1 mt-1">${JarvisTags._esc(groupName)}</div>`;
            for (const tag of tags) {
                const checked = entityTagIds.has(tag.id) ? ' checked' : '';
                const rgb = JarvisTags._hexToRgb(tag.color || '#0d6efd');
                bodyHtml += `<label class="d-flex align-items-center gap-2 px-1 py-1 jarvis-tag-picker-item" style="cursor:pointer; font-size:0.85rem">
                    <input type="checkbox" value="${tag.id}" data-tag-name="${JarvisTags._esc(tag.name)}"${checked} class="jarvis-picker-cb">
                    <span style="color:${tag.color}">&#9679;</span> ${JarvisTags._esc(tag.name)}
                </label>`;
            }
        }
        if (ungrouped.length > 0) {
            if (Object.keys(grouped).length > 0) bodyHtml += '<hr class="my-1">';
            for (const tag of ungrouped) {
                const checked = entityTagIds.has(tag.id) ? ' checked' : '';
                bodyHtml += `<label class="d-flex align-items-center gap-2 px-1 py-1 jarvis-tag-picker-item" style="cursor:pointer; font-size:0.85rem">
                    <input type="checkbox" value="${tag.id}" data-tag-name="${JarvisTags._esc(tag.name)}"${checked} class="jarvis-picker-cb">
                    <span style="color:${tag.color}">&#9679;</span> ${JarvisTags._esc(tag.name)}
                </label>`;
            }
        }
        bodyHtml += '</div>';

        // Create inline tag option
        bodyHtml += `<hr class="my-2">
            <div class="d-flex gap-1">
                <input type="text" class="form-control form-control-sm jarvis-new-tag-input" placeholder="New tag name...">
                <button class="btn btn-outline-primary btn-sm jarvis-new-tag-btn" title="Create private tag"><i class="bi bi-plus"></i></button>
            </div>`;

        // Use a custom modal
        let existingModal = document.getElementById('jarvisTagPickerModal');
        if (existingModal) existingModal.remove();

        const modal = document.createElement('div');
        modal.id = 'jarvisTagPickerModal';
        modal.className = 'modal fade';
        modal.setAttribute('tabindex', '-1');
        modal.innerHTML = `
            <div class="modal-dialog modal-sm modal-dialog-centered">
                <div class="modal-content">
                    <div class="modal-header py-2">
                        <h6 class="modal-title"><i class="bi bi-tags"></i> Manage Tags</h6>
                        <button type="button" class="btn-close btn-close-sm" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body py-2">${bodyHtml}</div>
                </div>
            </div>`;
        document.body.appendChild(modal);

        const bsModal = new bootstrap.Modal(modal);

        // Search filter
        modal.querySelector('.jarvis-tag-picker-search input').addEventListener('input', (e) => {
            const q = e.target.value.toLowerCase();
            modal.querySelectorAll('.jarvis-tag-picker-item').forEach(item => {
                item.style.display = item.textContent.toLowerCase().includes(q) ? '' : 'none';
            });
        });

        // Checkbox change → add/remove tag
        modal.querySelectorAll('.jarvis-picker-cb').forEach(cb => {
            cb.addEventListener('change', async () => {
                const tagId = parseInt(cb.value);
                try {
                    if (cb.checked) {
                        await fetch('/api/entity-tags', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ tag_id: tagId, entity_type: entityType, entity_id: entityId })
                        });
                    } else {
                        await fetch('/api/entity-tags', {
                            method: 'DELETE',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ tag_id: tagId, entity_type: entityType, entity_id: entityId })
                        });
                    }
                    // Dispatch custom event for the page to refresh the row
                    document.dispatchEvent(new CustomEvent('jarvis-tags-changed', {
                        detail: { entityType, entityId, tagId, action: cb.checked ? 'add' : 'remove' }
                    }));
                } catch (e) {
                    console.error('Failed to update tag:', e);
                }
            });
        });

        // Create new tag inline
        const newTagBtn = modal.querySelector('.jarvis-new-tag-btn');
        const newTagInput = modal.querySelector('.jarvis-new-tag-input');
        newTagBtn.addEventListener('click', async () => {
            const name = newTagInput.value.trim();
            if (!name) return;
            try {
                const res = await fetch('/api/tags', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, is_global: false, color: '#0d6efd' })
                });
                const data = await res.json();
                if (data.success) {
                    // Add tag to entity immediately
                    await fetch('/api/entity-tags', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ tag_id: data.id, entity_type: entityType, entity_id: entityId })
                    });
                    if (typeof JarvisToast !== 'undefined') JarvisToast.success(`Tag "${name}" created and applied`);
                    bsModal.hide();
                    document.dispatchEvent(new CustomEvent('jarvis-tags-changed', {
                        detail: { entityType, entityId, tagId: data.id, action: 'add' }
                    }));
                } else {
                    if (typeof JarvisToast !== 'undefined') JarvisToast.error(data.error || 'Failed to create tag');
                }
            } catch (e) {
                console.error('Failed to create tag:', e);
            }
        });

        newTagInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); newTagBtn.click(); }
        });

        // Cleanup on hide
        modal.addEventListener('hidden.bs.modal', () => { modal.remove(); });

        bsModal.show();
    }

    // Static: remove a tag from an entity (called from badge X button)
    static async removeTagFromEntity(tagId, entityType, entityId) {
        try {
            await fetch('/api/entity-tags', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tag_id: tagId, entity_type: entityType, entity_id: entityId })
            });
            document.dispatchEvent(new CustomEvent('jarvis-tags-changed', {
                detail: { entityType, entityId, tagId, action: 'remove' }
            }));
        } catch (e) {
            console.error('Failed to remove tag:', e);
        }
    }

    // Static: bulk tag multiple entities
    static async bulkTag(entityType, entityIds, tagId, action = 'add') {
        try {
            const res = await fetch('/api/entity-tags/bulk', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tag_id: tagId, entity_type: entityType, entity_ids: entityIds, action })
            });
            const data = await res.json();
            if (data.success) {
                document.dispatchEvent(new CustomEvent('jarvis-tags-changed', {
                    detail: { entityType, entityIds, tagId, action, count: data.count }
                }));
            }
            return data;
        } catch (e) {
            console.error('Bulk tag failed:', e);
            return { success: false };
        }
    }

    // Static: open a bulk tag dropdown for selected entities
    static async openBulkTagDropdown(entityType, entityIds, buttonElement) {
        const tagsRes = await fetch('/api/tags');
        const tags = await tagsRes.json();

        const grouped = {};
        const ungrouped = [];
        for (const tag of tags) {
            if (tag.group_name) {
                if (!grouped[tag.group_name]) grouped[tag.group_name] = [];
                grouped[tag.group_name].push(tag);
            } else {
                ungrouped.push(tag);
            }
        }

        let menuHtml = '';
        for (const [groupName, gTags] of Object.entries(grouped)) {
            menuHtml += `<h6 class="dropdown-header" style="font-size:0.7rem">${JarvisTags._esc(groupName)}</h6>`;
            for (const tag of gTags) {
                menuHtml += `<button class="dropdown-item py-1" data-tag-id="${tag.id}" style="font-size:0.85rem">
                    <span style="color:${tag.color}">&#9679;</span> ${JarvisTags._esc(tag.name)}
                </button>`;
            }
        }
        if (ungrouped.length > 0 && Object.keys(grouped).length > 0) {
            menuHtml += '<div class="dropdown-divider"></div>';
        }
        for (const tag of ungrouped) {
            menuHtml += `<button class="dropdown-item py-1" data-tag-id="${tag.id}" style="font-size:0.85rem">
                <span style="color:${tag.color}">&#9679;</span> ${JarvisTags._esc(tag.name)}
            </button>`;
        }

        // Create temporary dropdown menu
        let existing = document.getElementById('jarvisBulkTagMenu');
        if (existing) existing.remove();

        const menu = document.createElement('div');
        menu.id = 'jarvisBulkTagMenu';
        menu.className = 'dropdown-menu show p-1';
        menu.style.cssText = 'position:absolute; z-index:1060; min-width:200px; max-height:300px; overflow-y:auto;';
        menu.innerHTML = menuHtml;

        // Position near button
        const rect = buttonElement.getBoundingClientRect();
        menu.style.top = (rect.bottom + window.scrollY) + 'px';
        menu.style.left = rect.left + 'px';
        document.body.appendChild(menu);

        // Click handler
        menu.querySelectorAll('[data-tag-id]').forEach(btn => {
            btn.addEventListener('click', async () => {
                const tagId = parseInt(btn.dataset.tagId);
                menu.remove();
                const result = await JarvisTags.bulkTag(entityType, entityIds, tagId, 'add');
                if (result.success && typeof JarvisToast !== 'undefined') {
                    JarvisToast.success(`Tagged ${result.count} item(s)`);
                }
            });
        });

        // Close on outside click
        const closeHandler = (e) => {
            if (!menu.contains(e.target) && e.target !== buttonElement) {
                menu.remove();
                document.removeEventListener('click', closeHandler);
            }
        };
        setTimeout(() => document.addEventListener('click', closeHandler), 10);
    }

    _esc(str) { return JarvisTags._esc(str); }

    static _esc(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    static _hexToRgb(hex) {
        const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
        return result ? {
            r: parseInt(result[1], 16),
            g: parseInt(result[2], 16),
            b: parseInt(result[3], 16)
        } : { r: 13, g: 110, b: 253 };
    }
}

window.JarvisTags = JarvisTags;
