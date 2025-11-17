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
    
    Alpine.data('checkoutForm', (asset, channelId) => ({
        asset: asset, channelId: channelId, quantity: 1, state: 'ready', phoneNumber: '', statusMessage: '', errorMessage: '', eventSource: null, paymentUrl: '', sessionUrl: '',
        get totalPrice() { return this.asset.price * this.quantity; },
        init() { this.paymentUrl = this.$root.dataset.paymentUrl; this.sessionUrl = this.$root.dataset.sessionUrl; this.$watch('quantity', (value) => { if (!Number.isInteger(value) || value < 1) { this.quantity = 1; }}); },
        async submitPayment() { if (!this.phoneNumber.trim()) { this.errorMessage = 'Please enter your phone number.'; return; } this.state = 'waiting'; this.errorMessage = ''; try { const response = await fetch(this.paymentUrl, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ phone_number: this.phoneNumber, asset_id: this.asset.id, channel_id: this.channelId, quantity: this.quantity, total_price: this.totalPrice }) }); const result = await response.json(); if (result.success) { this.statusMessage = result.message; this.listenForPaymentResult(); } else { this.errorMessage = result.message || 'Could not initiate payment.'; this.state = 'ready'; } } catch (error) { this.errorMessage = 'Server connection error. Please try again.'; this.state = 'ready'; } },
        listenForPaymentResult() { this.eventSource = new EventSource(`/api/payment-stream/${this.channelId}`); this.eventSource.onmessage = (event) => { const data = JSON.parse(event.data); if (data.status === 'SUCCESS') { this.statusMessage = data.message; fetch(this.sessionUrl, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ phone_number: this.phoneNumber }) }).then(() => { window.location.href = data.redirect_url; }); } else { this.errorMessage = data.message; this.state = 'ready'; } this.eventSource.close(); }; this.eventSource.onerror = () => { this.errorMessage = 'Connection to server lost. Please refresh and try again.'; this.state = 'ready'; this.eventSource.close(); }; }
    }));

    Alpine.data('userLibrary', (currencySymbol) => ({
        purchasedAssets: [], activeTab: 'all', currency: currencySymbol,
        init() { try { const dataElement = document.getElementById('library-data'); if (dataElement) this.purchasedAssets = JSON.parse(dataElement.textContent); } catch (e) { console.error('Error parsing library data:', e); } },
        get filteredAssets() { if (this.activeTab === 'all') return this.purchasedAssets; return this.purchasedAssets.filter(asset => asset.asset_type === this.activeTab); },
        setTab(tab) { this.activeTab = tab; },
        formatCurrency(amount) { return new Intl.NumberFormat('en-US', { style: 'decimal', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount || 0); }
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
            this.applyFiltersAndSort();
            this.$watch(() => [this.searchTerm, this.statusFilter, this.typeFilter, this.sortBy, this.sortAsc], () => { this.currentPage = 1; this.applyFiltersAndSort(); });
        },

        applyFiltersAndSort() {
            let temp = [...this.assets];
            if (this.searchTerm.trim()) { const s = this.searchTerm.toLowerCase(); temp = temp.filter(a => (a.title && a.title.toLowerCase().includes(s)) || (a.description && a.description.toLowerCase().includes(s))); }
            if (this.statusFilter !== 'all') { temp = temp.filter(a => a.status === this.statusFilter); }
            if (this.typeFilter !== 'all') { temp = temp.filter(a => a.type.toLowerCase().replace(/_/g, '-') === this.typeFilter); }
            temp.sort((a, b) => { let vA, vB; switch (this.sortBy) { case 'title': vA = a.title.toLowerCase(); vB = b.title.toLowerCase(); break; case 'sales': vA = a.sales || 0; vB = b.sales || 0; break; case 'revenue': vA = a.revenue || 0; vB = b.revenue || 0; break; default: vA = new Date(a.updated_at); vB = new Date(b.updated_at); break; } if (vA < vB) return this.sortAsc ? -1 : 1; if (vA > vB) return this.sortAsc ? 1 : -1; return 0; });
            this.filteredAssets = temp;
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
        step: 1, asset: { id: null, title: '', description: '', cover_image_url: null, story_snippet: '' }, assetType: '', assetTypeEnum: '', contentItems: [], customFields: [], eventDetails: { link: '', maxAttendees: null, date: '', time: '' }, subscriptionDetails: { welcomeContent: '', benefits: '' }, newsletterDetails: { welcomeFile: null, welcomeDescription: '', frequency: 'monthly' }, pricing: { type: 'one-time', amount: null, billingCycle: 'monthly' },
        steps: [{number:1,title:'Type',subtitle:'Choose content format'},{number:2,title:'Details',subtitle:'Describe your asset'},{number:3,title:'Content',subtitle:'Add files/links'},{number:4,title:'Pricing',subtitle:'Set your price'}],
        init() {
            const dataElement = document.getElementById('asset-form-data');
            if (dataElement && dataElement.textContent.trim() !== '{}') {
                const existing = JSON.parse(dataElement.textContent);
                this.asset = { id: existing.id, title: existing.title, description: existing.description, cover_image_url: existing.cover_image_url, story_snippet: existing.story };
                this.assetType = this.mapEnumTypeToFormType(existing.asset_type);
                this.assetTypeEnum = existing.asset_type;
                this.contentItems = existing.files || [];
                this.customFields = existing.custom_fields || [];
                this.eventDetails = { link: existing.event_location, maxAttendees: existing.max_attendees, date: existing.event_date, time: existing.event_time };
                this.pricing = { type: existing.is_subscription ? 'recurring' : 'one-time', amount: existing.price, billingCycle: existing.subscription_interval || 'monthly' };
                if (existing.details) {
                    this.subscriptionDetails = existing.details.welcomeContent ? existing.details : this.subscriptionDetails;
                    this.newsletterDetails = existing.details.frequency ? existing.details : this.newsletterDetails;
                }
                this.step = 2;
            }
        },
        setAssetType(type){this.assetType=type;this.assetTypeEnum=this.mapFormTypeToEnumType(type);},
        addContentItem(type){this.contentItems.push({type:type,title:'',link:'',description:''});},
        removeContentItem(index){this.contentItems.splice(index,1);},
        addCustomField(){this.customFields.push({type:'text',question:''});},
        removeCustomField(index){this.customFields.splice(index,1);},
        previewCoverImage(event){const file=event.target.files[0];if(file){this.asset.cover_image_url=URL.createObjectURL(file);}},
        submitForm(action){const allData={action:action,asset:this.asset,assetTypeEnum:this.assetTypeEnum,contentItems:this.contentItems,customFields:this.customFields,eventDetails:this.eventDetails,subscriptionDetails:this.subscriptionDetails,newsletterDetails:{...this.newsletterDetails,welcomeFile:null},pricing:this.pricing};const hidden=document.createElement('input');hidden.type='hidden';hidden.name='asset_data';hidden.value=JSON.stringify(allData);this.$refs.assetForm.appendChild(hidden);this.$refs.assetForm.submit();},
        getAssetTypeDetails(){const details={'video-series':{title:'Video Course',contentDescription:'Add your videos, lessons, or modules below.'},'ticket':{title:'Event & Webinar',contentDescription:'Provide event details and ask for attendee information.'},'digital-file':{title:'Digital Product',contentDescription:'Upload the files your customers will receive.'},'subscription':{title:'Subscription',contentDescription:'Describe the benefits and welcome content for new subscribers.'},'newsletter':{title:'Newsletter',contentDescription:'Set up your welcome content and publishing frequency.'}};return details[this.assetType]||{title:'Asset',contentDescription:''};},
        mapEnumTypeToFormType(enumType){const map={'VIDEO_SERIES':'video-series','TICKET':'ticket','DIGITAL_PRODUCT':'digital-file','SUBSCRIPTION':'subscription','NEWSLETTER':'newsletter'};return map[enumType];},
        mapFormTypeToEnumType(formType){const map={'video-series':'VIDEO_SERIES','ticket':'TICKET','digital-file':'DIGITAL_PRODUCT','subscription':'SUBSCRIPTION','newsletter':'NEWSLETTER'};return map[formType];},
    }));

    Alpine.data('settingsPage', (initialSettings) => ({
        mainTab: 'storeProfile', integrationTab: 'notifications', storeLogo: initialSettings.store_logo_url || '', telegramTesting: false, telegramTested: false, telegramTestSuccess: false, whatsappTesting: false, emailTesting: false, emailTested: false, emailTestSuccess: false, testEmailAddress: '', settings: initialSettings,
        init(){const theme=localStorage.getItem('theme')||'system';this.$dispatch('set-theme',theme);this.applyUtilityClasses();},
        setTheme(newTheme){this.settings.admin_theme=newTheme;this.$dispatch('set-theme',newTheme);},
        previewStoreLogo(event){const file=event.target.files[0];if(file){this.storeLogo=URL.createObjectURL(file);}},
        applyUtilityClasses(){const map={'.input-label':'block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5','.input-field':'w-full px-4 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700/50 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-colors','.checkbox':'w-4 h-4 text-indigo-600 bg-gray-100 border-gray-300 rounded focus:ring-indigo-500 dark:focus:ring-indigo-600 dark:ring-offset-gray-800 focus:ring-2 dark:bg-gray-700 dark:border-gray-600','.primary-button':'px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-lg text-sm transition-colors shadow-sm','.secondary-button':'px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/50 text-sm font-medium transition-colors','.verify-button':'px-4 py-2 bg-green-600 hover:bg-green-700 text-white font-medium rounded-lg text-sm transition-colors shadow-sm inline-flex items-center'};for(const s in map){document.querySelectorAll(s).forEach(el=>el.className=map[s]);}},
        testTelegram(){this.telegramTesting=true;this.telegramTested=false;setTimeout(()=>{this.telegramTesting=false;this.telegramTested=true;this.telegramTestSuccess=Math.random()>.3;},2000);},
        testWhatsApp(){this.whatsappTesting=true;setTimeout(()=>{this.whatsappTesting=false;this.settings.whatsapp_verified=true;},1500);},
        testEmail(){if(!this.testEmailAddress){alert('Please enter an email address.');return;}this.emailTesting=true;this.emailTested=false;setTimeout(()=>{this.emailTesting=false;this.emailTested=true;this.emailTestSuccess=Math.random()>.2;},2500);},
        testSMS(){alert('SMS test would send.');},testAI(){alert('AI test would run.');},testInstagram(){alert('IG test would run.');},
        connectInstagram(){this.settings.social_instagram_connected=true;},connectGoogle(){this.settings.productivity_google_connected=true;},
    }));
});