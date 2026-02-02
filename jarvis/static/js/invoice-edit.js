/**
 * Invoice Edit Module - Shared JavaScript for editing invoices
 * Used by: accounting.html, profile.html, and any page with the edit invoice modal
 *
 * Full-featured version matching accounting.html functionality:
 * - Smart split allocation
 * - Lock allocations
 * - Multi-line reinvoice destinations
 * - Allocation comments
 */

// Module state
const InvoiceEdit = {
    currentInvoiceData: null,
    organizationalStructure: [],
    statusOptions: [],
    paymentStatusOptions: [],
    vatRates: [],
    companiesData: [],
    editAllocations: [],
    onSaveCallback: null,  // Callback after successful save
    userRole: 'Viewer',    // Current user's role (set during init)

    // Role hierarchy for permission checks (higher index = more permissions)
    roleHierarchy: ['Viewer', 'User', 'Manager', 'Admin'],

    // Check if user's role meets the minimum required role
    userHasRole(minRole) {
        const userRoleIndex = this.roleHierarchy.indexOf(this.userRole);
        const minRoleIndex = this.roleHierarchy.indexOf(minRole || 'Viewer');
        return userRoleIndex >= minRoleIndex;
    },

    // Check if user can edit processed invoices (legacy - for backward compatibility)
    canEditProcessed() {
        return ['Admin', 'Manager'].includes(this.userRole);
    },

    // Initialize the module
    async init(options = {}) {
        this.onSaveCallback = options.onSaveCallback || null;
        this.userRole = options.userRole || 'Viewer';
        await this.loadDropdownOptions();
        await this.loadOrganizationalStructure();
        this.setupEventListeners();
    },

    // Load dropdown options from API
    async loadDropdownOptions() {
        try {
            const [optionsResponse, vatResponse] = await Promise.all([
                fetch('/api/dropdown-options'),
                fetch('/api/vat-rates')
            ]);
            const data = await optionsResponse.json();

            // Filter options by dropdown_type (API returns flat array)
            this.statusOptions = data.filter(opt => opt.dropdown_type === 'invoice_status');
            this.paymentStatusOptions = data.filter(opt => opt.dropdown_type === 'payment_status');
            this.vatRates = await vatResponse.json();

            // Populate status dropdown (filter based on min_role)
            const statusSelect = document.getElementById('editStatus');
            if (statusSelect) {
                statusSelect.innerHTML = this.statusOptions
                    .filter(opt => this.userHasRole(opt.min_role))
                    .map(opt => `<option value="${opt.value}">${opt.label || opt.value}</option>`)
                    .join('');
            }

            // Populate payment status dropdown
            const paymentSelect = document.getElementById('editPaymentStatus');
            if (paymentSelect) {
                paymentSelect.innerHTML = this.paymentStatusOptions.map(opt =>
                    `<option value="${opt.value}">${opt.label || opt.value}</option>`
                ).join('');
            }

            // Populate VAT rates dropdown
            const vatSelect = document.getElementById('editVatRateId');
            if (vatSelect) {
                vatSelect.innerHTML = '<option value="">Select rate...</option>' +
                    this.vatRates.map(r => `<option value="${r.id}" data-rate="${r.rate}">${r.name}</option>`).join('');
            }
        } catch (e) {
            console.error('Error loading dropdown options:', e);
        }
    },

    // Load organizational structure
    async loadOrganizationalStructure() {
        try {
            const [structResponse, companiesResponse] = await Promise.all([
                fetch('/api/structure'),
                fetch('/api/companies-vat')
            ]);
            this.organizationalStructure = await structResponse.json();
            this.companiesData = await companiesResponse.json();

            // Populate company dropdown
            const companySelect = document.getElementById('editDedicatedCompany');
            if (companySelect) {
                companySelect.innerHTML = '<option value="">Select company...</option>' +
                    this.companiesData.map(c => `<option value="${c.company}">${c.company}</option>`).join('');
            }
        } catch (e) {
            console.error('Error loading organizational structure:', e);
        }
    },

    // Setup event listeners
    setupEventListeners() {
        // VAT checkbox handler
        const subtractVatCheckbox = document.getElementById('editSubtractVat');
        if (subtractVatCheckbox) {
            subtractVatCheckbox.addEventListener('change', () => this.onVatCheckboxChange());
        }

        // VAT rate change handler
        const vatRateSelect = document.getElementById('editVatRateId');
        if (vatRateSelect) {
            vatRateSelect.addEventListener('change', () => this.calculateNetValue());
        }

        // Invoice value change handler
        const invoiceValueInput = document.getElementById('editInvoiceValue');
        if (invoiceValueInput) {
            invoiceValueInput.addEventListener('input', () => {
                this.recalculateAllocationValues();
                this.renderEditAllocations();
                if (document.getElementById('editSubtractVat').checked) {
                    this.calculateNetValue();
                }
            });
        }

        // Currency change handler
        const currencySelect = document.getElementById('editCurrency');
        if (currencySelect) {
            currencySelect.addEventListener('change', () => this.renderEditAllocations());
        }

        // Add allocation button
        const addBtn = document.getElementById('addAllocationBtn');
        if (addBtn) {
            addBtn.addEventListener('click', () => this.addAllocation());
        }

        // Company change handler
        const companySelect = document.getElementById('editDedicatedCompany');
        if (companySelect) {
            companySelect.addEventListener('change', () => this.onDedicatedCompanyChange());
        }

        // Save button
        const saveBtn = document.getElementById('saveInvoiceBtn');
        if (saveBtn) {
            saveBtn.addEventListener('click', () => this.saveInvoice());
        }

        // Upload file button
        const uploadBtn = document.getElementById('uploadEditFileBtn');
        if (uploadBtn) {
            uploadBtn.addEventListener('click', () => this.uploadFile());
        }

        // Edit from detail modal
        const editFromDetailBtn = document.getElementById('editFromDetailBtn');
        if (editFromDetailBtn) {
            editFromDetailBtn.addEventListener('click', () => {
                if (this.currentInvoiceData) {
                    const detailModal = bootstrap.Modal.getInstance(document.getElementById('invoiceDetailModal'));
                    if (detailModal) detailModal.hide();
                    this.openEditModal(this.currentInvoiceData.id);
                }
            });
        }

        // Save allocation comment
        const saveCommentBtn = document.getElementById('saveAllocationCommentBtn');
        if (saveCommentBtn) {
            saveCommentBtn.addEventListener('click', () => this.saveAllocationComment());
        }
    },

    // View invoice detail
    async viewInvoice(invoiceId) {
        const modal = new bootstrap.Modal(document.getElementById('invoiceDetailModal'));
        const body = document.getElementById('invoiceDetailBody');
        body.innerHTML = '<div class="text-center"><div class="spinner-border"></div></div>';
        modal.show();

        try {
            const response = await fetch(`/api/db/invoices/${invoiceId}`);
            const invoice = await response.json();
            this.currentInvoiceData = invoice;

            body.innerHTML = `
                <div class="row">
                    <div class="col-md-6">
                        <p><strong>Supplier:</strong> ${invoice.supplier || '-'}</p>
                        <p><strong>Invoice Number:</strong> ${invoice.invoice_number || '-'}</p>
                        <p><strong>Invoice Date:</strong> ${this.formatDateRomanian(invoice.invoice_date)}</p>
                        <p><strong>Invoice Value:</strong> ${this.formatCurrency(invoice.invoice_value)} ${invoice.currency || 'RON'}</p>
                    </div>
                    <div class="col-md-6">
                        <p><strong>Status:</strong> <span class="badge ${this.getStatusClass(invoice.status)}">${invoice.status || '-'}</span></p>
                        <p><strong>Payment Status:</strong> ${invoice.payment_status || '-'}</p>
                        <p><strong>Notes:</strong> ${invoice.comment || '-'}</p>
                        ${invoice.drive_link ? `<p><a href="${invoice.drive_link}" target="_blank" class="btn btn-sm btn-outline-success"><i class="bi bi-cloud-arrow-down"></i> View in Drive</a></p>` : ''}
                    </div>
                </div>
                ${invoice.allocations && invoice.allocations.length > 0 ? `
                <hr>
                <h6><i class="bi bi-pie-chart"></i> Allocations</h6>
                <table class="table table-sm">
                    <thead>
                        <tr><th>Company</th><th>Department</th><th>Brand</th><th class="text-end">Value</th><th class="text-end">%</th></tr>
                    </thead>
                    <tbody>
                        ${invoice.allocations.map(a => `
                            <tr>
                                <td>${a.company || '-'}</td>
                                <td>${a.department || '-'}</td>
                                <td>${a.brand || '-'}</td>
                                <td class="text-end">${this.formatCurrency(a.allocation_value)}</td>
                                <td class="text-end">${(a.allocation_percent || 0).toFixed(0)}%</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
                ` : ''}
            `;
        } catch (e) {
            body.innerHTML = `<div class="alert alert-danger">Error loading invoice: ${e.message}</div>`;
        }
    },

    // Open edit modal
    async openEditModal(invoiceId) {
        if (typeof showLoading === 'function') showLoading('Loading invoice...');

        try {
            // Load invoice data
            const response = await fetch(`/api/db/invoices/${invoiceId}`);
            const invoice = await response.json();
            this.currentInvoiceData = invoice;

            // Block users from editing invoices if their role is below the status's min_role
            const currentStatusOption = this.statusOptions.find(opt => opt.value === invoice.status);
            if (currentStatusOption && !this.userHasRole(currentStatusOption.min_role)) {
                if (typeof hideLoading === 'function') hideLoading();
                const minRole = currentStatusOption.min_role || 'Manager';
                JarvisDialog.alert(`Invoices with status "${currentStatusOption.label}" can only be edited by ${minRole}s or higher.`, { type: 'warning', title: 'Access Restricted' });
                return;
            }

            // Populate form
            document.getElementById('editInvoiceId').value = invoice.id;
            document.getElementById('editSupplier').value = invoice.supplier || '';
            document.getElementById('editInvoiceNumber').value = invoice.invoice_number || '';
            document.getElementById('editInvoiceDate').value = invoice.invoice_date || '';
            document.getElementById('editInvoiceValue').value = invoice.invoice_value || '';
            document.getElementById('editCurrency').value = invoice.currency || 'RON';
            document.getElementById('editDriveLink').value = invoice.drive_link || '';
            document.getElementById('editComment').value = invoice.comment || '';
            document.getElementById('editStatus').value = invoice.status || '';
            document.getElementById('editPaymentStatus').value = invoice.payment_status || '';

            // VAT fields
            const subtractVat = invoice.subtract_vat || false;
            document.getElementById('editSubtractVat').checked = subtractVat;
            document.getElementById('editVatRateCol').style.display = subtractVat ? 'block' : 'none';
            document.getElementById('editNetValueCol').style.display = subtractVat ? 'block' : 'none';

            if (invoice.vat_rate_id) {
                document.getElementById('editVatRateId').value = invoice.vat_rate_id;
            } else if (invoice.vat_rate) {
                // Match by rate value if vat_rate_id not available
                const vatSelect = document.getElementById('editVatRateId');
                for (let opt of vatSelect.options) {
                    if (opt.dataset.rate == invoice.vat_rate) {
                        vatSelect.value = opt.value;
                        break;
                    }
                }
            }

            if (invoice.net_value) {
                document.getElementById('editNetValue').value = invoice.net_value;
                document.getElementById('editNetValueDisplay').value = this.formatCurrencyNoSymbol(invoice.net_value) + ' ' + (invoice.currency || 'RON');
            }

            // Set dedicated company from first allocation
            if (invoice.allocations && invoice.allocations.length > 0) {
                document.getElementById('editDedicatedCompany').value = invoice.allocations[0].company || '';
                this.editAllocations = invoice.allocations.map(a => ({
                    ...a,
                    locked: a.locked || false,
                    comment: a.comment || null,
                    reinvoice_destinations: a.reinvoice_destinations || []
                }));
            } else {
                this.editAllocations = [];
            }

            this.renderEditAllocations();

            // Reset file input
            const fileInput = document.getElementById('editInvoiceFile');
            if (fileInput) fileInput.value = '';

            // Show modal
            const modal = new bootstrap.Modal(document.getElementById('editInvoiceModal'));
            modal.show();
        } catch (e) {
            if (typeof showError === 'function') showError('Error loading invoice: ' + e.message);
            else JarvisDialog.alert('Error loading invoice: ' + e.message, { type: 'error' });
        } finally {
            if (typeof hideLoading === 'function') hideLoading();
        }
    },

    // VAT checkbox change handler
    onVatCheckboxChange() {
        const checked = document.getElementById('editSubtractVat').checked;
        document.getElementById('editVatRateCol').style.display = checked ? 'block' : 'none';
        document.getElementById('editNetValueCol').style.display = checked ? 'block' : 'none';
        if (checked) {
            this.calculateNetValue();
        }
        this.recalculateAllocationValues();
        this.renderEditAllocations();
    },

    // Calculate net value
    calculateNetValue() {
        const invoiceValue = parseFloat(document.getElementById('editInvoiceValue').value) || 0;
        const vatRateSelect = document.getElementById('editVatRateId');
        const selectedOption = vatRateSelect.options[vatRateSelect.selectedIndex];

        if (!selectedOption || !selectedOption.dataset.rate) {
            document.getElementById('editNetValue').value = '';
            document.getElementById('editNetValueDisplay').value = '';
            return;
        }

        const vatRate = parseFloat(selectedOption.dataset.rate);
        const netValue = invoiceValue / (1 + vatRate / 100);
        const currency = document.getElementById('editCurrency').value || 'RON';

        document.getElementById('editNetValue').value = netValue.toFixed(2);
        document.getElementById('editNetValueDisplay').value = this.formatCurrencyNoSymbol(netValue) + ' ' + currency;

        this.recalculateAllocationValues();
    },

    // Get base value for allocation calculations (net value if VAT subtracted, otherwise gross value)
    getBaseValue() {
        const subtractVat = document.getElementById('editSubtractVat').checked;
        const grossValue = parseFloat(document.getElementById('editInvoiceValue').value) || 0;
        const netValue = parseFloat(document.getElementById('editNetValue').value) || 0;
        return subtractVat && netValue > 0 ? netValue : grossValue;
    },

    // Dedicated company change handler
    onDedicatedCompanyChange() {
        const company = document.getElementById('editDedicatedCompany').value;
        // Update all allocations to new company and reset fields
        this.editAllocations.forEach(a => {
            a.company = company;
            a.brand = '';
            a.department = '';
            a.subdepartment = '';
            a.responsible = '';
        });
        this.renderEditAllocations();
    },

    // Smart split percentages based on count (matching accounting.html)
    // 1: 100%, 2: 50-50, 3: 40-30-30, 4: 40-20-20-20, etc.
    getSmartSplitPercentages(count) {
        if (count === 1) return [100];
        if (count === 2) return [50, 50];

        // For 3+: first gets 40%, rest split equally
        const firstPercent = 40;
        const remaining = 100 - firstPercent;
        const otherPercent = remaining / (count - 1);

        const result = [firstPercent];
        for (let i = 1; i < count; i++) {
            result.push(otherPercent);
        }
        return result;
    },

    // Apply smart split to all allocations (respecting locked allocations)
    applySmartSplit() {
        const count = this.editAllocations.length;
        if (count === 0) return;

        const baseValue = this.getBaseValue();

        // Separate locked and unlocked allocations
        const lockedAllocs = this.editAllocations.filter(a => a.locked);
        const unlockedAllocs = this.editAllocations.filter(a => !a.locked);

        // Calculate total locked percentage
        let lockedPercent = 0;
        lockedAllocs.forEach(alloc => {
            lockedPercent += parseFloat(alloc.allocation_percent) || 0;
        });

        // Distribute remaining percentage among unlocked allocations
        const remainingPercent = Math.max(0, 100 - lockedPercent);
        const unlockedCount = unlockedAllocs.length;

        if (unlockedCount > 0) {
            let percentages = this.getSmartSplitPercentages(unlockedCount);
            // Scale percentages to fit remaining percent
            const scaleFactor = remainingPercent / 100;
            percentages = percentages.map(p => p * scaleFactor);

            unlockedAllocs.forEach((alloc, idx) => {
                alloc.allocation_percent = percentages[idx];
                alloc.allocation_value = (baseValue * percentages[idx]) / 100;
            });
        }

        // Update locked allocation values (in case invoice value changed)
        lockedAllocs.forEach(alloc => {
            alloc.allocation_value = (baseValue * (parseFloat(alloc.allocation_percent) || 0)) / 100;
        });

        this.renderEditAllocations();
    },

    // Add allocation with smart split
    addAllocation() {
        const company = document.getElementById('editDedicatedCompany').value;
        if (!company) {
            JarvisDialog.alert('Please select a company first', { type: 'warning' });
            return;
        }

        this.editAllocations.push({
            company: company,
            brand: null,
            department: '',
            subdepartment: null,
            allocation_percent: 0,
            allocation_value: 0,
            responsible: '',
            reinvoice_destinations: [],
            locked: false,
            comment: null
        });

        // Apply smart split when adding
        this.applySmartSplit();
    },

    // Remove allocation with smart split redistribution
    removeAllocation(index) {
        if (this.editAllocations.length <= 1) {
            JarvisDialog.alert('Invoice must have at least one allocation', { type: 'warning', title: 'Cannot Delete' });
            return;
        }
        this.editAllocations.splice(index, 1);
        // Apply smart split when removing
        this.applySmartSplit();
    },

    // Render allocations (matching accounting.html layout)
    renderEditAllocations() {
        const container = document.getElementById('allocationsContainer');
        const currency = document.getElementById('editCurrency').value || 'RON';
        const dedicatedCompany = document.getElementById('editDedicatedCompany').value;
        const baseValue = this.getBaseValue();

        // Get departments/brands for the dedicated company
        const departments = this.getDepartmentsForCompany(dedicatedCompany);
        const brands = this.getBrandsForCompany(dedicatedCompany);
        const hasBrands = brands.length > 0;

        if (this.editAllocations.length === 0) {
            container.innerHTML = '<p class="text-muted">No allocations. Click "Add Allocation" to add one.</p>';
            this.updateAllocationTotalBadge();
            return;
        }

        container.innerHTML = this.editAllocations.map((alloc, idx) => {
            const subdepartments = this.getSubdepartmentsForDept(dedicatedCompany, alloc.department);
            const hasSubdepts = subdepartments.length > 0;
            const allocValue = (baseValue * (parseFloat(alloc.allocation_percent) || 0)) / 100;
            const manager = this.getManagerForDepartment(dedicatedCompany, alloc.department, alloc.subdepartment, alloc.brand);
            const hasReinvoice = alloc.reinvoice_destinations && alloc.reinvoice_destinations.length > 0;

            return `
                <div class="allocation-edit-row position-relative border rounded p-3 mb-2" data-idx="${idx}">
                    <div class="position-absolute d-flex gap-1" style="top: 8px; right: 45px;">
                        <button type="button" class="btn btn-sm ${alloc.comment ? 'btn-info' : 'btn-outline-info'}" onclick="InvoiceEdit.openAllocationComment(${idx})" title="${alloc.comment ? 'Edit comment' : 'Add comment'}">
                            <i class="bi ${alloc.comment ? 'bi-chat-text-fill' : 'bi-chat-text'}"></i>
                        </button>
                        <button type="button" class="btn btn-sm ${alloc.locked ? 'btn-warning' : 'btn-outline-secondary'}" onclick="InvoiceEdit.toggleLock(${idx})" title="${alloc.locked ? 'Unlock this allocation' : 'Lock this allocation'}">
                            <i class="bi ${alloc.locked ? 'bi-lock-fill' : 'bi-unlock'}"></i>
                        </button>
                    </div>
                    <button type="button" class="btn btn-sm btn-outline-danger position-absolute" style="top: 8px; right: 8px;" onclick="InvoiceEdit.removeAllocation(${idx})" ${this.editAllocations.length <= 1 ? 'disabled' : ''} title="Delete allocation">
                        <i class="bi bi-trash"></i>
                    </button>
                    <div class="row">
                        <div class="col-md-2 mb-2" ${hasBrands ? '' : 'style="display: none;"'}>
                            <label class="form-label small">Brand</label>
                            <select class="form-select form-select-sm" data-idx="${idx}" onchange="InvoiceEdit.onAllocationFieldChange(${idx}, 'brand', this.value)">
                                <option value="">N/A</option>
                                ${brands.map(b => `<option value="${b}" ${b === alloc.brand ? 'selected' : ''}>${b}</option>`).join('')}
                            </select>
                        </div>
                        <div class="col-md-2 mb-2">
                            <label class="form-label small">Department</label>
                            <select class="form-select form-select-sm" data-idx="${idx}" onchange="InvoiceEdit.onAllocationDeptChange(${idx}, this.value)">
                                <option value="">Select...</option>
                                ${departments.map(d => `<option value="${d}" ${d === alloc.department ? 'selected' : ''}>${d}</option>`).join('')}
                            </select>
                        </div>
                        <div class="col-md-2 mb-2" ${hasSubdepts ? '' : 'style="display: none;"'}>
                            <label class="form-label small">Subdepartment</label>
                            <select class="form-select form-select-sm" data-idx="${idx}" onchange="InvoiceEdit.onAllocationFieldChange(${idx}, 'subdepartment', this.value)">
                                <option value="">N/A</option>
                                ${subdepartments.map(s => `<option value="${s}" ${s === alloc.subdepartment ? 'selected' : ''}>${s}</option>`).join('')}
                            </select>
                        </div>
                        <div class="col-md-2 mb-2">
                            <label class="form-label small">Allocation %</label>
                            <div class="input-group input-group-sm">
                                <input type="number" class="form-control alloc-percent" data-idx="${idx}"
                                       value="${alloc.allocation_percent || ''}" min="0" max="100" step="0.01"
                                       onchange="InvoiceEdit.onAllocationPercentChange(${idx}, this.value)"
                                       onkeyup="InvoiceEdit.onAllocationPercentChange(${idx}, this.value)">
                                <span class="input-group-text">%</span>
                            </div>
                        </div>
                        <div class="col-md-3 mb-2">
                            <label class="form-label small">Value (${currency})</label>
                            <input type="number" class="form-control form-control-sm alloc-value" data-idx="${idx}"
                                   value="${allocValue.toFixed(2)}" min="0" step="0.01"
                                   onchange="InvoiceEdit.onAllocationValueChange(${idx}, this.value)"
                                   onkeyup="InvoiceEdit.onAllocationValueChange(${idx}, this.value)">
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-md-6 mb-2">
                            <small class="text-muted">Manager: ${manager || '--'}</small>
                        </div>
                        <div class="col-md-6 mb-2">
                            <div class="form-check form-check-inline">
                                <input class="form-check-input alloc-reinvoice-check" type="checkbox" data-idx="${idx}"
                                       ${hasReinvoice ? 'checked' : ''} onchange="InvoiceEdit.onReinvoiceCheckChange(${idx}, this.checked)">
                                <label class="form-check-label small">Reinvoice to:</label>
                                <span class="reinvoice-total-badge badge bg-secondary ms-2" data-idx="${idx}" style="display: ${hasReinvoice ? '' : 'none'};">0%</span>
                            </div>
                        </div>
                    </div>
                    <div class="reinvoice-section" data-idx="${idx}" style="display: ${hasReinvoice ? '' : 'none'};">
                        <div class="reinvoice-lines-container" data-idx="${idx}"></div>
                        <div class="row mt-1">
                            <div class="col-12">
                                <button type="button" class="btn btn-outline-secondary btn-sm" onclick="InvoiceEdit.addReinvoiceLine(${idx}, true)">
                                    <i class="bi bi-plus"></i> Add Reinvoice Line
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

        this.updateAllocationTotalBadge();

        // Initialize reinvoice lines for allocations with existing reinvoice destinations
        this.initializeReinvoiceLines();
    },

    // Initialize reinvoice lines from existing data
    async initializeReinvoiceLines() {
        for (let idx = 0; idx < this.editAllocations.length; idx++) {
            const alloc = this.editAllocations[idx];
            // Support both new reinvoice_destinations array and legacy single reinvoice fields
            if (alloc.reinvoice_destinations && alloc.reinvoice_destinations.length > 0) {
                // New multi-destination format
                for (const dest of alloc.reinvoice_destinations) {
                    await this.addReinvoiceLine(idx, false, dest);
                }
            } else if (alloc.reinvoice_to) {
                // Legacy single destination - migrate to new format
                const legacyDest = {
                    company: alloc.reinvoice_to,
                    brand: alloc.reinvoice_brand,
                    department: alloc.reinvoice_department,
                    subdepartment: alloc.reinvoice_subdepartment,
                    percentage: 100
                };
                this.editAllocations[idx].reinvoice_destinations = [legacyDest];
                await this.addReinvoiceLine(idx, false, legacyDest);
            }
            this.updateReinvoiceTotalBadge(idx);
        }
    },

    // Add reinvoice line
    async addReinvoiceLine(allocIdx, redistribute = false, existingData = null) {
        const container = document.querySelector(`.reinvoice-lines-container[data-idx="${allocIdx}"]`);
        if (!container) return;

        // Get companies list
        const companies = this.companiesData.map(c => c.company);

        const lineCount = container.children.length;
        let newPercentage = existingData ? existingData.percentage : 100;

        // If redistributing, update all existing lines to equal percentage
        if (redistribute && lineCount > 0) {
            newPercentage = 100 / (lineCount + 1);
            container.querySelectorAll('.reinvoice-percent').forEach(input => {
                input.value = newPercentage.toFixed(2);
            });
        }

        const lineId = `reinvoice-line-${allocIdx}-${Date.now()}`;
        const line = document.createElement('div');
        line.className = 'reinvoice-line row mb-1 align-items-center';
        line.id = lineId;

        line.innerHTML = `
            <div class="col-md-2">
                <select class="form-select form-select-sm reinvoice-company" onchange="InvoiceEdit.onReinvoiceCompanyChange('${lineId}', ${allocIdx})">
                    <option value="">Company...</option>
                    ${companies.map(c => `<option value="${c}" ${existingData && c === existingData.company ? 'selected' : ''}>${c}</option>`).join('')}
                </select>
            </div>
            <div class="col-md-2">
                <select class="form-select form-select-sm reinvoice-brand">
                    <option value="">Brand...</option>
                </select>
            </div>
            <div class="col-md-2">
                <select class="form-select form-select-sm reinvoice-dept" onchange="InvoiceEdit.onReinvoiceDeptChange('${lineId}', ${allocIdx})">
                    <option value="">Dept...</option>
                </select>
            </div>
            <div class="col-md-2">
                <select class="form-select form-select-sm reinvoice-subdept" onchange="InvoiceEdit.updateReinvoiceTotalBadge(${allocIdx})">
                    <option value="">N/A</option>
                </select>
            </div>
            <div class="col-md-2">
                <div class="input-group input-group-sm">
                    <input type="number" class="form-control reinvoice-percent" value="${newPercentage.toFixed(2)}"
                           min="0" max="100" step="0.01" onchange="InvoiceEdit.updateReinvoiceTotalBadge(${allocIdx})">
                    <span class="input-group-text">%</span>
                </div>
            </div>
            <div class="col-md-2">
                <button type="button" class="btn btn-outline-danger btn-sm" onclick="InvoiceEdit.removeReinvoiceLine('${lineId}', ${allocIdx})">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
        `;

        container.appendChild(line);

        // Populate brands, departments and subdepartments if existing data
        if (existingData && existingData.company) {
            const brandSelect = line.querySelector('.reinvoice-brand');
            const deptSelect = line.querySelector('.reinvoice-dept');
            const subdeptSelect = line.querySelector('.reinvoice-subdept');

            const [brands, depts] = await Promise.all([
                fetch(`/api/brands/${encodeURIComponent(existingData.company)}`).then(r => r.json()),
                fetch(`/api/departments/${encodeURIComponent(existingData.company)}`).then(r => r.json())
            ]);

            brandSelect.innerHTML = '<option value="">Brand...</option>';
            brands.forEach(b => {
                const opt = document.createElement('option');
                opt.value = b;
                opt.textContent = b;
                if (b === existingData.brand) opt.selected = true;
                brandSelect.appendChild(opt);
            });

            deptSelect.innerHTML = '<option value="">Dept...</option>';
            depts.forEach(d => {
                const opt = document.createElement('option');
                opt.value = d;
                opt.textContent = d;
                if (d === existingData.department) opt.selected = true;
                deptSelect.appendChild(opt);
            });

            if (existingData.department) {
                const subdepts = await fetch(`/api/subdepartments/${encodeURIComponent(existingData.company)}/${encodeURIComponent(existingData.department)}`).then(r => r.json());
                subdeptSelect.innerHTML = '<option value="">N/A</option>';
                subdepts.forEach(s => {
                    const opt = document.createElement('option');
                    opt.value = s;
                    opt.textContent = s;
                    if (s === existingData.subdepartment) opt.selected = true;
                    subdeptSelect.appendChild(opt);
                });
            }
        }

        this.updateReinvoiceTotalBadge(allocIdx);
    },

    // Remove reinvoice line
    removeReinvoiceLine(lineId, allocIdx) {
        const line = document.getElementById(lineId);
        if (line) {
            line.remove();
        }

        // If no lines left, uncheck the reinvoice checkbox
        const container = document.querySelector(`.reinvoice-lines-container[data-idx="${allocIdx}"]`);
        if (container && container.children.length === 0) {
            const checkbox = document.querySelector(`.alloc-reinvoice-check[data-idx="${allocIdx}"]`);
            if (checkbox) checkbox.checked = false;
            const section = document.querySelector(`.reinvoice-section[data-idx="${allocIdx}"]`);
            if (section) section.style.display = 'none';
            const badge = document.querySelector(`.reinvoice-total-badge[data-idx="${allocIdx}"]`);
            if (badge) badge.style.display = 'none';
        }

        this.updateReinvoiceTotalBadge(allocIdx);
    },

    // Reinvoice company change handler
    async onReinvoiceCompanyChange(lineId, allocIdx) {
        const line = document.getElementById(lineId);
        if (!line) return;

        const company = line.querySelector('.reinvoice-company').value;
        const brandSelect = line.querySelector('.reinvoice-brand');
        const deptSelect = line.querySelector('.reinvoice-dept');
        const subdeptSelect = line.querySelector('.reinvoice-subdept');

        brandSelect.innerHTML = '<option value="">Brand...</option>';
        deptSelect.innerHTML = '<option value="">Dept...</option>';
        subdeptSelect.innerHTML = '<option value="">N/A</option>';

        if (company) {
            const [brands, depts] = await Promise.all([
                fetch(`/api/brands/${encodeURIComponent(company)}`).then(r => r.json()),
                fetch(`/api/departments/${encodeURIComponent(company)}`).then(r => r.json())
            ]);

            brands.forEach(b => {
                const opt = document.createElement('option');
                opt.value = b;
                opt.textContent = b;
                brandSelect.appendChild(opt);
            });

            depts.forEach(d => {
                const opt = document.createElement('option');
                opt.value = d;
                opt.textContent = d;
                deptSelect.appendChild(opt);
            });
        }

        this.updateReinvoiceTotalBadge(allocIdx);
    },

    // Reinvoice department change handler
    async onReinvoiceDeptChange(lineId, allocIdx) {
        const line = document.getElementById(lineId);
        if (!line) return;

        const company = line.querySelector('.reinvoice-company').value;
        const department = line.querySelector('.reinvoice-dept').value;
        const subdeptSelect = line.querySelector('.reinvoice-subdept');

        subdeptSelect.innerHTML = '<option value="">N/A</option>';

        if (company && department) {
            const subdepts = await fetch(`/api/subdepartments/${encodeURIComponent(company)}/${encodeURIComponent(department)}`).then(r => r.json());
            subdepts.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s;
                opt.textContent = s;
                subdeptSelect.appendChild(opt);
            });
        }

        this.updateReinvoiceTotalBadge(allocIdx);
    },

    // Update reinvoice total badge
    updateReinvoiceTotalBadge(allocIdx) {
        const container = document.querySelector(`.reinvoice-lines-container[data-idx="${allocIdx}"]`);
        const badge = document.querySelector(`.reinvoice-total-badge[data-idx="${allocIdx}"]`);
        if (!container || !badge) return;

        let total = 0;
        container.querySelectorAll('.reinvoice-percent').forEach(input => {
            total += parseFloat(input.value) || 0;
        });

        badge.textContent = `${total.toFixed(1)}%`;
        badge.className = total <= 100 ? 'reinvoice-total-badge badge bg-success ms-2' : 'reinvoice-total-badge badge bg-danger ms-2';
    },

    // Get reinvoice destinations for an allocation
    getReinvoiceDestinations(allocIdx) {
        const container = document.querySelector(`.reinvoice-lines-container[data-idx="${allocIdx}"]`);
        const destinations = [];
        if (!container) return destinations;

        container.querySelectorAll('.reinvoice-line').forEach(line => {
            const company = line.querySelector('.reinvoice-company').value;
            const brand = line.querySelector('.reinvoice-brand').value;
            const department = line.querySelector('.reinvoice-dept').value;
            const subdepartment = line.querySelector('.reinvoice-subdept').value;
            const percentage = parseFloat(line.querySelector('.reinvoice-percent').value) || 0;

            if (company && percentage > 0) {
                destinations.push({
                    company,
                    brand: brand || null,
                    department: department || null,
                    subdepartment: subdepartment || null,
                    percentage
                });
            }
        });

        return destinations;
    },

    // Reinvoice checkbox change handler
    onReinvoiceCheckChange(idx, checked) {
        const section = document.querySelector(`.reinvoice-section[data-idx="${idx}"]`);
        const badge = document.querySelector(`.reinvoice-total-badge[data-idx="${idx}"]`);
        const container = document.querySelector(`.reinvoice-lines-container[data-idx="${idx}"]`);

        if (checked) {
            section.style.display = '';
            badge.style.display = '';
            // Add first line if none exist
            if (container && container.children.length === 0) {
                this.addReinvoiceLine(idx, false);
            }
        } else {
            section.style.display = 'none';
            badge.style.display = 'none';
            // Clear all reinvoice lines
            if (container) {
                container.innerHTML = '';
            }
            this.editAllocations[idx].reinvoice_destinations = [];
        }
    },

    // Helper functions for organizational structure
    getBrandsForCompany(company) {
        if (!this.organizationalStructure || !company) return [];
        const brands = new Set();
        this.organizationalStructure.filter(s => s.company === company).forEach(s => {
            if (s.brand) brands.add(s.brand);
        });
        return Array.from(brands).sort();
    },

    getDepartmentsForCompany(company) {
        if (!this.organizationalStructure || !company) return [];
        const depts = new Set();
        this.organizationalStructure.filter(s => s.company === company).forEach(s => {
            if (s.department) depts.add(s.department);
        });
        return Array.from(depts).sort();
    },

    getSubdepartmentsForDept(company, department) {
        if (!this.organizationalStructure || !company || !department) return [];
        const subdepts = new Set();
        this.organizationalStructure.filter(s =>
            s.company === company && s.department === department
        ).forEach(s => {
            if (s.subdepartment) subdepts.add(s.subdepartment);
        });
        return Array.from(subdepts).sort();
    },

    getManagerForDepartment(company, department, subdepartment, brand) {
        if (!this.organizationalStructure || !company || !department) return null;
        const match = this.organizationalStructure.find(s =>
            s.company === company &&
            s.department === department &&
            (!subdepartment || s.subdepartment === subdepartment) &&
            (!brand || s.brand === brand)
        );
        return match?.manager || null;
    },

    // Allocation field change handlers
    onAllocationFieldChange(idx, field, value) {
        this.editAllocations[idx][field] = value || null;

        // Update responsible based on company/dept/subdept/brand
        const company = document.getElementById('editDedicatedCompany').value;
        const alloc = this.editAllocations[idx];
        alloc.responsible = this.getManagerForDepartment(company, alloc.department, alloc.subdepartment, alloc.brand);
    },

    onAllocationDeptChange(idx, value) {
        const company = document.getElementById('editDedicatedCompany').value;
        const brand = this.editAllocations[idx].brand;

        this.editAllocations[idx].department = value;
        this.editAllocations[idx].subdepartment = '';
        this.editAllocations[idx].responsible = this.getManagerForDepartment(company, value, null, brand);
        this.renderEditAllocations();
    },

    onAllocationPercentChange(idx, value) {
        const percent = parseFloat(value) || 0;
        const baseValue = this.getBaseValue();
        this.editAllocations[idx].allocation_percent = percent;
        this.editAllocations[idx].allocation_value = (baseValue * percent) / 100;

        // Update value field without re-rendering (to avoid losing focus)
        const valueInput = document.querySelector(`.alloc-value[data-idx="${idx}"]`);
        if (valueInput) {
            valueInput.value = this.editAllocations[idx].allocation_value.toFixed(2);
        }

        // Redistribute remaining to other unlocked allocations
        this.redistributeOtherAllocations(idx);
    },

    onAllocationValueChange(idx, value) {
        const allocValue = parseFloat(value) || 0;
        const baseValue = this.getBaseValue();

        this.editAllocations[idx].allocation_value = allocValue;
        this.editAllocations[idx].allocation_percent = baseValue > 0 ? (allocValue / baseValue) * 100 : 0;

        // Update percent field without re-rendering (to avoid losing focus)
        const percentInput = document.querySelector(`.alloc-percent[data-idx="${idx}"]`);
        if (percentInput) {
            percentInput.value = this.editAllocations[idx].allocation_percent.toFixed(2);
        }

        // Redistribute remaining to other unlocked allocations
        this.redistributeOtherAllocations(idx);
    },

    // Redistribute remaining percentage equally among other unlocked allocations
    redistributeOtherAllocations(changedIdx) {
        const count = this.editAllocations.length;
        if (count <= 1) {
            this.updateAllocationTotalBadge();
            return;
        }

        // Get indices of unlocked allocations (excluding the changed one)
        const unlockedOthers = this.editAllocations
            .map((a, i) => ({ alloc: a, idx: i }))
            .filter(item => !item.alloc.locked && item.idx !== changedIdx);

        if (unlockedOthers.length === 0) {
            this.updateAllocationTotalBadge();
            return;
        }

        const changedPercent = this.editAllocations[changedIdx].allocation_percent || 0;

        // Calculate total locked percent (excluding the changed allocation)
        let lockedPercent = 0;
        this.editAllocations.forEach((a, i) => {
            if (a.locked && i !== changedIdx) {
                lockedPercent += parseFloat(a.allocation_percent) || 0;
            }
        });

        const remaining = 100 - changedPercent - lockedPercent;
        const perOther = remaining / unlockedOthers.length;
        const baseValue = this.getBaseValue();

        unlockedOthers.forEach(item => {
            item.alloc.allocation_percent = perOther;
            item.alloc.allocation_value = (baseValue * perOther) / 100;

            // Update UI without re-rendering
            const pInput = document.querySelector(`.alloc-percent[data-idx="${item.idx}"]`);
            const vInput = document.querySelector(`.alloc-value[data-idx="${item.idx}"]`);
            if (pInput) pInput.value = perOther.toFixed(2);
            if (vInput) vInput.value = item.alloc.allocation_value.toFixed(2);
        });

        this.updateAllocationTotalBadge();
    },

    toggleLock(index) {
        this.editAllocations[index].locked = !this.editAllocations[index].locked;
        this.renderEditAllocations();
    },

    openAllocationComment(index) {
        const alloc = this.editAllocations[index];
        const currency = document.getElementById('editCurrency').value || 'RON';
        const baseValue = this.getBaseValue();
        const allocValue = (baseValue * (parseFloat(alloc.allocation_percent) || 0)) / 100;

        document.getElementById('allocationCommentIndex').value = index;
        const deptPart = alloc.department || '-';
        const brandPart = alloc.brand ? ` (${alloc.brand})` : '';
        document.getElementById('allocationCommentDetails').textContent =
            `${deptPart}${brandPart} - ${this.formatCurrencyNoSymbol(allocValue)} ${currency} (${alloc.allocation_percent || 0}%)`;
        document.getElementById('allocationCommentText').value = alloc.comment || '';

        const modal = new bootstrap.Modal(document.getElementById('allocationCommentModal'));
        modal.show();
    },

    saveAllocationComment() {
        const index = parseInt(document.getElementById('allocationCommentIndex').value);
        const comment = document.getElementById('allocationCommentText').value;
        this.editAllocations[index].comment = comment || null;

        bootstrap.Modal.getInstance(document.getElementById('allocationCommentModal')).hide();
        this.renderEditAllocations();
    },

    recalculateAllocationValues() {
        const baseValue = this.getBaseValue();
        this.editAllocations.forEach(a => {
            a.allocation_value = (baseValue * (a.allocation_percent || 0)) / 100;
        });
    },

    updateAllocationTotalBadge() {
        const totalPercent = this.editAllocations.reduce((sum, a) => sum + (parseFloat(a.allocation_percent) || 0), 0);
        const totalValue = this.editAllocations.reduce((sum, a) => sum + (parseFloat(a.allocation_value) || 0), 0);
        const currency = document.getElementById('editCurrency').value || 'RON';
        const badge = document.getElementById('allocationTotalBadge');

        if (badge) {
            badge.textContent = `${totalPercent.toFixed(2)}% | ${this.formatCurrencyNoSymbol(totalValue)} ${currency}`;
            // Valid if 100% to 100.1% (allow small overdraft for rounding)
            badge.className = 'badge ms-2 ' + ((totalPercent >= 100 && totalPercent <= 100.1) ? 'bg-success' : 'bg-danger');
        }
    },

    // Upload file
    async uploadFile() {
        const fileInput = document.getElementById('editInvoiceFile');
        const file = fileInput.files[0];

        if (!file) {
            JarvisDialog.alert('Please select a file first', { type: 'warning' });
            return;
        }

        const invoiceDate = document.getElementById('editInvoiceDate').value || '';
        const company = document.getElementById('editDedicatedCompany').value || 'Unknown Company';
        const invoiceNumber = document.getElementById('editInvoiceNumber').value || 'Unknown Invoice';

        const formData = new FormData();
        formData.append('file', file);
        formData.append('invoice_date', invoiceDate);
        formData.append('company', company);
        formData.append('invoice_number', invoiceNumber);

        const btn = document.getElementById('uploadEditFileBtn');
        const originalText = btn.innerHTML;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Uploading...';
        btn.disabled = true;

        try {
            const response = await fetch('/api/drive/upload', {
                method: 'POST',
                body: formData
            });
            const result = await response.json();

            if (result.success && result.drive_link) {
                document.getElementById('editDriveLink').value = result.drive_link;
                JarvisToast.success('File uploaded successfully to Google Drive!');
                fileInput.value = '';
            } else {
                JarvisDialog.alert('Upload failed: ' + (result.error || 'Unknown error'), { type: 'error' });
            }
        } catch (e) {
            JarvisDialog.alert('Upload error: ' + e.message, { type: 'error' });
        } finally {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    },

    // Save invoice
    async saveInvoice() {
        const invoiceId = document.getElementById('editInvoiceId').value;
        const totalPercent = this.editAllocations.reduce((sum, a) => sum + (a.allocation_percent || 0), 0);

        // Validate allocations
        if (totalPercent < 100 || totalPercent > 100.1) {
            JarvisDialog.alert(`Allocations must sum to 100% (max 0.1% overdraft allowed). Current total: ${totalPercent.toFixed(2)}%`, { type: 'warning', title: 'Validation Error' });
            return;
        }

        if (this.editAllocations.some(a => !a.department)) {
            JarvisDialog.alert('All allocations must have a department', { type: 'warning', title: 'Validation Error' });
            return;
        }

        this.recalculateAllocationValues();

        const subtractVat = document.getElementById('editSubtractVat').checked;
        const vatRateSelect = document.getElementById('editVatRateId');
        const selectedOption = vatRateSelect.options[vatRateSelect.selectedIndex];
        const vatRate = subtractVat && selectedOption && selectedOption.dataset.rate ? parseFloat(selectedOption.dataset.rate) : null;
        const vatRateId = subtractVat && vatRateSelect.value ? parseInt(vatRateSelect.value) : null;
        const netValue = subtractVat ? parseFloat(document.getElementById('editNetValue').value) : null;
        const dedicatedCompany = document.getElementById('editDedicatedCompany').value;

        const invoiceData = {
            supplier: document.getElementById('editSupplier').value,
            invoice_number: document.getElementById('editInvoiceNumber').value,
            invoice_date: document.getElementById('editInvoiceDate').value,
            invoice_value: parseFloat(document.getElementById('editInvoiceValue').value),
            currency: document.getElementById('editCurrency').value,
            drive_link: document.getElementById('editDriveLink').value,
            comment: document.getElementById('editComment').value,
            status: document.getElementById('editStatus').value,
            payment_status: document.getElementById('editPaymentStatus').value,
            subtract_vat: subtractVat,
            vat_rate: vatRate,
            vat_rate_id: vatRateId,
            net_value: netValue
        };

        // Collect reinvoice destinations for each allocation
        const allocationsData = this.editAllocations.map((a, idx) => ({
            company: dedicatedCompany,
            brand: a.brand || null,
            department: a.department,
            subdepartment: a.subdepartment || null,
            allocation_percent: a.allocation_percent,
            allocation_value: a.allocation_value,
            responsible: a.responsible || null,
            reinvoice_destinations: this.getReinvoiceDestinations(idx),
            comment: a.comment || null,
            locked: a.locked || false
        }));

        if (typeof showLoading === 'function') showLoading('Saving invoice...');

        try {
            // Save invoice details
            const invoiceRes = await fetch(`/api/db/invoices/${invoiceId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(invoiceData)
            });
            const invoiceResult = await invoiceRes.json();

            if (!invoiceResult.success && invoiceRes.status !== 404) {
                JarvisDialog.alert('Error updating invoice: ' + (invoiceResult.error || 'Unknown error'), { type: 'error' });
                return;
            }

            // Save allocations
            const sendNotification = document.getElementById('sendNotificationToggle').checked;
            const allocRes = await fetch(`/api/db/invoices/${invoiceId}/allocations`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ allocations: allocationsData, send_notification: sendNotification })
            });
            const allocResult = await allocRes.json();

            if (allocResult.success) {
                bootstrap.Modal.getInstance(document.getElementById('editInvoiceModal')).hide();

                // Call the callback if provided
                if (this.onSaveCallback) {
                    await this.onSaveCallback();
                }

                JarvisToast.success('Invoice and allocations updated successfully!');
            } else {
                JarvisDialog.alert('Error updating allocations: ' + (allocResult.error || 'Unknown error'), { type: 'error' });
            }
        } catch (e) {
            JarvisDialog.alert('Error: ' + e.message, { type: 'error' });
        } finally {
            if (typeof hideLoading === 'function') hideLoading();
        }
    },

    // Formatting helpers
    formatCurrency(value, currency = 'RON') {
        return new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0) + ' ' + currency;
    },

    formatCurrencyNoSymbol(value) {
        return new Intl.NumberFormat('ro-RO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value || 0);
    },

    formatDateRomanian(dateStr) {
        if (!dateStr) return '-';
        const d = new Date(dateStr);
        if (isNaN(d.getTime())) return '-';
        return d.toLocaleDateString('ro-RO');
    },

    getStatusClass(status) {
        const classes = {
            'Nebugetata': 'bg-danger',
            'New': 'bg-info',
            'new': 'bg-info',
            'Processing': 'bg-warning text-dark',
            'Processed': 'bg-success',
            'processed': 'bg-success',
            'incomplete': 'bg-secondary'
        };
        return classes[status] || 'bg-secondary';
    }
};

// Export for global access
window.InvoiceEdit = InvoiceEdit;

// Shortcut functions for use in onclick handlers
function viewInvoice(id) { InvoiceEdit.viewInvoice(id); }
function editInvoice(id) { InvoiceEdit.openEditModal(id); }
