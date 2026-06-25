// static/js/main.js

document.addEventListener('alpine:init', () => {

    // ========================================================================
    // == GLOBAL & USER-FACING COMPONENTS
    // ========================================================================

    Alpine.data('themeManager', () => ({
        theme: localStorage.getItem('theme') || 'system',
        isDarkMode: false,
        init() { this.applyTheme(); window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { if (this.theme === 'system') this.applyTheme(); }); window.addEventListener('set-theme', (event) => { this.setTheme(event.detail); }); },
        applyTheme() { if (this.theme === 'dark' || (this.theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)) { document.documentElement.classList.add('dark'); this.isDarkMode = true; } else { document.documentElement.classList.remove('dark'); this.isDarkMode = false; } },
        setTheme(newTheme) { this.theme = newTheme; localStorage.setItem('theme', newTheme); this.applyTheme(); }
    }));

    Alpine.data('storefront', (currencySymbol) => ({
        assets: [], activeFilter: 'all', currency: currencySymbol,
        init() { try { const dataElement = document.getElementById('storefront-data'); if (dataElement) this.assets = JSON.parse(dataElement.textContent); } catch (e) { console.error('Error parsing storefront data:', e); } },
        get filteredAssets() { if (this.activeFilter === 'all') return this.assets; return this.assets.filter(asset => asset.asset_type === this.activeFilter); },
        setFilter(type) { this.activeFilter = type; },
        formatCurrency(amount) { return new Intl.NumberFormat('en-US', { style: 'decimal', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount || 0); }
    }));

    Alpine.data('assetDetail', (currencySymbol) => ({
        asset: {}, countdown: 'Loading...', currency: currencySymbol, visibleReviews: 3,
        toast: { show: false, message: '', type: 'success' },
        qrCodeUrl: '', showQRCode: false,

        init() { try { const dataElement = document.getElementById('asset-data'); if (dataElement) this.asset = JSON.parse(dataElement.textContent); } catch (e) { console.error('Error parsing asset detail data:', e); } if (this.asset.asset_type === 'TICKET' && this.asset.event_date) { this.countdownInterval = setInterval(() => this.updateCountdown(), 1000); this.updateCountdown(); } },

        showToast(message, type = 'success') {
            this.toast.message = message;
            this.toast.type = type;
            this.toast.show = true;
            setTimeout(() => { this.toast.show = false; }, 3000);
        },

        updateCountdown() { const eventDate = new Date(this.asset.event_date).getTime(); const now = new Date().getTime(); const distance = eventDate - now; if (distance < 0) { this.countdown = "EVENT HAS PASSED"; if (this.countdownInterval) clearInterval(this.countdownInterval); return; } const d = Math.floor(distance / (1000 * 60 * 60 * 24)); const h = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60)); const m = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60)); const s = Math.floor((distance % (1000 * 60)) / 1000); this.countdown = `${d}d ${h}h ${m}m ${s}s`; },
        get averageRating() { if (!this.asset.reviews || this.asset.reviews.length === 0) return 'N/A'; const total = this.asset.reviews.reduce((sum, review) => sum + review.rating, 0); return (total / this.asset.reviews.length).toFixed(1); },
        showMoreReviews() { this.visibleReviews += 5; },
        renderMarkdown(text) {
            if (!text) return '';
            const mdPattern = /(?:^#{1,6}\s|^\s*[-*+]\s|^\s*\d+\.\s|\*\*.+\*\*|__.+__|`.+`|\[.+\]\(.+\)|^>\s|^```|!\[)/m;
            const hasMarkdown = mdPattern.test(text);
            if (hasMarkdown && window.marked) {
                try { return window.marked.parse(text); } catch (e) { /* fall through */ }
            }
            const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
            return escaped.replace(/\n/g, '<br>');
        },
        formatCurrency(amount) { return new Intl.NumberFormat('en-US', { style: 'decimal', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount || 0); },

        toggleQRCode() {
            try {
                if (!this.qrCodeUrl) {
                    const icsString = this.generateICSString(true);
                    this.qrCodeUrl = `https://api.qrserver.com/v1/create-qr-code/?size=400x400&ecc=L&margin=1&format=svg&data=${encodeURIComponent(icsString)}`;
                }
                this.showQRCode = !this.showQRCode;
            } catch (err) {
                console.error("Error generating QR code:", err);
                this.showToast("Could not generate calendar code. Invalid event details.", "error");
            }
        },

        getEventDates() {
            let startDt = new Date();
            let endDt = new Date(startDt.getTime() + 60 * 60 * 1000); // default +1 hour

            const evtDate = this.asset.eventDetails?.date;
            const evtTime = this.asset.eventDetails?.time;

            if (evtDate) {
                // Try parsing as-is first
                let parsed = new Date(evtDate);

                // If we also have a time, try to compose them safely
                if (evtTime) {
                    // Make sure date is in YYYY-MM-DD format before appending T
                    const isIsoRegex = /^\d{4}-\d{2}-\d{2}$/;
                    if (isIsoRegex.test(evtDate)) {
                        const composed = new Date(`${evtDate}T${evtTime}`);
                        if (!isNaN(composed.getTime())) parsed = composed;
                    } else {
                        // Fallback: use the date parsed, set hours/mins from time
                        const [hours, minutes] = evtTime.split(':');
                        if (!isNaN(parsed.getTime()) && hours !== undefined && minutes !== undefined) {
                            parsed.setHours(parseInt(hours, 10), parseInt(minutes, 10), 0);
                        }
                    }
                }

                if (!isNaN(parsed.getTime())) {
                    startDt = parsed;
                    endDt = new Date(startDt.getTime() + 60 * 60 * 1000);
                }
            }

            // Local time formatting for ICS (Floating Time)
            const formatICS = (d) => {
                const pad = (n) => n < 10 ? '0' + n : n;
                return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}T${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
            };

            // UTC format for Google Calendar
            const formatGoogle = (d) => {
                return d.toISOString().replace(/-|:|\.\d\d\d/g, "");
            };

            return {
                icsStart: formatICS(startDt),
                icsEnd: formatICS(endDt),
                googleStart: formatGoogle(startDt),
                googleEnd: formatGoogle(endDt)
            };
        },

        getEventDescription() {
            const asset = this.asset;
            let fullDescription = asset.description || '';

            if (asset.details && asset.details.postPurchaseInstructions) {
                fullDescription += `\n\nNotes / Instructions:\n${asset.details.postPurchaseInstructions}`;
            }

            const link = asset.eventDetails?.link;
            if (link) {
                fullDescription += `\n\nWebinar Link: ${link}`;
            }

            if (asset.files && asset.files.length > 0) {
                fullDescription += `\n\nIncluded Files/Links:\n`;
                asset.files.forEach(f => {
                    const linkUrl = f.link.startsWith('http') ? f.link : (window.location.origin + f.link);
                    fullDescription += `- ${f.title}: ${linkUrl}\n`;
                });
            }
            return fullDescription;
        },

        generateICSString(isForQR = false) {
            const asset = this.asset;
            const title = asset.title || 'Event';
            let description = this.getEventDescription().replace(/\n/g, '\\n');
            const location = asset.eventDetails?.link || '';
            const dates = this.getEventDates();

            // Truncate description for QR codes to maintain scannability
            if (isForQR && description.length > 300) {
                description = description.substring(0, 297) + '...';
            }

            let alarms = '';
            // Omit alarms for QR to reduce string length
            if (!isForQR) {
                const reminders = [
                    { trigger: '-P1D', desc: '1 day' },
                    { trigger: '-PT1H', desc: '1 hour' },
                    { trigger: '-PT5M', desc: '5 mins' }
                ];

                reminders.forEach(r => {
                    alarms += `BEGIN:VALARM\nTRIGGER:${r.trigger}\nACTION:DISPLAY\nDESCRIPTION:Reminder: ${title} in ${r.desc}\nEND:VALARM\n`;
                });
            }

            const now = new Date().toISOString().replace(/-|:|\.\d\d\d/g, "");
            return `BEGIN:VCALENDAR\nVERSION:2.0\nPROID:-//Nyota//Asset Calendar//EN\nBEGIN:VEVENT\nUID:${asset.id || Date.now()}@nyota.app\nDTSTAMP:${now}\nDTSTART:${dates.icsStart}\nDTEND:${dates.icsEnd}\nSUMMARY:${title}\nDESCRIPTION:${description}\nLOCATION:${location}\n${alarms}END:VEVENT\nEND:VCALENDAR`;
        },

        smartCalendarSave() {
            try {
                const userAgent = navigator.userAgent || navigator.vendor || window.opera;
                const isAndroid = /android/i.test(userAgent);

                if (isAndroid) {
                    window.open(this.getGoogleCalendarUrl(), '_blank');
                } else {
                    const icsString = this.generateICSString();
                    const blob = new Blob([icsString], { type: 'text/calendar;charset=utf-8' });
                    const link = document.createElement('a');
                    link.href = window.URL.createObjectURL(blob);
                    link.setAttribute('download', `${this.asset.slug || 'event'}.ics`);
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                }
            } catch (err) {
                console.error("Error saving to calendar:", err);
                this.showToast("Could not save to calendar. Invalid event details.", "error");
            }
        },

        getGoogleCalendarUrl() {
            const asset = this.asset;
            const title = encodeURIComponent(asset.title || 'Event');
            const description = encodeURIComponent(this.getEventDescription());
            const location = encodeURIComponent(asset.eventDetails?.link || '');
            const dates = this.getEventDates();

            return `https://www.google.com/calendar/render?action=TEMPLATE&text=${title}&details=${description}&location=${location}&dates=${dates.googleStart}/${dates.googleEnd}`;
        }
    }));

    Alpine.data('userLibrary', (currencySymbol) => ({
        purchasedAssets: [], activeTab: 'all', currency: currencySymbol,
        init() { try { const dataElement = document.getElementById('library-data'); if (dataElement) this.purchasedAssets = JSON.parse(dataElement.textContent); } catch (e) { console.error('Error parsing library data:', e); } },
        get filteredAssets() { if (this.activeTab === 'all') return this.purchasedAssets; return this.purchasedAssets.filter(asset => asset.asset_type === this.activeTab); },
        setTab(tab) { this.activeTab = tab; },
        formatCurrency(amount) { return new Intl.NumberFormat('en-US', { style: 'decimal', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount || 0); }
    }));

    Alpine.data('postPurchaseForm', (assetId, purchaseId, alreadyAnswered = false) => ({
        fields: [],
        formData: {},
        fileData: {},
        isSubmitting: false,
        submitted: false,
        alreadyAnswered: alreadyAnswered,
        // 'view' shows a read-only summary of submitted answers; 'edit' shows the form.
        mode: alreadyAnswered ? 'view' : 'edit',
        // In view mode the summary is a collapsed disclosure so it never competes with the
        // bought content above it. Expanded by default while filling/unlocking the form.
        open: !alreadyAnswered,
        init() {
            // Field definitions and any existing answers are read from JSON <script> tags rather
            // than inline attribute arguments — embedding the JSON directly in x-data breaks the
            // HTML attribute (its double quotes close the attribute early) and the form never renders.
            try {
                const el = document.getElementById('post-purchase-fields-' + assetId);
                const parsed = el ? JSON.parse(el.textContent || '[]') : [];
                this.fields = Array.isArray(parsed) ? parsed : [];
            } catch (e) {
                this.fields = [];
                console.error('Failed to parse post-purchase fields:', e);
            }

            let answers = {};
            try {
                const el = document.getElementById('post-purchase-answers-' + assetId);
                answers = el ? (JSON.parse(el.textContent || '{}') || {}) : {};
            } catch (e) {
                answers = {};
            }
            delete answers.tier; // internal subscription key — never shown or edited

            // Seed formData: reuse an existing answer when present, else a sensible empty default.
            this.fields.forEach(field => {
                const existing = answers[field.question];
                if (field.type === 'file') {
                    this.fileData[field.question] = null;
                    // Show original filename if already uploaded
                    this.formData[field.question] = (existing && existing.__file__)
                        ? existing.original_name : '';
                } else if (existing !== undefined && existing !== null) {
                    this.formData[field.question] = existing;
                } else {
                    this.formData[field.question] = field.type === 'checkbox' ? false : '';
                }
            });
        },
        // Human-readable value for the read-only summary.
        displayValue(field) {
            const v = this.formData[field.question];
            if (field.type === 'checkbox') return v ? 'Yes' : 'No';
            if (field.type === 'file') return v ? v : '—';
            return (v === '' || v === null || v === undefined) ? '—' : v;
        },
        handleFileSelect(question, event) {
            const file = event.target.files[0] || null;
            this.fileData[question] = file;
            this.formData[question] = file ? file.name : '';
        },
        get currentStep() {
            const total = this.fields.length;
            const answered = this.fields.filter(f => {
                if (f.type === 'file') return !!this.fileData[f.question];
                const v = this.formData[f.question];
                return v !== '' && v !== false && v !== null && v !== undefined;
            }).length;
            return { answered, total };
        },
        async submit() {
            this.isSubmitting = true;
            try {
                // Step 1: collect non-file answers
                const textAnswers = {};
                this.fields.forEach(f => {
                    if (f.type !== 'file') {
                        textAnswers[f.question] = this.formData[f.question];
                    }
                });

                // Step 2: submit text answers to existing endpoint
                if (Object.keys(textAnswers).length > 0) {
                    const r = await fetch(`/api/purchases/${purchaseId}/ticket-data`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ ticket_data: textAnswers })
                    });
                    const result = await r.json();
                    if (!r.ok || !result.success) {
                        alert(result.message || 'Error submitting answers.');
                        return;
                    }
                }

                // Step 3: upload each file answer
                for (const field of this.fields) {
                    if (field.type !== 'file') continue;
                    const file = this.fileData[field.question];
                    if (!file && field.required) {
                        alert(`Please select a file for "${field.question}".`);
                        return;
                    }
                    if (!file) continue;

                    const maxBytes = (field.maxSizeMb || 5) * 1024 * 1024;
                    if (file.size > maxBytes) {
                        alert(`"${field.question}": file exceeds the ${field.maxSizeMb || 5} MB limit.`);
                        return;
                    }

                    const fd = new FormData();
                    fd.append('question_name', field.question);
                    fd.append('file', file);
                    const fr = await fetch(`/api/purchases/${purchaseId}/ticket-file`, {
                        method: 'POST',
                        body: fd
                    });
                    const fres = await fr.json();
                    if (!fr.ok || !fres.success) {
                        alert(fres.message || `Error uploading file for "${field.question}".`);
                        return;
                    }
                }

                this.submitted = true;
                setTimeout(() => window.location.reload(), 1500);
            } catch (e) {
                alert('A network error occurred.');
            } finally {
                this.isSubmitting = false;
            }
        }
    }));

    // ========================================================================
    // == ADMIN COMPONENTS
    // ========================================================================

    Alpine.data('adminAssets', () => ({
        assets: [], filteredAssets: [], viewMode: 'list', searchTerm: '', statusFilter: 'all', typeFilter: 'all',
        sortBy: 'updated_at', sortAsc: false, selectedAssets: [], bulkAction: '', currentPage: 1, itemsPerPage: 10,

        init() {
            try {
                const dataElement = document.getElementById('assets-data');
                if (dataElement && dataElement.textContent) {
                    this.assets = Array.isArray(JSON.parse(dataElement.textContent)) ? JSON.parse(dataElement.textContent) : [];
                }
            } catch (e) { this.assets = []; console.error('Error parsing assets data:', e); }

            // Load UI preferences from localStorage
            const savedPreferences = JSON.parse(localStorage.getItem('adminAssetsPreferences')) || {};
            this.viewMode = savedPreferences.viewMode || 'list';
            this.searchTerm = savedPreferences.searchTerm || '';
            this.statusFilter = savedPreferences.statusFilter || 'all';
            this.typeFilter = savedPreferences.typeFilter || 'all';
            this.sortBy = savedPreferences.sortBy || 'updated_at';
            this.sortAsc = savedPreferences.sortAsc !== undefined ? savedPreferences.sortAsc : false;
            this.itemsPerPage = savedPreferences.itemsPerPage || 10;
            this.currentPage = savedPreferences.currentPage || 1; // Load currentPage

            this.$watch(() => [this.searchTerm, this.statusFilter, this.typeFilter, this.sortBy, this.sortAsc], () => {
                this.applyFiltersAndSort();
                this.currentPage = 1; // Reset to first page on filter/sort change
                this.savePreferences();
            });

            this.$watch(() => [this.viewMode, this.itemsPerPage, this.currentPage], () => this.savePreferences());

            this.applyFiltersAndSort(); // Initial application of filters and sort
        },

        savePreferences() {
            localStorage.setItem('adminAssetsPreferences', JSON.stringify({
                viewMode: this.viewMode,
                searchTerm: this.searchTerm,
                statusFilter: this.statusFilter,
                typeFilter: this.typeFilter,
                sortBy: this.sortBy,
                sortAsc: this.sortAsc,
                itemsPerPage: this.itemsPerPage,
                currentPage: this.currentPage,
            }));
        },

        applyFiltersAndSort() {
            let temp = [...this.assets];
            if (this.searchTerm.trim()) { const s = this.searchTerm.toLowerCase(); temp = temp.filter(a => (a.title && a.title.toLowerCase().includes(s)) || (a.description && a.description.toLowerCase().includes(s))); }
            if (this.statusFilter !== 'all') { temp = temp.filter(a => a.status === this.statusFilter); }
            if (this.typeFilter !== 'all') { temp = temp.filter(a => a.type.toLowerCase().replace(/_/g, '-') === this.typeFilter); }
            temp.sort((a, b) => { let vA, vB; switch (this.sortBy) { case 'title': vA = a.title.toLowerCase(); vB = b.title.toLowerCase(); break; case 'sales': vA = a.sales || 0; vB = b.sales || 0; break; case 'revenue': vA = a.revenue || 0; vB = b.revenue || 0; break; default: vA = new Date(a.updated_at); vB = new Date(b.updated_at); break; } if (vA < vB) return this.sortAsc ? -1 : 1; if (vA > vB) return this.sortAsc ? 1 : -1; return 0; });
            this.filteredAssets = temp;
        },

        // --- Pagination ---
        get paginatedAssets() {
            const start = (this.currentPage - 1) * this.itemsPerPage;
            const end = start + this.itemsPerPage;
            return this.filteredAssets.slice(start, end);
        },
        get totalPages() {
            return Math.ceil(this.filteredAssets.length / this.itemsPerPage);
        },
        goToPage(page) {
            if (page >= 1 && page <= this.totalPages) {
                this.currentPage = page;
            }
        },
        nextPage() {
            if (this.currentPage < this.totalPages) {
                this.currentPage++;
            }
        },
        prevPage() {
            if (this.currentPage > 1) {
                this.currentPage--;
            }
        },

        // --- Action Methods ---
        async applyBulkAction() {
            if (!this.bulkAction || this.selectedAssets.length === 0) return alert('Please select an action and at least one asset.');
            if (this.bulkAction === 'delete' && !confirm(`Permanently delete ${this.selectedAssets.length} asset(s)? This cannot be undone.`)) return;

            try {
                const response = await fetch('/admin/api/assets/bulk-action', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: this.bulkAction, ids: this.selectedAssets })
                });
                const result = await response.json();
                if (response.ok && result.success) {
                    alert(result.message);
                    window.location.reload();
                } else {
                    alert('Error: ' + (result.message || 'An unknown error occurred.'));
                }
            } catch (e) {
                alert('A server connection error occurred.');
            }
        },
        confirmDelete(assetId) {
            if (confirm('Are you sure you want to permanently delete this asset?')) {
                this.selectedAssets = [assetId];
                this.bulkAction = 'delete';
                this.applyBulkAction();
            }
        },
        async duplicateAsset(assetId) {
            if (confirm('Create a duplicate of this asset? It will be saved as a draft.')) {
                try {
                    const response = await fetch(`/admin/api/assets/${assetId}/duplicate`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                    });
                    const result = await response.json();
                    if (response.ok && result.success) {
                        alert(result.message);
                        window.location.reload();
                    } else {
                        alert('Error: ' + (result.message || 'An unknown error occurred.'));
                    }
                } catch (e) {
                    alert('A server connection error occurred.');
                }
            }
        },

        // --- UI & Helper Methods ---
        getStatusCount(status) { return this.assets.filter(a => a.status === status).length; },
        getTotalRevenue() { return this.assets.reduce((sum, asset) => sum + (parseFloat(asset.revenue) || 0), 0); },
        getTotalSales() { return this.assets.reduce((sum, asset) => sum + (parseInt(asset.sales) || 0), 0); },
        formatDate(iso) { if (!iso) return 'N/A'; return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }); },
        getStatusClasses(status) { return { 'Published': 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300', 'Draft': 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300', 'Archived': 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-300' }[status] || 'bg-gray-100 text-gray-800'; },
        getAssetTypeLabel(type) { if (!type) return 'Product'; return type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()); },
        toggleSelectAll(event) { if (event.target.checked) { this.selectedAssets = this.filteredAssets.map(a => a.id); } else { this.selectedAssets = []; } },
        hasActiveFilters() { return this.searchTerm || this.statusFilter !== 'all' || this.typeFilter !== 'all' },
        getActiveFilters() { let f = []; if (this.searchTerm) f.push({ key: 'searchTerm', label: `Search: "${this.searchTerm}"` }); if (this.statusFilter !== 'all') f.push({ key: 'statusFilter', label: `Status: ${this.statusFilter}` }); if (this.typeFilter !== 'all') f.push({ key: 'typeFilter', label: `Type: ${this.typeFilter.replace('-', ' ')}` }); return f; },
        removeFilter(key) { this[key] = key === 'searchTerm' ? '' : 'all'; },
        clearAllFilters() { this.searchTerm = ''; this.statusFilter = 'all'; this.typeFilter = 'all'; },
    }));

    Alpine.data('assetForm', () => ({
        step: 1,
        asset: { id: null, title: '', description: '', cover_image_url: null, story_snippet: '' },
        assetType: '',
        assetTypeEnum: '',
        contentItems: [],
        customFields: [],
        eventDetails: { link: '', maxAttendees: null, date: '', time: '', postPurchaseInstructions: '' },
        subscriptionDetails: { welcomeContent: '', benefits: '' },
        newsletterDetails: { welcomeFile: null, welcomeDescription: '', frequency: 'monthly' },
        pricing: { type: 'one-time', amount: null, billingCycle: 'monthly', tiers: [] },
        positionPreference: 'bottom',
        collectInfoMode: 'optional',
        steps: [{ number: 1, title: 'Type', subtitle: 'Choose content format' }, { number: 2, title: 'Details', subtitle: 'Describe your asset' }, { number: 3, title: 'Content', subtitle: 'Add files/links' }, { number: 4, title: 'Pricing', subtitle: 'Set your price' }],

        init() {
            const dataElement = document.getElementById('asset-form-data');
            if (dataElement && dataElement.textContent.trim() !== '{}') {
                const existing = JSON.parse(dataElement.textContent);
                this.asset = { id: existing.id, title: existing.title, description: existing.description, cover_image_url: existing.cover_image_url, story_snippet: existing.story };
                this.assetType = this.mapEnumTypeToFormType(existing.asset_type);
                this.assetTypeEnum = existing.asset_type;

                // Initialize content items with type detection
                this.contentItems = (existing.files || []).map(f => ({
                    ...f,
                    type: f.link && !f.link.startsWith('/content/') ? 'link' : 'upload'
                }));

                this.customFields = existing.custom_fields || [];

                // Initialize event details
                this.eventDetails = {
                    link: existing.eventDetails?.link || existing.event_location,
                    maxAttendees: existing.eventDetails?.maxAttendees || existing.max_attendees,
                    date: existing.eventDetails?.date || existing.event_date,
                    time: existing.eventDetails?.time || existing.event_time,
                    postPurchaseInstructions: existing.details?.postPurchaseInstructions || ''
                };

                // Initialize pricing and tiers
                const isSubscription = existing.is_subscription;
                this.pricing = {
                    type: isSubscription ? 'recurring' : 'one-time',
                    amount: existing.price,
                    billingCycle: existing.subscription_interval || 'monthly',
                    tiers: existing.details?.subscription_tiers || []
                };

                if (existing.details) {
                    this.subscriptionDetails = existing.details.welcomeContent ? existing.details : this.subscriptionDetails;
                    this.newsletterDetails = existing.details.frequency ? existing.details : this.newsletterDetails;
                }
                // FIX: Only jump to step 2 if we are EDITING an existing asset (has ID)
                this.step = existing.id ? 2 : 1;
            }
            this.$nextTick(() => { this._initMDEditors(); });
        },

        _initMDEditors() {
            if (typeof EasyMDE === 'undefined') return;
            const toolbar = ['bold', 'italic', 'heading', '|', 'quote', 'unordered-list', 'ordered-list', '|', 'link', '|', 'preview'];
            const descEl = document.getElementById('description');
            if (descEl && !descEl._mde) {
                const mde = new EasyMDE({ element: descEl, toolbar, minHeight: '80px', spellChecker: false, status: false });
                mde.codemirror.on('change', () => { this.asset.description = mde.value(); });
                if (this.asset.description) mde.value(this.asset.description);
                descEl._mde = mde;
            }
            const storyEl = document.getElementById('story');
            if (storyEl && !storyEl._mde) {
                const mde = new EasyMDE({ element: storyEl, toolbar, minHeight: '140px', spellChecker: false, status: false });
                mde.codemirror.on('change', () => { this.asset.story_snippet = mde.value(); });
                if (this.asset.story_snippet) mde.value(this.asset.story_snippet);
                storyEl._mde = mde;
            }
        },
        setAssetType(type) { this.assetType = type; this.assetTypeEnum = this.mapFormTypeToEnumType(type); },
        addContentItem(defaultType = 'upload') { this.contentItems.push({ type: defaultType, title: '', link: '', description: '' }); },
        removeContentItem(index) { this.contentItems.splice(index, 1); },
        addCustomField() { this.customFields.push({ type: 'text', question: '', required: false, options: [], _optionsRaw: '', accept: '', maxSizeMb: 5 }); },
        removeCustomField(index) { this.customFields.splice(index, 1); },
        addPricingTier() { this.pricing.tiers.push({ name: '', price: null, interval: 'monthly', description: '' }); },
        removePricingTier(index) { this.pricing.tiers.splice(index, 1); },
        previewCoverImage(event) { const file = event.target.files[0]; if (file) { this.asset.cover_image_url = URL.createObjectURL(file); } },
        submitForm(action) {
            // Clean custom fields: derive dropdown options + drop editor-only helpers.
            const cleanedCustomFields = (this.customFields || []).map(f => {
                const out = { type: f.type || 'text', question: f.question || '', required: !!f.required };
                if (f.type === 'select') {
                    out.options = (f._optionsRaw || (Array.isArray(f.options) ? f.options.join(', ') : ''))
                        .split(',').map(s => s.trim()).filter(Boolean);
                }
                if (f.type === 'file') {
                    out.accept = f.accept || '';
                    out.maxSizeMb = f.maxSizeMb || 5;
                }
                return out;
            }).filter(f => f.question.trim());

            // Prepare data for submission
            const allData = {
                action: action,
                asset: this.asset,
                assetTypeEnum: this.assetTypeEnum,
                contentItems: this.contentItems,
                customFields: cleanedCustomFields,
                collect_info_mode: this.collectInfoMode || 'optional',
                eventDetails: this.eventDetails,
                subscriptionDetails: this.subscriptionDetails,
                newsletterDetails: { ...this.newsletterDetails, welcomeFile: null },
                pricing: this.pricing,
                position_preference: this.positionPreference || 'bottom'
            };

            const hidden = document.createElement('input');
            hidden.type = 'hidden';
            hidden.name = 'asset_data';
            hidden.value = JSON.stringify(allData);
            this.$refs.assetForm.appendChild(hidden);
            this.$refs.assetForm.submit();
        },

        // Asset Type Details — descriptions, examples, and guide tips
        assetTypeDetails: {
            'video-series': {
                title: 'Video Course',
                description: 'A structured series of video lessons your audience can purchase and watch at their own pace. Ideal for teaching skills, sharing knowledge, or building a curriculum.',
                contentDescription: 'Add your course videos — upload files or paste links from YouTube, Vimeo, etc.',
                examples: ['Online cooking class', 'Photography masterclass', 'Fitness workout series'],
                guide: ['Give each lesson a clear, numbered title (e.g. "Lesson 1: Getting Started")', 'Add a short description so students know what each video covers', 'You can mix uploaded videos and external links']
            },
            'ticket': {
                title: 'Event & Webinar',
                description: 'Sell access to a live or virtual event. Attendees register and purchase a ticket, then receive instructions on how to join.',
                contentDescription: 'Configure your event — set the date, time, location/link, and any custom registration questions.',
                examples: ['Zoom workshop', 'In-person seminar', 'Live Q&A session'],
                guide: ['Set a clear date & time so attendees can plan ahead', 'Add a Zoom/Meet link or physical address', 'Use custom questions to collect info like T-shirt size or dietary needs']
            },
            'digital-file': {
                title: 'Digital Product',
                description: 'Sell downloadable files — e-books, templates, presets, design assets, music, or any digital file your audience can download after purchase.',
                contentDescription: 'Upload your files. You can add multiple files, each with optional release and expiration dates.',
                examples: ['E-book (PDF)', 'Lightroom presets pack', 'Canva templates bundle'],
                guide: ['Bundle related files into a single zip for a cleaner experience', 'Use descriptive file names so buyers know what they\'re getting', 'Test your downloads before publishing']
            },
            'subscription': {
                title: 'Subscription',
                description: 'Offer recurring paid access to exclusive content, community, or services. Subscribers are billed on a regular cycle and retain access as long as they\'re subscribed.',
                contentDescription: 'Describe what subscribers will receive — welcome content and ongoing benefits.',
                examples: ['Monthly exclusive articles', 'Private community membership', 'Weekly coaching calls'],
                guide: ['Clearly list what subscribers get so they understand the value', 'Create pricing tiers (e.g. Monthly, Quarterly, Annual) with different prices', 'Write a warm welcome message for new subscribers']
            },
            'newsletter': {
                title: 'Newsletter',
                description: 'Build a paid newsletter — subscribers pay for regular, exclusive written content delivered on a schedule you define.',
                contentDescription: 'Set up your welcome content and choose how often you\'ll send new editions.',
                examples: ['Weekly industry insights', 'Monthly market analysis', 'Bi-weekly creative writing'],
                guide: ['Include a high-value welcome PDF or message so new subscribers feel it\'s worth it', 'Pick a frequency you can consistently maintain', 'Set clear expectations about what each edition will cover']
            }
        },

        getAssetTypeDetails() { return this.assetTypeDetails[this.assetType] || { title: 'Asset', contentDescription: '', description: '', examples: [], guide: [] }; },
        mapEnumTypeToFormType(enumType) { const map = { 'VIDEO_SERIES': 'video-series', 'TICKET': 'ticket', 'DIGITAL_PRODUCT': 'digital-file', 'SUBSCRIPTION': 'subscription', 'NEWSLETTER': 'newsletter' }; return map[enumType]; },
        mapFormTypeToEnumType(formType) { const map = { 'video-series': 'VIDEO_SERIES', 'ticket': 'TICKET', 'digital-file': 'DIGITAL_PRODUCT', 'subscription': 'SUBSCRIPTION', 'newsletter': 'NEWSLETTER' }; return map[formType]; },
    }));

    Alpine.data('settingsPage', (initialSettings) => ({
        // --- State ---
        settings: initialSettings || {}, // Guard against null/undefined data
        mainTab: 'storeProfile',
        integrationTab: 'notifications',
        storeLogo: null, // Initialize as null, set in init()

        // Form states
        telegramEnabled: false,
        whatsappEnabled: false,
        smtpEnabled: false,
        aiEnabled: false,

        // Testing states
        telegramTesting: false,
        telegramTested: false,
        telegramTestSuccess: false,
        emailTesting: false,
        emailTested: false,
        emailTestSuccess: false,
        testEmailAddress: '',
        testSMSNumber: '',
        smsEnabled: false,
        smsTesting: false,
        smsTested: false,
        smsTestSuccess: false,
        smsTestMessage: '',
        metaPixelEnabled: false,
        gaEnabled: false,

        init() {
            // Populate state from the initial settings object
            this.storeLogo = this.settings.store_logo_url || '';
            this.telegramEnabled = this.settings.telegram_enabled || false;
            this.whatsappEnabled = this.settings.whatsapp_enabled || false;
            this.smtpEnabled = this.settings.email_smtp_enabled || false;
            this.smsEnabled = this.settings.sms_enabled || false;
            this.aiEnabled = this.settings.ai_enabled || false;
            this.metaPixelEnabled = this.settings.marketing_meta_pixel_enabled || false;
            this.gaEnabled = this.settings.marketing_ga_enabled || false;

            // Restore the last-open tabs so a refresh returns to the same view.
            const validMainTabs = ['storeProfile', 'appearance', 'integrations'];
            const validIntegrationTabs = ['notifications', 'payments', 'marketing'];
            const savedMainTab = localStorage.getItem('adminSettingsMainTab');
            const savedIntegrationTab = localStorage.getItem('adminSettingsIntegrationTab');
            if (validMainTabs.includes(savedMainTab)) this.mainTab = savedMainTab;
            if (validIntegrationTabs.includes(savedIntegrationTab)) this.integrationTab = savedIntegrationTab;
            this.$watch('mainTab', val => localStorage.setItem('adminSettingsMainTab', val));
            this.$watch('integrationTab', val => localStorage.setItem('adminSettingsIntegrationTab', val));

            // This is just for the local theme picker, separate from saved settings
            const theme = localStorage.getItem('theme') || 'system';
            this.$dispatch('set-theme', theme);
        },

        setTheme(newTheme) {
            // This method updates the LIVE theme, not the saved setting
            this.$dispatch('set-theme', newTheme);
        },

        previewStoreLogo(event) {
            const file = event.target.files[0];
            if (file) {
                this.storeLogo = URL.createObjectURL(file);
            }
        },

        // Test methods (placeholders)
        testTelegram() {
            this.telegramTesting = true;
            setTimeout(() => {
                this.telegramTesting = false;
                this.telegramTested = true;
                this.telegramTestSuccess = Math.random() > 0.3;
            }, 2000);
        },
        testEmail() {
            if (!this.testEmailAddress.trim()) {
                alert('Please enter an email address to send a test to.');
                return;
            }
            this.emailTesting = true;
            setTimeout(() => {
                this.emailTesting = false;
                this.emailTested = true;
                this.emailTestSuccess = Math.random() > 0.2;
            }, 2500);
        },
        testWhatsApp() { alert('Testing WhatsApp...'); },
        testWhatsApp() { alert('Testing WhatsApp...'); },
        testSMS() {
            if (!this.testSMSNumber || !this.testSMSNumber.trim()) {
                alert('Please enter a phone number to send a test SMS to.');
                return;
            }
            this.smsTesting = true;
            this.smsTested = false;

            const formData = new FormData();
            formData.append('phone', this.testSMSNumber);

            fetch('/admin/settings/sms/test', {
                method: 'POST',
                body: formData
            })
                .then(response => response.json())
                .then(data => {
                    this.smsTesting = false;
                    this.smsTested = true;
                    this.smsTestSuccess = data.success;
                    this.smsTestMessage = data.message;
                })
                .catch(error => {
                    this.smsTesting = false;
                    this.smsTested = true;
                    this.smsTestSuccess = false;
                    this.smsTestMessage = 'Network error occurred.';
                    console.error('Error:', error);
                });
        },
        testAI() { alert('Testing AI...'); },
        testInstagram() { alert('Testing Instagram...'); },
        connectInstagram() { alert('Connecting to Instagram...'); },
        connectGoogle() { alert('Connecting to Google...'); },
    }));

    Alpine.data('assetView', (initialAsset, allStatuses) => ({
        // Original data from the server. Guard against null.
        // Original data from the server. Guard against null.
        asset: initialAsset || {},
        // A mutable copy for the form. Initialize immediately to prevent template errors.
        editableAsset: JSON.parse(JSON.stringify(initialAsset || {})),

        statuses: allStatuses || [],
        activeTab: 'general',
        isSaving: false,
        notification: { show: false, message: '', type: 'success' },
        previewImage: null,

        init() {
            // Initialize preview image
            this.previewImage = this.asset.cover_image_url;

            // Restore the last-open tab so a refresh returns to the same view.
            // Fall back to General if the saved tab isn't valid for this asset type.
            const validTabs = ['general', 'configuration', 'content', 'questionnaire', 'responses', 'activity'];
            let savedTab = localStorage.getItem('adminAssetViewTab');
            if (savedTab && validTabs.includes(savedTab)) {
                const configurableTypes = ['TICKET', 'SUBSCRIPTION', 'NEWSLETTER'];
                if (savedTab === 'configuration' && !configurableTypes.includes(this.asset.asset_type)) {
                    savedTab = 'general';
                }
                this.activeTab = savedTab;
            }
            this.$watch('activeTab', val => localStorage.setItem('adminAssetViewTab', val));

            // Safely add the nested properties if they don't exist.
            if (!this.editableAsset.eventDetails) {
                this.editableAsset.eventDetails = {
                    link: this.asset.eventDetails?.link || '',
                    date: this.asset.eventDetails?.date || '',
                    time: this.asset.eventDetails?.time || '',
                    maxAttendees: this.asset.eventDetails?.maxAttendees || null,
                    postPurchaseInstructions: this.asset.details?.postPurchaseInstructions || ''
                };
            } else {
                // Ensure postPurchaseInstructions is populated if eventDetails exists but field is missing
                this.editableAsset.eventDetails.postPurchaseInstructions = this.asset.details?.postPurchaseInstructions || '';
            }

            if (!this.editableAsset.details) {
                this.editableAsset.details = { welcomeContent: '', benefits: '', subscription_tiers: [], labels: { en: '', sw: '' } };
            }
            if (!this.editableAsset.details.labels) {
                this.editableAsset.details.labels = this.asset.details?.labels || { en: '', sw: '' };
            }

            // Initialize UZA Product ID
            if (!this.editableAsset.uza_product_id) {
                this.editableAsset.uza_product_id = this.asset.details?.uza_product_id || '';
            }

            // Initialize pricing tiers
            if (!this.editableAsset.details.subscription_tiers) {
                this.editableAsset.details.subscription_tiers = this.asset.details?.subscription_tiers || [];
            }

            // Initialize subscription content fields
            if (!this.editableAsset.details.welcomeContent) {
                this.editableAsset.details.welcomeContent = this.asset.details?.welcomeContent || '';
            }
            if (!this.editableAsset.details.benefits) {
                this.editableAsset.details.benefits = this.asset.details?.benefits || '';
            }

            // Initialize allow_download (default to true if not set)
            if (this.editableAsset.allow_download === undefined || this.editableAsset.allow_download === null) {
                this.editableAsset.allow_download = this.asset.allow_download !== false;
            }

            // Initialize custom fields (available for all asset types)
            if (!this.editableAsset.customFields) {
                this.editableAsset.customFields = this.asset.custom_fields || [];
            }
            // Ensure each field has an editable raw-options string for the dropdown builder
            this.editableAsset.customFields.forEach(f => {
                if (f._optionsRaw === undefined) {
                    f._optionsRaw = Array.isArray(f.options) ? f.options.join(', ') : '';
                }
                if (f.required === undefined) f.required = false;
                if (f.accept === undefined) f.accept = '';
                if (f.maxSizeMb === undefined) f.maxSizeMb = 5;
            });

            // Initialize questionnaire enforcement mode: 'optional' | 'reminder' | 'gate'
            if (!this.editableAsset.collect_info_mode) {
                this.editableAsset.collect_info_mode = this.asset.details?.collect_info_mode || 'optional';
            }

            // Initialize content items date/expiry from description
            if (this.editableAsset.files) {
                this.editableAsset.files.forEach((f, i) => {
                    f.newFile = null; // Initialize for UI binding
                    f._uid = f.id ? ('db-' + f.id) : ('uid-' + Date.now() + '-' + i);
                    // Parse [Date:YYYY-MM-DD] from description
                    const dateMatch = f.description ? f.description.match(/\[Date:(\d{4}-\d{2}-\d{2})\]\s*/) : null;
                    if (dateMatch) {
                        f.date = dateMatch[1];
                        f.description = f.description.replace(dateMatch[0], '');
                    }
                    // Parse [Expiry:YYYY-MM-DD] from description
                    const expiryMatch = f.description ? f.description.match(/\[Expiry:(\d{4}-\d{2}-\d{2})\]\s*/) : null;
                    if (expiryMatch) {
                        f.expiry = expiryMatch[1];
                        f.description = f.description.replace(expiryMatch[0], '');
                    }
                    if (!f.expiry) f.expiry = '';
                    if (!f.date) f.date = '';
                    // Initialize type if missing
                    if (!f.type) {
                        f.type = f.link && !f.link.startsWith('/content/') ? 'link' : 'upload';
                    }
                });
            }

            this.applyUtilityClasses();
        },


        handleCoverSelect(event) {
            const file = event.target.files[0];
            if (file) {
                this.previewImage = URL.createObjectURL(file);
                this.editableAsset.newCoverImage = file;
            }
        },

        get publicUrl() {
            // Guard against a null asset object here as well.
            return `${window.location.origin}/${this.editableAsset.slug || this.asset.slug || ''}`;
        },

        addContentItem(position = 'bottom') {
            if (!this.editableAsset.files) this.editableAsset.files = [];
            const blank = { _uid: 'new-' + Date.now() + '-' + Math.random(), title: '', link: '', description: '', newFile: null, type: 'upload', date: '', expiry: '' };
            if (position === 'top') {
                this.editableAsset.files.unshift(blank);
            } else {
                this.editableAsset.files.push(blank);
            }
            // Bring the newly added card into view on the next render tick.
            this.$nextTick(() => {
                const list = this.$refs.contentList;
                if (!list) return;
                const target = position === 'top' ? list.firstElementChild : list.lastElementChild;
                if (target && target.scrollIntoView) target.scrollIntoView({ behavior: 'smooth', block: 'center' });
            });
        },

        removeContentItem(index) {
            this.editableAsset.files.splice(index, 1);
        },

        // Initialize SortableJS for drag-and-drop reordering
        initSortable() {
            if (typeof Sortable === 'undefined') {
                console.warn('SortableJS not loaded, drag-and-drop disabled');
                return;
            }

            this.$nextTick(() => {
                const el = this.$refs.contentList;
                if (!el) return;

                new Sortable(el, {
                    animation: 150,
                    handle: '.drag-handle',
                    ghostClass: 'opacity-50',
                    chosenClass: 'ring-indigo-500',
                    dragClass: 'shadow-lg',
                    onEnd: (evt) => {
                        const oldIndex = evt.oldIndex;
                        const newIndex = evt.newIndex;
                        if (oldIndex !== newIndex && this.editableAsset.files) {
                            // Move item in array
                            const item = this.editableAsset.files.splice(oldIndex, 1)[0];
                            this.editableAsset.files.splice(newIndex, 0, item);
                        }
                    }
                });
            });
        },

        moveItemUp(index) {
            if (index <= 0 || !this.editableAsset.files) return;
            const files = this.editableAsset.files;
            [files[index - 1], files[index]] = [files[index], files[index - 1]];
        },

        moveItemDown(index) {
            if (!this.editableAsset.files || index >= this.editableAsset.files.length - 1) return;
            const files = this.editableAsset.files;
            [files[index], files[index + 1]] = [files[index + 1], files[index]];
        },

        addPricingTier() {
            this.editableAsset.details.subscription_tiers.push({ name: '', price: null, interval: 'monthly', description: '' });
        },

        removePricingTier(index) {
            this.editableAsset.details.subscription_tiers.splice(index, 1);
        },

        addCustomField() {
            if (!this.editableAsset.customFields) this.editableAsset.customFields = [];
            this.editableAsset.customFields.push({ type: 'text', question: '', required: false, options: [], _optionsRaw: '', accept: '', maxSizeMb: 5 });
        },

        removeCustomField(index) {
            this.editableAsset.customFields.splice(index, 1);
        },

        handleFileSelect(event, index) {
            const file = event.target.files[0];
            if (file) {
                // Ensure the object is reactive
                this.editableAsset.files[index].newFile = file;
                // Force Alpine to notice the change if needed (usually automatic)
            }
        },

        async saveChanges() {
            this.isSaving = true;
            this.hideNotification();

            if (!this.editableAsset || !this.asset.id) {
                this.showNotification('Error: Asset data is missing. Cannot save.', 'error');
                this.isSaving = false;
                return;
            }

            const formData = new FormData();

            // Construct the asset_data JSON structure expected by save_asset_from_form
            const contentItems = (this.editableAsset.files || []).map(f => {
                let desc = f.description || '';
                if (f.expiry) {
                    desc = `[Expiry:${f.expiry}] ${desc}`;
                }
                if (f.date) {
                    desc = `[Date:${f.date}] ${desc}`;
                }
                return {
                    title: f.title,
                    link: f.link,
                    description: desc,
                    type: f.type || 'upload'
                };
            });

            // Clean custom fields: derive dropdown options from the raw string and
            // drop the editor-only _optionsRaw helper before persisting.
            const cleanedCustomFields = (this.editableAsset.customFields || []).map(f => {
                const out = {
                    type: f.type || 'text',
                    question: f.question || '',
                    required: !!f.required
                };
                if (f.type === 'select') {
                    out.options = (f._optionsRaw || (Array.isArray(f.options) ? f.options.join(', ') : ''))
                        .split(',').map(s => s.trim()).filter(Boolean);
                }
                if (f.type === 'file') {
                    out.accept = f.accept || '';
                    out.maxSizeMb = f.maxSizeMb || 5;
                }
                return out;
            }).filter(f => f.question.trim());

            const assetData = {
                action: this.editableAsset.status === 'Draft' ? 'draft' : 'publish',
                asset: {
                    id: this.asset.id,
                    title: this.editableAsset.title,
                    description: this.editableAsset.description,
                    story_snippet: this.editableAsset.story,
                    uza_product_id: this.editableAsset.uza_product_id || '',
                    slug: this.editableAsset.slug || ''
                },
                allow_download: this.editableAsset.allow_download,
                assetTypeEnum: this.asset.asset_type,
                contentItems: contentItems,
                customFields: cleanedCustomFields,
                collect_info_mode: this.editableAsset.collect_info_mode || 'optional',
                eventDetails: this.editableAsset.eventDetails || {},
                subscriptionDetails: {
                    welcomeContent: this.editableAsset.details?.welcomeContent || '',
                    benefits: this.editableAsset.details?.benefits || '',
                    subscription_tiers: this.editableAsset.details?.subscription_tiers || []
                },
                newsletterDetails: {
                    welcomeContent: this.editableAsset.details?.welcomeContent || '',
                    benefits: this.editableAsset.details?.benefits || ''
                },
                labels: this.editableAsset.details?.labels || {},
                pricing: {
                    amount: this.editableAsset.price,
                    type: this.editableAsset.is_subscription ? 'recurring' : 'one-time',
                    billingCycle: (this.editableAsset.subscription_interval || 'monthly').toLowerCase(),
                    tiers: this.editableAsset.details?.subscription_tiers || []
                }
            };


            formData.append('asset_data', JSON.stringify(assetData));

            // Append Cover Image if changed
            if (this.editableAsset.newCoverImage) {
                formData.append('cover_image', this.editableAsset.newCoverImage);
            }

            // Append files
            (this.editableAsset.files || []).forEach((f, index) => {
                if (f.newFile) {
                    formData.append(`content_file_${index}`, f.newFile);
                }
            });

            try {
                // Use the robust save_asset endpoint
                const response = await fetch('/admin/assets/save', {
                    method: 'POST',
                    headers: { 'Accept': 'application/json' },
                    body: formData
                });

                const result = await response.json();

                if (response.ok && result.success) {
                    this.showNotification(result.message, 'success');
                    // Reload to reflect changes (especially file links)
                    setTimeout(() => window.location.reload(), 1000);
                } else {
                    this.showNotification(result.message || 'An unknown error occurred.', 'error');
                }
            } catch (e) {
                console.error(e);
                this.showNotification('A server connection error occurred.', 'error');
            } finally {
                this.isSaving = false;
            }
        },

        showNotification(message, type = 'success') {
            this.notification.message = message;
            this.notification.type = type;
            this.notification.show = true;
            setTimeout(() => this.hideNotification(), 4000);
        },

        hideNotification() {
            this.notification.show = false;
        },



        applyUtilityClasses() {
            const map = {
                '.input-label': 'block text-sm font-semibold text-gray-700 dark:text-gray-200 mb-1.5',
                '.input-field': 'w-full px-4 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-shadow shadow-sm placeholder-gray-400 dark:placeholder-gray-500',
            };
            document.querySelectorAll(Object.keys(map).join(',')).forEach(el => {
                for (const selector in map) {
                    if (el.matches(selector)) {
                        el.className = map[selector];
                    }
                }
            });
        }
    }));

    Alpine.data('checkout', (asset, currencySymbol, paymentUrl) => ({
        isOpen: false,
        asset: asset,
        currency: currencySymbol,
        paymentUrl: paymentUrl,
        renewalTierName: null,
        autoOpenRenew: false,
        phoneNumber: localStorage.getItem('nyota_phone') || '',
        status: 'ready',
        errorMessage: '',
        statusMessage: '',
        channelId: null,
        eventSource: null,
        selectedTier: null,
        tiers: [],
        purchaseId: null,
        dealId: null,
        pollingInterval: null,
        pollCount: 0,
        maxPolls: 120, // 10 minutes at 5s interval
        modalTimeout: null, // Timeout for modal auto-refresh
        _trackPurchaseOnce: false, // Prevent duplicate purchase events from SSE+polling

        get isFree() {
            // Check if this is a free asset (no tier selected or tier price is 0)
            if (this.selectedTier && this.selectedTier.price) {
                return parseFloat(this.selectedTier.price) === 0;
            }
            return parseFloat(this.asset.price || 0) === 0;
        },

        init() {
            // Renewal context — set by the server when a lapsed subscriber lands here.
            try {
                const rd = document.getElementById('renewal-data');
                if (rd && rd.textContent.trim()) {
                    const parsed = JSON.parse(rd.textContent);
                    if (parsed) {
                        this.renewalTierName = parsed.tier_name || null;
                        this.autoOpenRenew = !!parsed.auto_open;
                    }
                }
            } catch (e) { /* no renewal context */ }

            this.$watch('isOpen', value => {
                if (!value) {
                    this.clearModalTimeout();
                }
            });
            window.addEventListener('open-checkout-modal', (event) => {
                const prefillNumber = event.detail ? event.detail.phoneNumber : localStorage.getItem('nyota_phone');
                this.openModal(prefillNumber);
            });

            // Listen for cancellation event
            window.addEventListener('stop-payment-verification', () => {
                console.log('Stopping payment verification due to cancellation');
                this.stopPolling();
                if (this.eventSource) {
                    this.eventSource.close();
                    this.eventSource = null;
                }
                this.status = 'none';
                this.isOpen = false;
            });

            // Check for pending purchase immediately on init (handles page refresh)
            // This avoids race conditions with external events
            const pendingKey = `nyota_purchase_${this.asset.id}`;
            const pendingData = localStorage.getItem(pendingKey);

            if (pendingData) {
                try {
                    const pending = JSON.parse(pendingData);
                    if (pending.status && pending.status.name === 'PENDING' && pending.id) {
                        console.log('[Resumption] Found pending purchase in storage:', pending);
                        // Small delay to ensure Alpine is fully ready
                        setTimeout(() => {
                            this.resumePaymentCheck(pending.id, pending.deal_id, pending.channel_id);
                        }, 500);
                    }
                } catch (e) {
                    console.error('[Resumption] Error parsing pending purchase:', e);
                }
            }

            // --- VISIBILITY API HOOK ---
            // Fixes mobile dropped SSE connections by checking status instantly when browser returns to foreground
            document.addEventListener('visibilitychange', () => {
                if (document.visibilityState === 'visible' && this.status === 'waiting' && this.purchaseId) {
                    console.log('👀 [VISIBILITY] User returned to tab. Instantly verifying payment status...');
                    this.checkPaymentStatus();
                }
            });

            // Arrived here via "Renew Subscription" (?renew=1) — open checkout straight away.
            if (this.autoOpenRenew && !pendingData) {
                this.$nextTick(() => this.openModal());
            }
        },

        openModal(prefillNumber = null, autoRetry = false) {
            this.isOpen = true; this.status = 'ready';
            this.errorMessage = ''; this.statusMessage = '';
            this.phoneNumber = prefillNumber || localStorage.getItem('nyota_phone') || '';
            this.channelId = crypto.randomUUID();
            this._trackPurchaseOnce = false;

            // Analytics: begin_checkout
            try {
                var price = parseFloat(this.asset.price || 0);
                if (typeof window.nyotaTrack === 'function') {
                    window.nyotaTrack('begin_checkout',
                        { currency: currencySymbol, value: price, items: [{ item_id: String(this.asset.id), item_name: this.asset.title, item_category: this.asset.asset_type, price: price, quantity: 1 }] },
                        { event: 'InitiateCheckout', params: { content_ids: [String(this.asset.id)], content_type: 'product', value: price, currency: currencySymbol, num_items: 1 } }
                    );
                }
            } catch (e) { }

            // Initialize tiers if available
            this.tiers = this.asset.details?.subscription_tiers || [];
            // On renewal, pre-select the plan the customer was previously on (by name);
            // otherwise default to the first tier.
            const priorTier = this.renewalTierName
                ? this.tiers.find(t => t.name === this.renewalTierName)
                : null;
            this.selectedTier = priorTier || (this.tiers.length > 0 ? this.tiers[0] : null);

            this.$nextTick(() => { if (this.$refs.phoneInput) this.$refs.phoneInput.focus(); });

            if (autoRetry) {
                // If retrying, specific logic to avoid double-initiation or just immediate start
                this.retryPayment();
            }
        },

        startTimeoutTimer() {
            // DEPRECATED: We no longer arbitrarily reload the page after 15 seconds.
            // This interrupted users who were still entering their mobile money PIN.
            // Reliability is now handled by robust parallel polling and the visibility API.
            this.clearModalTimeout();
        },

        clearModalTimeout() {
            if (this.modalTimeout) {
                clearTimeout(this.modalTimeout);
                this.modalTimeout = null;
            }
        },

        dispatchStatus(status, data = {}) {
            window.dispatchEvent(new CustomEvent('payment-status-change', {
                detail: { status: status, ...data }
            }));
        },

        // Analytics: fire purchase event exactly once (SSE+polling may both detect success)
        _firePurchaseEvent() {
            if (this._trackPurchaseOnce) return;
            this._trackPurchaseOnce = true;
            try {
                var price = this.selectedTier ? parseFloat(this.selectedTier.price || 0) : parseFloat(this.asset.price || 0);
                if (typeof window.nyotaTrack === 'function') {
                    window.nyotaTrack('purchase',
                        { transaction_id: String(this.purchaseId || ''), currency: currencySymbol, value: price, items: [{ item_id: String(this.asset.id), item_name: this.asset.title, item_category: this.asset.asset_type, price: price, quantity: 1 }] },
                        { event: 'Purchase', params: { content_ids: [String(this.asset.id)], content_type: 'product', content_name: this.asset.title, value: price, currency: currencySymbol } }
                    );
                }
            } catch (e) { }
        },

        closeModal() {
            this.isOpen = false;
            // CRITICAL: Do NOT stop polling or close SSE when modal closes
            // Payment verification must continue in the background
            // Only stop when payment actually succeeds or user explicitly cancels
            console.log('Modal closed, but payment verification continues in background');
        },

        formatPhoneNumber() {
            let cleaned = this.phoneNumber.replace(/\D/g, '');
            if (cleaned.startsWith('255')) cleaned = '0' + cleaned.substring(3);
            else if (cleaned.startsWith('0') && cleaned.length > 10) cleaned = cleaned.substring(0, 10);

            if (cleaned.length > 4) cleaned = cleaned.substring(0, 4) + ' ' + cleaned.substring(4);
            if (cleaned.length > 8) cleaned = cleaned.substring(0, 8) + ' ' + cleaned.substring(8);

            this.phoneNumber = cleaned;
        },

        async initiatePayment() {
            if (this.phoneNumber.replace(/\D/g, '').length < 10) {
                this.errorMessage = 'Please enter a valid phone number.';
                return;
            }
            this.status = 'initiating';
            this.errorMessage = '';
            localStorage.setItem('nyota_phone', this.phoneNumber);

            try {
                const response = await fetch(this.paymentUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        phone_number: this.phoneNumber.replace(/\D/g, ''),
                        asset_id: this.asset.id,
                        channel_id: this.channelId,
                        tier: this.selectedTier,
                        language: navigator.language || 'en'
                    })
                });

                const result = await response.json();

                if (response.ok && result.success) {
                    // --- FREE ASSET: instant success, no payment verification ---
                    if (result.is_free) {
                        this.status = 'success';
                        this.statusMessage = result.message || 'Access granted!';
                        this.dispatchStatus('COMPLETED');
                        localStorage.setItem('nyota_phone', this.phoneNumber);

                        // Analytics: generate_lead (free asset acquisition)
                        try {
                            if (typeof window.nyotaTrack === 'function') {
                                window.nyotaTrack('generate_lead',
                                    { currency: currencySymbol, value: 0, items: [{ item_id: String(this.asset.id), item_name: this.asset.title, item_category: this.asset.asset_type, price: 0, quantity: 1 }] },
                                    { event: 'Lead', params: { content_ids: [String(this.asset.id)], content_type: 'product', content_name: this.asset.title, value: 0, currency: currencySymbol } }
                                );
                            }
                        } catch (e) { }

                        setTimeout(() => {
                            window.location.href = result.redirect_url || '/library';
                        }, 800);
                        return;
                    }

                    // Analytics: add_payment_info (phone submitted successfully)
                    try {
                        var payPrice = this.selectedTier ? parseFloat(this.selectedTier.price || 0) : parseFloat(this.asset.price || 0);
                        if (typeof window.nyotaTrack === 'function') {
                            window.nyotaTrack('add_payment_info',
                                { currency: currencySymbol, value: payPrice, payment_type: 'mobile_money', items: [{ item_id: String(this.asset.id), item_name: this.asset.title, item_category: this.asset.asset_type, price: payPrice, quantity: 1 }] },
                                { event: 'AddPaymentInfo', params: { content_ids: [String(this.asset.id)], content_type: 'product', value: payPrice, currency: currencySymbol } }
                            );
                        }
                    } catch (e) { }

                    // --- PAID ASSET: wait for payment verification ---
                    this.status = 'waiting';
                    this.statusMessage = result.message || 'Check your phone...';
                    this.purchaseId = result.purchase_id;
                    this.dealId = result.deal_id;

                    const pendingPurchase = {
                        id: result.purchase_id,
                        deal_id: result.deal_id,
                        channel_id: this.channelId, // Store channel ID for reconnection
                        status: { name: 'PENDING' }
                    };
                    localStorage.setItem(`nyota_purchase_${this.asset.id}`, JSON.stringify(pendingPurchase));

                    this.dispatchStatus('PENDING', { phoneNumber: this.phoneNumber });

                    // Belt and suspenders: Listen via SSE, but also poll in parallel
                    this.listenForPaymentResult();
                    this.startPolling();
                    this.startTimeoutTimer(); // (Now deprecated/empty)
                } else {
                    this.status = 'failed';
                    this.errorMessage = result.message || 'Could not start payment.';
                }
            } catch (err) {
                this.status = 'failed';
                this.errorMessage = 'A network error occurred.';
            }
        },

        async retryPayment() {
            if (!this.dealId || !this.purchaseId) {
                // Fallback to full initiation if we lost state
                return this.initiatePayment();
            }

            this.status = 'initiating';
            this.errorMessage = '';
            this.stopPolling(); // Stop any existing polling
            this.pollCount = 0; // Reset counter

            try {
                const response = await fetch('/api/retry-payment', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        deal_id: this.dealId,
                        purchase_id: this.purchaseId,
                        phone_number: this.phoneNumber.replace(/\D/g, '')
                    })
                });

                const result = await response.json();

                if (response.ok && result.success) {
                    this.status = 'waiting';
                    this.statusMessage = result.message || 'New request sent. Check your phone.';
                    this.dispatchStatus('PENDING', { phoneNumber: this.phoneNumber });
                    this.startTimeoutTimer(); // (Now deprecated/empty)

                    // Re-initiate robust checking
                    this.startPolling();

                    // Ensure listener is active (it might have been closed)
                    if (!this.eventSource || this.eventSource.readyState === EventSource.CLOSED) {
                        this.listenForPaymentResult();
                    }
                } else {
                    this.status = 'timeout'; // Go back to timeout state so they can try again
                    this.errorMessage = result.message || 'Retry failed.';
                }
            } catch (e) {
                this.status = 'timeout';
                this.errorMessage = 'Network error during retry.';
            }
        },

        async checkPaymentStatus() {
            if (!this.purchaseId) {
                console.warn('No purchase ID available for status check');
                return;
            }

            console.log(`[POLLING] Checking payment status for purchase #${this.purchaseId}... (${this.pollCount}/${this.maxPolls})`);

            this.pollCount++;
            if (this.pollCount > this.maxPolls) {
                console.warn('[POLLING] Max polling attempts reached. Stopping.');
                this.stopPolling();
                this.status = 'timeout';
                this.errorMessage = 'Payment verification timed out. Please check your phone or retry.';
                if (this.eventSource) this.eventSource.close();
                return;
            }

            try {
                const response = await fetch(`/api/payment-status/${this.purchaseId}`);
                const data = await response.json();

                if (response.ok && data.success) {
                    console.log(`[POLLING] Status received: ${data.status}`);

                    if (data.status === 'COMPLETED') {
                        console.log('[POLLING] ✅ PAYMENT CONFIRMED! Redirecting...');
                        this.status = 'success';
                        this.statusMessage = 'Payment confirmed!';
                        this.clearModalTimeout(); // Clear timeout on success
                        this.stopPolling();
                        if (this.eventSource) this.eventSource.close();

                        // Clear localStorage
                        localStorage.removeItem(`nyota_purchase_${this.asset.id}`);

                        // Analytics: purchase (via polling)
                        this._firePurchaseEvent();

                        // Redirect regardless of modal state
                        setTimeout(() => {
                            window.location.href = data.redirect_url || '/library';
                        }, 1500);
                    } else if (data.status === 'FAILED') {
                        console.log('[POLLING] ❌ Payment failed');
                        this.status = 'failed';
                        this.errorMessage = data.message || 'Payment failed.';
                        this.stopPolling();
                        if (this.eventSource) this.eventSource.close();

                        // Reopen modal to show error
                        if (!this.isOpen) {
                            this.isOpen = true;
                        }
                    }
                    // If PENDING, continue polling (no action needed)
                } else {
                    console.error('[POLLING] Status check failed:', data.message);
                }
            } catch (e) {
                console.error('[POLLING] Error checking payment status:', e);
            }
        },

        startPolling() {
            console.log('🔄 [POLLING] Starting robust background payment verification (every 5 seconds)');
            this.stopPolling(); // Clear any existing interval
            this.pollCount = 0; // Reset counter on fresh start

            // Check immediately, then every 5 seconds
            this.checkPaymentStatus();
            this.pollingInterval = setInterval(() => this.checkPaymentStatus(), 5000);
        },

        stopPolling() {
            if (this.pollingInterval) {
                console.log('⏸️ [POLLING] Stopping payment verification');
                clearInterval(this.pollingInterval);
                this.pollingInterval = null;
            }
        },

        resumePaymentCheck(purchaseId, dealId, channelId) {
            console.log('Resuming payment check after refresh:', { purchaseId, dealId, channelId });

            // Restore state
            this.purchaseId = purchaseId;
            this.dealId = dealId;
            this.phoneNumber = localStorage.getItem('nyota_phone') || '';
            this.status = 'waiting';
            this.statusMessage = 'Checking payment status...';
            // this.isOpen = true; // User requested NOT to open modal automatically on refresh

            // Background verification continues below...

            if (channelId) {
                // If we have a channel ID, try to reconnect SSE first
                console.log('Found existing channel ID, reconnecting SSE...');
                this.channelId = channelId;
                this.listenForPaymentResult();
            } else {
                // Fallback to polling if no channel ID (legacy support)
                console.log('No channel ID found, falling back to polling...');
                this.checkPaymentStatus();
                this.startPolling();
            }
        },

        listenForPaymentResult() {
            if (this.eventSource) this.eventSource.close();

            // CRITICAL: Always check current status via API when connecting/reconnecting
            // This handles cases where we missed the SSE event during network downtime or refresh
            this.checkPaymentStatus();

            const streamUrl = `/api/payment-stream/${this.channelId}`;
            console.log(`[SSE] Connecting to ${streamUrl}...`);
            this.eventSource = new EventSource(streamUrl);

            this.eventSource.onopen = () => {
                console.log('[SSE] Connection established.');
            };

            this.eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);
                console.log('[SSE] Message received:', data);

                if (data.status === 'SUCCESS') {
                    this.status = 'success';
                    this.statusMessage = data.message || 'Payment successful!';
                    this.dispatchStatus('COMPLETED');
                    this.stopPolling();
                    this.eventSource.close();

                    // Clear localStorage
                    localStorage.removeItem(`nyota_purchase_${this.asset.id}`);

                    // Analytics: purchase (via SSE)
                    this._firePurchaseEvent();

                    setTimeout(() => { window.location.href = data.redirect_url || '/library'; }, 1500);
                } else if (data.status === 'FAILED') {
                    this.status = 'failed';
                    this.errorMessage = data.message || 'Payment failed. Please try again.';
                    this.dispatchStatus('FAILED');
                    this.stopPolling();
                    this.eventSource.close();
                }
                // Note: We no longer send TIMEOUT events. The connection stays open indefinitely.
            };

            this.eventSource.onerror = (error) => {
                // Browser will auto-reconnect on error, but we log it.
                // If it's a fatal error (readyState === 2), we might need to intervene.
                console.warn('[SSE] Connection error/interruption:', this.eventSource.readyState);

                // If closed, try to reconnect after a delay if we're still waiting
                if (this.eventSource.readyState === EventSource.CLOSED && this.status === 'waiting') {
                    console.log('[SSE] Connection closed, attempting reconnect in 3s...');
                    setTimeout(() => this.listenForPaymentResult(), 3000);
                }
            };
        }
    }));

    // checkoutForm — standalone full-page checkout component (used by /checkout/<slug>)
    // Mirrors the modal `checkout` component but uses `state` instead of `status`
    // and derives paymentUrl from the parent element's data-payment-url attribute.
    Alpine.data('checkoutForm', (asset, channelId) => ({
        asset: asset,
        channelId: channelId,
        phoneNumber: localStorage.getItem('nyota_phone') || '',
        state: 'ready',
        errorMessage: '',
        statusMessage: '',
        purchaseId: null,
        dealId: null,
        pollingInterval: null,
        pollCount: 0,
        maxPolls: 120,
        eventSource: null,
        selectedTier: null,
        _trackPurchaseOnce: false,

        get paymentUrl() {
            return this.$el.dataset.paymentUrl || '/api/initiate-payment';
        },

        get totalPrice() {
            if (this.selectedTier && this.selectedTier.price !== undefined) {
                return parseFloat(this.selectedTier.price) || 0;
            }
            return parseFloat(this.asset.price || 0);
        },

        init() {
            this.selectedTier = (this.asset.details?.subscription_tiers || [])[0] || null;

            // Resume a pending payment if one was stored (e.g. page refresh)
            const pendingData = localStorage.getItem(`nyota_purchase_${this.asset.id}`);
            if (pendingData) {
                try {
                    const pending = JSON.parse(pendingData);
                    if (pending.status?.name === 'PENDING' && pending.id) {
                        setTimeout(() => this.resumePaymentCheck(pending.id, pending.deal_id, pending.channel_id), 500);
                    }
                } catch (e) { }
            }

            document.addEventListener('visibilitychange', () => {
                if (document.visibilityState === 'visible' && this.state === 'waiting' && this.purchaseId) {
                    this.checkPaymentStatus();
                }
            });
        },

        async submitPayment() {
            if (this.phoneNumber.replace(/\D/g, '').length < 10) {
                this.errorMessage = 'Please enter a valid phone number.';
                return;
            }
            this.state = 'waiting';
            this.statusMessage = 'Initiating payment...';
            this.errorMessage = '';
            localStorage.setItem('nyota_phone', this.phoneNumber);

            try {
                const response = await fetch(this.paymentUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        phone_number: this.phoneNumber.replace(/\D/g, ''),
                        asset_id: this.asset.id,
                        channel_id: this.channelId,
                        tier: this.selectedTier,
                        language: navigator.language || 'en'
                    })
                });
                const result = await response.json();

                // --- Already owns this item ---
                if (result.already_owned) {
                    if (result.sms_sent) {
                        this.state = 'already_owned';
                        this.statusMessage = result.message;
                    } else {
                        // SMS throttled or not configured — show inline error + library link
                        this.state = 'ready';
                        this.errorMessage = result.message;
                    }
                    return;
                }

                if (response.ok && result.success) {
                    if (result.is_free) {
                        this.state = 'success';
                        this.statusMessage = result.message || 'Access granted!';
                        setTimeout(() => { window.location.href = result.redirect_url || '/library'; }, 800);
                        return;
                    }
                    this.state = 'waiting';
                    this.statusMessage = result.message || 'Check your phone to complete payment.';
                    this.purchaseId = result.purchase_id;
                    this.dealId = result.deal_id;
                    localStorage.setItem(`nyota_purchase_${this.asset.id}`, JSON.stringify({
                        id: result.purchase_id,
                        deal_id: result.deal_id,
                        channel_id: this.channelId,
                        status: { name: 'PENDING' }
                    }));
                    this.listenForPaymentResult();
                    this.startPolling();
                } else {
                    this.state = 'ready';
                    this.errorMessage = result.message || 'Could not start payment.';
                }
            } catch (err) {
                this.state = 'ready';
                this.errorMessage = 'A network error occurred. Please try again.';
            }
        },

        async resumePaymentCheck(purchaseId, dealId, storedChannelId) {
            this.purchaseId = purchaseId;
            this.dealId = dealId;
            if (storedChannelId) this.channelId = storedChannelId;
            this.state = 'waiting';
            this.statusMessage = 'Resuming payment check...';
            this.listenForPaymentResult();
            this.startPolling();
        },

        startPolling() {
            this.stopPolling();
            this.pollCount = 0;
            this.pollingInterval = setInterval(() => this.checkPaymentStatus(), 5000);
        },

        stopPolling() {
            if (this.pollingInterval) {
                clearInterval(this.pollingInterval);
                this.pollingInterval = null;
            }
        },

        async checkPaymentStatus() {
            if (!this.purchaseId) return;
            this.pollCount++;
            if (this.pollCount > this.maxPolls) {
                this.stopPolling();
                this.state = 'ready';
                this.errorMessage = 'Payment timed out. Please try again or contact support.';
                return;
            }
            try {
                const response = await fetch(`/api/payment-status/${this.purchaseId}`);
                if (!response.ok) return;
                const data = await response.json();
                if (data.status === 'COMPLETED') {
                    this._onSuccess(data);
                } else if (data.status === 'FAILED') {
                    this.state = 'ready';
                    this.errorMessage = data.message || 'Payment failed. Please try again.';
                    this.stopPolling();
                }
            } catch (e) { }
        },

        listenForPaymentResult() {
            if (this.eventSource) { this.eventSource.close(); }
            this.eventSource = new EventSource(`/api/payment-stream/${this.channelId}`);
            this.eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (data.status === 'SUCCESS') this._onSuccess(data);
                    else if (data.status === 'FAILED') {
                        this.state = 'ready';
                        this.errorMessage = data.message || 'Payment failed.';
                        this.stopPolling();
                        this.eventSource.close();
                    }
                } catch (e) { }
            };
            this.eventSource.onerror = () => {
                if (this.eventSource?.readyState === EventSource.CLOSED && this.state === 'waiting') {
                    setTimeout(() => this.listenForPaymentResult(), 3000);
                }
            };
        },

        _onSuccess(data) {
            if (this._trackPurchaseOnce) return;
            this._trackPurchaseOnce = true;
            this.state = 'success';
            this.statusMessage = 'Payment confirmed!';
            this.stopPolling();
            if (this.eventSource) { this.eventSource.close(); }
            localStorage.removeItem(`nyota_purchase_${this.asset.id}`);
            setTimeout(() => { window.location.href = data.redirect_url || '/library'; }, 1500);
        }
    }));

    Alpine.data('adminSupporters', () => ({
        // --- Data ---
        supporters: [], // Start with a guaranteed empty array
        filteredSupporters: [],
        viewMode: 'list',
        searchTerm: '',
        typeFilter: 'all',
        sortBy: 'spent',
        sortAsc: false,
        selectedSupporters: [],
        bulkAction: '',

        init() {
            // --- THIS IS THE FIX ---
            // A much more robust way to initialize the data.
            const dataElement = document.getElementById('supporters-data');
            if (dataElement && dataElement.textContent.trim()) {
                try {
                    const parsedData = JSON.parse(dataElement.textContent);
                    // Ensure the parsed data is actually an array before assigning it
                    if (Array.isArray(parsedData)) {
                        this.supporters = parsedData;
                    } else {
                        console.error("Parsed supporters data is not an array:", parsedData);
                        this.supporters = []; // Fallback to empty array
                    }
                } catch (e) {
                    console.error('Error parsing supporters data:', e);
                    this.supporters = []; // Fallback to empty array on parsing error
                }
            } else {
                this.supporters = []; // Fallback if data element is missing or empty
            }

            this.applyFiltersAndSort();

            this.$watch(() => [this.searchTerm, this.typeFilter, this.sortBy], () => {
                this.applyFiltersAndSort();
            });
        },

        // --- Computed Properties & Logic ---
        applyFiltersAndSort() {
            let temp = [...this.supporters]; // This now works because `supporters` is an array

            if (this.searchTerm.trim()) {
                const s = this.searchTerm.toLowerCase();
                temp = temp.filter(supporter =>
                    supporter.name.toLowerCase().includes(s) ||
                    (supporter.email && supporter.email.toLowerCase().includes(s))
                );
            }

            if (this.typeFilter !== 'all') {
                temp = temp.filter(supporter => {
                    if (this.typeFilter === 'customer') return supporter.purchases > 0;
                    if (this.typeFilter === 'affiliate') return supporter.is_affiliate;
                    if (this.typeFilter === 'subscriber') return supporter.is_subscriber;
                    return true;
                });
            }

            temp.sort((a, b) => {
                let valA, valB;
                switch (this.sortBy) {
                    case 'name': valA = a.name.toLowerCase(); valB = b.name.toLowerCase(); break;
                    case 'recent': valA = new Date(a.join_date); valB = new Date(b.join_date); break;
                    case 'purchases': valA = a.purchases || 0; valB = b.purchases || 0; break;
                    default: valA = a.total_spent || 0; valB = b.total_spent || 0; break; // 'spent'
                }
                // Default to descending sort for money/dates
                if (valA < valB) return 1;
                if (valA > valB) return -1;
                return 0;
            });

            this.filteredSupporters = temp;
        },

        // --- Helper Functions for UI ---
        // These will now work correctly
        getTotalRevenue() {
            return this.supporters.reduce((sum, s) => sum + (s.total_spent || 0), 0);
        },
        getAffiliateCount() {
            return this.supporters.filter(s => s.is_affiliate).length;
        },
        getAverageLTV() {
            const customerCount = this.supporters.filter(s => s.purchases > 0).length;
            if (customerCount === 0) return 0;
            return this.getTotalRevenue() / customerCount;
        },
        formatDate(iso) {
            if (!iso) return 'N/A';
            return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
        },

        // --- UI State Helpers ---
        hasActiveFilters() { return this.searchTerm.trim() || this.typeFilter !== 'all'; },
        getActiveFilters() {
            let filters = [];
            if (this.searchTerm.trim()) filters.push({ key: 'searchTerm', label: `Search: "${this.searchTerm}"` });
            if (this.typeFilter !== 'all') filters.push({ key: 'typeFilter', label: `Type: ${this.typeFilter}` });
            return filters;
        },
        removeFilter(key) { this[key] = (key === 'searchTerm') ? '' : 'all'; },
        clearAllFilters() { this.searchTerm = ''; this.typeFilter = 'all'; },

        // --- Actions ---
        applyBulkAction() { alert(`Applying action "${this.bulkAction}" to ${this.selectedSupporters.length} supporters.`); },
        viewSupporter(id) { alert(`Viewing supporter ${id}`); },
        messageSupporter(id) { alert(`Messaging supporter ${id}`); },

        toggleSelectAll(event) {
            this.selectedSupporters = event.target.checked ? this.filteredSupporters.map(s => s.id) : [];
        },
    }));

    Alpine.data('assetPageController', () => ({
        purchase: null,
        phoneNumber: localStorage.getItem('nyota_phone') || '',

        // --- IMPROVED STATE MANAGEMENT ---
        isRetrying: false,
        isCancelling: false,
        feedbackMessage: '',
        isSuccess: false,

        init() {
            try {
                const dataElement = document.getElementById('purchase-data');
                if (dataElement && dataElement.textContent.trim()) {
                    this.purchase = JSON.parse(dataElement.textContent);
                    // Pre-fill phone number from the pending purchase if available
                    if (this.purchase && this.purchase.phone_number) {
                        this.phoneNumber = this.purchase.phone_number;
                    }
                }
            } catch (e) { this.purchase = null; }
        },

        get purchaseId() { return this.purchase ? this.purchase.id : null; },
        get dealId() { return this.purchase ? this.purchase.payment_gateway_ref : null; },
        get purchaseStatus() { return this.purchase ? (this.purchase.status ? this.purchase.status.name : null) : null; },

        // Computed property to disable buttons during any action
        get isProcessing() {
            return this.isRetrying || this.isCancelling;
        },

        handlePurchaseAction() {
            // If it's a failed or pending purchase, we retry.
            if (this.purchaseId && (this.purchaseStatus === 'FAILED' || this.purchaseStatus === 'PENDING')) {
                this.retryPayment();
            } else {
                // Otherwise, it's a new purchase; open the modal.
                this.$dispatch('open-checkout-modal');
            }
        },

        async retryPayment() {
            if (!this.purchaseId || !this.dealId) {
                this.feedbackMessage = 'Order data is missing. Please try a new purchase.';
                this.isSuccess = false;
                return;
            }
            if (this.phoneNumber.length < 9) {
                this.feedbackMessage = 'Please enter a valid phone number.';
                this.isSuccess = false;
                return;
            }

            this.isRetrying = true;
            this.feedbackMessage = '';

            try {
                const response = await fetch('/api/retry-payment', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        phone_number: this.phoneNumber,
                        deal_id: this.dealId,
                        purchase_id: this.purchaseId
                    })
                });
                const result = await response.json();

                this.feedbackMessage = result.message;
                this.isSuccess = response.ok && result.success;

                if (this.isSuccess) {
                    localStorage.setItem('nyota_phone', this.phoneNumber);
                    // Give user time to read the success message
                    setTimeout(() => window.location.reload(), 2000);
                }
            } catch (err) {
                this.feedbackMessage = 'A network error occurred.';
                this.isSuccess = false;
            } finally {
                // Only stop processing if it wasn't a success, otherwise we wait for reload
                if (!this.isSuccess) {
                    setTimeout(() => {
                        this.isRetrying = false;
                        this.feedbackMessage = '';
                    }, 5000);
                }
            }
        },

        // --- NEW: Method to cancel a pending payment ---
        async cancelPayment() {
            if (!this.purchaseId) {
                this.feedbackMessage = 'Cannot cancel: Order ID is missing.';
                this.isSuccess = false;
                return;
            }

            if (!confirm('Are you sure you want to cancel this pending payment?')) {
                return;
            }

            this.isCancelling = true;
            this.feedbackMessage = '';

            try {
                // NOTE: You will need to create this backend endpoint.
                const response = await fetch('/api/cancel-payment', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ purchase_id: this.purchaseId })
                });

                const result = await response.json();
                this.feedbackMessage = result.message;
                this.isSuccess = response.ok && result.success;

                if (this.isSuccess) {
                    // On success, reload the page to show the purchase button again.
                    setTimeout(() => window.location.reload(), 2000);
                }

            } catch (err) {
                this.feedbackMessage = 'A network error occurred while cancelling.';
                this.isSuccess = false;
            } finally {
                if (!this.isSuccess) {
                    setTimeout(() => {
                        this.isCancelling = false;
                        this.feedbackMessage = '';
                    }, 5000);
                }
            }
        }
    }));

    Alpine.data('activityFeed', (hasQuestionnaire = false, assetId = null) => ({
        allItems: [],
        hasQuestionnaire,
        assetId,
        filters: { activityType: 'all', paymentStatus: 'all', questFilled: 'all', dateFrom: '', dateTo: '' },
        pageSize: 25,
        currentPage: 1,
        showFilterPanel: false,

        init() {
            // Restore saved filters from localStorage
            if (assetId) {
                try {
                    const saved = localStorage.getItem(`activityFilters_${assetId}`);
                    if (saved) this.filters = { ...this.filters, ...JSON.parse(saved) };
                } catch {}
            }

            try {
                const el = document.getElementById('activity-feed-data');
                const parsed = el ? JSON.parse(el.textContent || '[]') : [];
                this.allItems = parsed.sort((a, b) => new Date(b.date) - new Date(a.date));
            } catch (e) {
                this.allItems = [];
                console.error('Error parsing activity feed data:', e);
            }

            // Persist filter changes and reset page
            this.$watch('filters', (val) => {
                this.currentPage = 1;
                if (assetId) {
                    try { localStorage.setItem(`activityFilters_${assetId}`, JSON.stringify(val)); } catch {}
                }
            }, { deep: true });
        },

        get hasActiveFilters() {
            return this.filters.activityType !== 'all'
                || this.filters.paymentStatus !== 'all'
                || this.filters.questFilled !== 'all'
                || !!this.filters.dateFrom
                || !!this.filters.dateTo;
        },

        get filteredItems() {
            return this.allItems.filter(item => {
                if (this.filters.activityType !== 'all' && item.activity_type !== this.filters.activityType) return false;
                if (this.filters.dateFrom) {
                    if (new Date(item.date) < new Date(this.filters.dateFrom)) return false;
                }
                if (this.filters.dateTo) {
                    if (new Date(item.date) > new Date(this.filters.dateTo + 'T23:59:59')) return false;
                }
                if (item.activity_type === 'purchase') {
                    if (this.filters.paymentStatus !== 'all' && item.payment_status !== this.filters.paymentStatus) return false;
                    if (this.filters.questFilled === 'filled' && !item.filled) return false;
                    if (this.filters.questFilled === 'pending' && item.filled) return false;
                }
                return true;
            });
        },

        get totalPages() {
            return Math.max(1, Math.ceil(this.filteredItems.length / this.pageSize));
        },

        get pagedItems() {
            const start = (this.currentPage - 1) * this.pageSize;
            return this.filteredItems.slice(start, start + this.pageSize);
        },

        get exportUrl() {
            const base = `/admin/assets/${this.assetId}/responses/export`;
            const p = new URLSearchParams();
            if (this.filters.activityType  !== 'all') p.set('activity_type',  this.filters.activityType);
            if (this.filters.paymentStatus !== 'all') p.set('payment_status', this.filters.paymentStatus);
            if (this.filters.questFilled   !== 'all') p.set('quest_filled',   this.filters.questFilled);
            if (this.filters.dateFrom) p.set('date_from', this.filters.dateFrom);
            if (this.filters.dateTo)   p.set('date_to',   this.filters.dateTo);
            return p.toString() ? `${base}?${p}` : base;
        },

        // Returns chips for each active filter so the bar can render them
        get activeFilterChips() {
            const chips = [];
            const typeLabels = { purchase: 'Purchases', comment: 'Comments' };
            const statusLabels = { COMPLETED: 'Completed', PENDING: 'Pending', FAILED: 'Failed' };
            const questLabels = { filled: 'Form filled', pending: 'Awaiting form' };
            if (this.filters.activityType !== 'all') chips.push({ key: 'activityType',  label: typeLabels[this.filters.activityType]  || this.filters.activityType });
            if (this.filters.paymentStatus !== 'all') chips.push({ key: 'paymentStatus', label: statusLabels[this.filters.paymentStatus] || this.filters.paymentStatus });
            if (this.filters.questFilled   !== 'all') chips.push({ key: 'questFilled',   label: questLabels[this.filters.questFilled]   || this.filters.questFilled });
            if (this.filters.dateFrom) chips.push({ key: 'dateFrom', label: `From ${this.filters.dateFrom}` });
            if (this.filters.dateTo)   chips.push({ key: 'dateTo',   label: `To ${this.filters.dateTo}` });
            return chips;
        },

        clearChip(key) {
            if (key === 'dateFrom' || key === 'dateTo') this.filters[key] = '';
            else this.filters[key] = 'all';
        },

        prevPage() { if (this.currentPage > 1) this.currentPage--; },
        nextPage() { if (this.currentPage < this.totalPages) this.currentPage++; },

        resetFilters() {
            this.filters = { activityType: 'all', paymentStatus: 'all', questFilled: 'all', dateFrom: '', dateTo: '' };
            this.currentPage = 1;
            if (assetId) {
                try { localStorage.removeItem(`activityFilters_${assetId}`); } catch {}
            }
        },

        formatDate(iso) {
            try {
                return new Date(iso).toLocaleString(undefined, {
                    month: 'short', day: 'numeric', year: 'numeric',
                    hour: '2-digit', minute: '2-digit'
                });
            } catch { return iso; }
        }
    }));

    // Supporter detail page: one customer's purchases + questionnaire answers
    // across all of the creator's products. Mirrors activityFeed but filters by
    // product instead of activity type, and exports per-supporter.
    Alpine.data('supporterActivity', (supporterId = null) => ({
        allItems: [],
        products: [],
        supporterId,
        filters: { productId: 'all', paymentStatus: 'all', questFilled: 'all', dateFrom: '', dateTo: '' },
        pageSize: 25,
        currentPage: 1,
        showFilterPanel: false,

        init() {
            if (supporterId) {
                try {
                    const saved = localStorage.getItem(`supporterFilters_${supporterId}`);
                    if (saved) this.filters = { ...this.filters, ...JSON.parse(saved) };
                } catch {}
            }

            try {
                const el = document.getElementById('supporter-activity-data');
                const parsed = el ? JSON.parse(el.textContent || '[]') : [];
                this.allItems = parsed.sort((a, b) => new Date(b.date) - new Date(a.date));
            } catch (e) {
                this.allItems = [];
                console.error('Error parsing supporter activity data:', e);
            }

            try {
                const pel = document.getElementById('supporter-products-data');
                this.products = pel ? JSON.parse(pel.textContent || '[]') : [];
            } catch { this.products = []; }

            this.$watch('filters', (val) => {
                this.currentPage = 1;
                if (supporterId) {
                    try { localStorage.setItem(`supporterFilters_${supporterId}`, JSON.stringify(val)); } catch {}
                }
            }, { deep: true });
        },

        get hasActiveFilters() {
            return this.filters.productId !== 'all'
                || this.filters.paymentStatus !== 'all'
                || this.filters.questFilled !== 'all'
                || !!this.filters.dateFrom
                || !!this.filters.dateTo;
        },

        get filteredItems() {
            return this.allItems.filter(item => {
                if (this.filters.productId !== 'all' && String(item.asset_id) !== String(this.filters.productId)) return false;
                if (this.filters.paymentStatus !== 'all' && item.payment_status !== this.filters.paymentStatus) return false;
                if (this.filters.questFilled === 'filled' && !item.filled) return false;
                if (this.filters.questFilled === 'pending' && item.filled) return false;
                if (this.filters.dateFrom && new Date(item.date) < new Date(this.filters.dateFrom)) return false;
                if (this.filters.dateTo && new Date(item.date) > new Date(this.filters.dateTo + 'T23:59:59')) return false;
                return true;
            });
        },

        get totalPages() {
            return Math.max(1, Math.ceil(this.filteredItems.length / this.pageSize));
        },

        get pagedItems() {
            const start = (this.currentPage - 1) * this.pageSize;
            return this.filteredItems.slice(start, start + this.pageSize);
        },

        get exportUrl() {
            const base = `/admin/supporters/${this.supporterId}/responses/export`;
            const p = new URLSearchParams();
            if (this.filters.productId     !== 'all') p.set('asset_id',       this.filters.productId);
            if (this.filters.paymentStatus !== 'all') p.set('payment_status', this.filters.paymentStatus);
            if (this.filters.questFilled   !== 'all') p.set('quest_filled',   this.filters.questFilled);
            if (this.filters.dateFrom) p.set('date_from', this.filters.dateFrom);
            if (this.filters.dateTo)   p.set('date_to',   this.filters.dateTo);
            return p.toString() ? `${base}?${p}` : base;
        },

        get activeFilterChips() {
            const chips = [];
            const statusLabels = { COMPLETED: 'Completed', PENDING: 'Pending', FAILED: 'Failed' };
            const questLabels = { filled: 'Form filled', pending: 'Awaiting form' };
            if (this.filters.productId !== 'all') {
                const prod = this.products.find(p => String(p.id) === String(this.filters.productId));
                chips.push({ key: 'productId', label: prod ? prod.title : 'Product' });
            }
            if (this.filters.paymentStatus !== 'all') chips.push({ key: 'paymentStatus', label: statusLabels[this.filters.paymentStatus] || this.filters.paymentStatus });
            if (this.filters.questFilled   !== 'all') chips.push({ key: 'questFilled',   label: questLabels[this.filters.questFilled]   || this.filters.questFilled });
            if (this.filters.dateFrom) chips.push({ key: 'dateFrom', label: `From ${this.filters.dateFrom}` });
            if (this.filters.dateTo)   chips.push({ key: 'dateTo',   label: `To ${this.filters.dateTo}` });
            return chips;
        },

        clearChip(key) {
            if (key === 'dateFrom' || key === 'dateTo') this.filters[key] = '';
            else this.filters[key] = 'all';
        },

        prevPage() { if (this.currentPage > 1) this.currentPage--; },
        nextPage() { if (this.currentPage < this.totalPages) this.currentPage++; },

        resetFilters() {
            this.filters = { productId: 'all', paymentStatus: 'all', questFilled: 'all', dateFrom: '', dateTo: '' };
            this.currentPage = 1;
            if (supporterId) {
                try { localStorage.removeItem(`supporterFilters_${supporterId}`); } catch {}
            }
        },

        statusBadgeClass(status) {
            if (status === 'COMPLETED') return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300';
            if (status === 'PENDING')   return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300';
            return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300';
        },

        statusLabel(status) {
            return status ? status.charAt(0) + status.slice(1).toLowerCase() : '';
        },

        formatDate(iso) {
            try {
                return new Date(iso).toLocaleString(undefined, {
                    month: 'short', day: 'numeric', year: 'numeric',
                    hour: '2-digit', minute: '2-digit'
                });
            } catch { return iso; }
        }
    }));

});