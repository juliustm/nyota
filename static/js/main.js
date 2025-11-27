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
        init() { try { const dataElement = document.getElementById('asset-data'); if (dataElement) this.asset = JSON.parse(dataElement.textContent); } catch (e) { console.error('Error parsing asset detail data:', e); } if (this.asset.asset_type === 'TICKET' && this.asset.event_date) { this.countdownInterval = setInterval(() => this.updateCountdown(), 1000); this.updateCountdown(); } },
        updateCountdown() { const eventDate = new Date(this.asset.event_date).getTime(); const now = new Date().getTime(); const distance = eventDate - now; if (distance < 0) { this.countdown = "EVENT HAS PASSED"; if (this.countdownInterval) clearInterval(this.countdownInterval); return; } const d = Math.floor(distance / (1000 * 60 * 60 * 24)); const h = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60)); const m = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60)); const s = Math.floor((distance % (1000 * 60)) / 1000); this.countdown = `${d}d ${h}h ${m}m ${s}s`; },
        get averageRating() { if (!this.asset.reviews || this.asset.reviews.length === 0) return 'N/A'; const total = this.asset.reviews.reduce((sum, review) => sum + review.rating, 0); return (total / this.asset.reviews.length).toFixed(1); },
        showMoreReviews() { this.visibleReviews += 5; },
        renderMarkdown(text) { if (window.marked) return window.marked.parse(text || ''); return text || ''; },
        formatCurrency(amount) { return new Intl.NumberFormat('en-US', { style: 'decimal', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount || 0); }
    }));

    Alpine.data('userLibrary', (currencySymbol) => ({
        purchasedAssets: [], activeTab: 'all', currency: currencySymbol,
        init() { try { const dataElement = document.getElementById('library-data'); if (dataElement) this.purchasedAssets = JSON.parse(dataElement.textContent); } catch (e) { console.error('Error parsing library data:', e); } },
        get filteredAssets() { if (this.activeTab === 'all') return this.purchasedAssets; return this.purchasedAssets.filter(asset => asset.asset_type === this.activeTab); },
        setTab(tab) { this.activeTab = tab; },
        formatCurrency(amount) { return new Intl.NumberFormat('en-US', { style: 'decimal', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount || 0); }
    }));

    Alpine.data('postPurchaseForm', (assetId, purchaseId, customFields) => ({
        formData: {},
        isSubmitting: false,
        submitted: false,
        init() {
            // Initialize formData with empty values for each field
            (customFields || []).forEach(field => {
                this.formData[field.question] = '';
            });
        },
        async submit() {
            this.isSubmitting = true;
            try {
                const response = await fetch(`/api/purchases/${purchaseId}/ticket-data`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ticket_data: this.formData })
                });
                const result = await response.json();
                if (response.ok && result.success) {
                    this.submitted = true;
                    // Optional: Reload page or update UI state
                    setTimeout(() => window.location.reload(), 1500);
                } else {
                    alert(result.message || 'Error submitting form.');
                }
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
                this.step = 2;
            }
        },
        setAssetType(type) { this.assetType = type; this.assetTypeEnum = this.mapFormTypeToEnumType(type); },
        addContentItem(defaultType = 'upload') { this.contentItems.push({ type: defaultType, title: '', link: '', description: '' }); },
        removeContentItem(index) { this.contentItems.splice(index, 1); },
        addCustomField() { this.customFields.push({ type: 'text', question: '', required: false }); },
        removeCustomField(index) { this.customFields.splice(index, 1); },
        addPricingTier() { this.pricing.tiers.push({ name: '', price: null, interval: 'monthly', description: '' }); },
        removePricingTier(index) { this.pricing.tiers.splice(index, 1); },
        previewCoverImage(event) { const file = event.target.files[0]; if (file) { this.asset.cover_image_url = URL.createObjectURL(file); } },
        submitForm(action) {
            // Prepare data for submission
            const allData = {
                action: action,
                asset: this.asset,
                assetTypeEnum: this.assetTypeEnum,
                contentItems: this.contentItems,
                customFields: this.customFields,
                eventDetails: this.eventDetails,
                subscriptionDetails: this.subscriptionDetails,
                newsletterDetails: { ...this.newsletterDetails, welcomeFile: null },
                pricing: this.pricing
            };

            const hidden = document.createElement('input');
            hidden.type = 'hidden';
            hidden.name = 'asset_data';
            hidden.value = JSON.stringify(allData);
            this.$refs.assetForm.appendChild(hidden);
            this.$refs.assetForm.submit();
        },
        getAssetTypeDetails() { const details = { 'video-series': { title: 'Video Course', contentDescription: 'Add your videos, lessons, or modules below.' }, 'ticket': { title: 'Event & Webinar', contentDescription: 'Provide event details and ask for attendee information.' }, 'digital-file': { title: 'Digital Product', contentDescription: 'Upload the files your customers will receive.' }, 'subscription': { title: 'Subscription', contentDescription: 'Describe the benefits and welcome content for new subscribers.' }, 'newsletter': { title: 'Newsletter', contentDescription: 'Set up your welcome content and publishing frequency.' } }; return details[this.assetType] || { title: 'Asset', contentDescription: '' }; },
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

        init() {
            // Populate state from the initial settings object
            this.storeLogo = this.settings.store_logo_url || '';
            this.telegramEnabled = this.settings.telegram_enabled || false;
            this.whatsappEnabled = this.settings.whatsapp_enabled || false;
            this.smtpEnabled = this.settings.email_smtp_enabled || false;
            this.aiEnabled = this.settings.ai_enabled || false;

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
        testSMS() { alert('Testing SMS...'); },
        testAI() { alert('Testing AI...'); },
        testInstagram() { alert('Testing Instagram...'); },
        connectInstagram() { alert('Connecting to Instagram...'); },
        connectGoogle() { alert('Connecting to Google...'); },
    }));

    Alpine.data('assetView', (initialAsset, allStatuses) => ({
        // Original data from the server. Guard against null.
        asset: initialAsset || {},
        // A mutable copy for the form. Initialize as null and build it in init().
        editableAsset: null,

        statuses: allStatuses || [],
        statuses: allStatuses || [],
        activeTab: 'general',
        isSaving: false,
        notification: { show: false, message: '', type: 'success' },
        previewImage: null,

        init() {
            // Use $nextTick to ensure Alpine's reactivity system is ready
            // before we populate the data. This will force the view to update.
            this.$nextTick(() => {
                // 1. Create the editable copy. If asset is null/empty, start with an empty object.
                this.editableAsset = JSON.parse(JSON.stringify(this.asset));

                // Initialize preview image
                this.previewImage = this.asset.cover_image_url;

                // 2. Safely add the nested properties if they don't exist.
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
                    this.editableAsset.details = { welcomeContent: '', benefits: '' };
                }

                // Initialize pricing tiers
                if (!this.editableAsset.details.subscription_tiers) {
                    this.editableAsset.details.subscription_tiers = [];
                }

                // Initialize content items date from description
                if (this.editableAsset.files) {
                    this.editableAsset.files.forEach(f => {
                        const dateMatch = f.description ? f.description.match(/^\[Date:(\d{4}-\d{2}-\d{2})\]\s*/) : null;
                        if (dateMatch) {
                            f.date = dateMatch[1];
                            f.description = f.description.replace(dateMatch[0], '');
                        }
                        // Initialize type if missing
                        if (!f.type) {
                            f.type = f.link && !f.link.startsWith('/content/') ? 'link' : 'upload';
                        }
                    });
                }
            });

            // Other setup can run immediately.
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
            return `${window.location.origin}/asset/${this.asset.slug || ''}`;
        },

        addContentItem() {
            if (!this.editableAsset.files) this.editableAsset.files = [];
            this.editableAsset.files.push({ title: '', link: '', description: '', newFile: null });
        },

        removeContentItem(index) {
            this.editableAsset.files.splice(index, 1);
        },

        addPricingTier() {
            this.editableAsset.details.subscription_tiers.push({ name: '', price: null, interval: 'monthly', description: '' });
        },

        removePricingTier(index) {
            this.editableAsset.details.subscription_tiers.splice(index, 1);
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

            const assetData = {
                action: this.editableAsset.status === 'Draft' ? 'draft' : 'publish',
                asset: {
                    id: this.asset.id,
                    title: this.editableAsset.title,
                    description: this.editableAsset.description,
                    story_snippet: this.editableAsset.story
                },
                assetTypeEnum: this.asset.asset_type,
                contentItems: contentItems,
                customFields: this.editableAsset.customFields || [],
                eventDetails: this.editableAsset.eventDetails || {},
                subscriptionDetails: this.editableAsset.details || {},
                newsletterDetails: this.editableAsset.details || {},
                pricing: {
                    amount: this.editableAsset.price,
                    type: this.editableAsset.is_subscription ? 'recurring' : 'one-time',
                    billingCycle: (this.editableAsset.subscription_interval || 'monthly').toLowerCase(),
                    tiers: this.editableAsset.details?.subscription_tiers || []
                }
            };

            formData.append('asset_data', JSON.stringify(assetData));

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
                '.input-label': 'block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5',
                '.input-field': 'w-full px-4 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700/50 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-colors',
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
        phoneNumber: localStorage.getItem('nyota_phone') || '',
        status: 'ready',
        errorMessage: '',
        statusMessage: '',
        channelId: null,
        eventSource: null,
        selectedTier: null,
        tiers: [],

        init() {
            window.addEventListener('open-checkout-modal', (event) => {
                const prefillNumber = event.detail ? event.detail.phoneNumber : localStorage.getItem('nyota_phone');
                this.openModal(prefillNumber);
            });
        },

        openModal(prefillNumber = null) {
            this.isOpen = true; this.status = 'ready';
            this.errorMessage = ''; this.statusMessage = '';
            this.phoneNumber = prefillNumber || localStorage.getItem('nyota_phone') || '';
            this.channelId = crypto.randomUUID();

            // Initialize tiers if available
            this.tiers = this.asset.details?.subscription_tiers || [];
            this.selectedTier = this.tiers.length > 0 ? this.tiers[0] : null;

            this.$nextTick(() => { if (this.$refs.phoneInput) this.$refs.phoneInput.focus(); });
        },
        closeModal() { this.isOpen = false; if (this.eventSource) this.eventSource.close(); },

        formatPhoneNumber() { /* ... unchanged ... */ },

        async initiatePayment() {
            if (this.phoneNumber.length < 9) {
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
                        phone_number: this.phoneNumber,
                        asset_id: this.asset.id,
                        channel_id: this.channelId,
                        tier: this.selectedTier
                    })
                });

                const result = await response.json();

                if (response.ok && result.success) {
                    this.status = 'waiting';
                    this.statusMessage = result.message || 'Check your phone...';

                    // --- THIS IS THE KEY CHANGE ---
                    // The backend now gives us the IDs we need to store for a potential retry.
                    // We'll store this in localStorage, scoped to the asset ID.
                    const pendingPurchase = {
                        id: result.purchase_id,
                        deal_id: result.deal_id,
                        status: { name: 'PENDING' }
                    };
                    localStorage.setItem(`nyota_purchase_${this.asset.id}`, JSON.stringify(pendingPurchase));

                    this.listenForPaymentResult();
                } else {
                    this.status = 'failed';
                    this.errorMessage = result.message || 'Could not start payment.';
                }
            } catch (err) {
                this.status = 'failed';
                this.errorMessage = 'A network error occurred.';
            }
        },

        listenForPaymentResult() {
            if (this.eventSource) this.eventSource.close();

            const streamUrl = `/api/payment-stream/${this.channelId}`;
            this.eventSource = new EventSource(streamUrl);

            this.eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.status === 'SUCCESS') {
                    this.status = 'success';
                    this.statusMessage = data.message || 'Payment successful!';
                    this.eventSource.close();
                    setTimeout(() => { window.location.href = data.redirect_url || '/library'; }, 1500);
                } else if (data.status === 'FAILED') {
                    this.status = 'failed';
                    this.errorMessage = data.message || 'Payment failed. Please try again.';
                    this.eventSource.close();
                } else if (data.status === 'TIMEOUT') {
                    this.status = 'failed';
                    this.errorMessage = 'Payment timed out. Please try again.';
                    this.eventSource.close();
                }
            };

            this.eventSource.onerror = () => {
                this.status = 'failed';
                this.errorMessage = 'Connection lost. Please try again.';
                this.eventSource.close();
            };
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

});