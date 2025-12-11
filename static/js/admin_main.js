document.addEventListener('alpine:init', () => {
    // Component for global theme management
    Alpine.data('themeManager', () => ({
        theme: localStorage.getItem('theme') || 'system',
        isDarkMode: false,
        init() {
            // Apply theme on initial load
            this.applyTheme();
            // Listen for OS-level theme changes
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
                if (this.theme === 'system') this.applyTheme();
            });
        },
        applyTheme() {
            if (this.theme === 'dark') {
                document.documentElement.classList.add('dark');
                this.isDarkMode = true;
            } else if (this.theme === 'light') {
                document.documentElement.classList.remove('dark');
                this.isDarkMode = false;
            } else {
                if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
                    document.documentElement.classList.add('dark');
                    this.isDarkMode = true;
                } else {
                    document.documentElement.classList.remove('dark');
                    this.isDarkMode = false;
                }
            }
        },
        setTheme(newTheme) {
            this.theme = newTheme;
            localStorage.setItem('theme', newTheme);
            this.applyTheme();
        }
    }));

    Alpine.data('adminAssets', () => ({
        // Core State
        assets: [],
        searchTerm: '',
        statusFilter: 'all',
        typeFilter: 'all',
        sortBy: 'title',
        sortOrder: 'asc',
        viewMode: 'list',
        selectedAssets: [],
        bulkAction: '',
        currentPage: 1,
        itemsPerPage: 12,

        // Asset Type Labels
        assetTypeLabels: {
            'video-series': 'Video Course',
            'ticket': 'Event & Webinar',
            'digital-file': 'Digital Product',
            'subscription': 'Subscription',
            'newsletter': 'Newsletter'
        },

        // Status Classes
        statusClasses: {
            'Published': 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300',
            'Draft': 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300',
            'Archived': 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-300'
        },

        // Initialization
        init() {
            try {
                const dataElement = document.getElementById('assets-data');
                if (dataElement) {
                    this.assets = JSON.parse(dataElement.textContent);
                    // Ensure each asset has required fields
                    this.assets = this.assets.map(asset => ({
                        id: asset.id || Math.random().toString(36),
                        title: asset.title || 'Untitled Asset',
                        description: asset.description || '',
                        type: asset.type || 'digital-file',
                        status: asset.status || 'Draft',
                        cover: asset.cover_image_url || asset.cover || '/static/images/placeholder-cover.jpg',
                        sales: asset.sales || 0,
                        revenue: asset.revenue || 0,
                        updated_at: asset.updated_at || new Date().toISOString(),
                        created_at: asset.created_at || new Date().toISOString()
                    }));
                }
            } catch (e) {
                console.error('Error parsing assets data:', e);
                this.assets = [];
            }
        },

        // Computed Properties
        get filteredAssets() {
            let filtered = this.assets;

            // Apply search filter
            if (this.searchTerm) {
                const term = this.searchTerm.toLowerCase();
                filtered = filtered.filter(asset =>
                    asset.title.toLowerCase().includes(term) ||
                    (asset.description && asset.description.toLowerCase().includes(term)) ||
                    asset.type.toLowerCase().includes(term)
                );
            }

            // Apply status filter
            if (this.statusFilter !== 'all') {
                filtered = filtered.filter(asset => asset.status === this.statusFilter);
            }

            // Apply type filter
            if (this.typeFilter !== 'all') {
                filtered = filtered.filter(asset => asset.type === this.typeFilter);
            }

            // Apply sorting
            filtered.sort((a, b) => {
                let aVal, bVal;

                switch (this.sortBy) {
                    case 'sales':
                        aVal = a.sales || 0;
                        bVal = b.sales || 0;
                        break;
                    case 'revenue':
                        aVal = a.revenue || 0;
                        bVal = b.revenue || 0;
                        break;
                    case 'created':
                        aVal = new Date(a.created_at);
                        bVal = new Date(b.created_at);
                        break;
                    case 'title':
                    default:
                        aVal = a.title.toLowerCase();
                        bVal = b.title.toLowerCase();
                }

                if (this.sortOrder === 'desc') {
                    return aVal < bVal ? 1 : aVal > bVal ? -1 : 0;
                }
                return aVal > bVal ? 1 : aVal < bVal ? -1 : 0;
            });

            return filtered;
        },

        // Methods
        getAssetTypeLabel(type) {
            return this.assetTypeLabels[type] || type;
        },

        getStatusClasses(status) {
            return this.statusClasses[status] || 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-300';
        },

        getStatusCount(status) {
            return this.assets.filter(asset => asset.status === status).length;
        },

        getTotalRevenue() {
            return this.assets.reduce((total, asset) => total + (asset.revenue || 0), 0);
        },

        getTotalSales() {
            return this.assets.reduce((total, asset) => total + (asset.sales || 0), 0);
        },

        formatDate(dateString) {
            if (!dateString) return 'N/A';
            const date = new Date(dateString);
            return date.toLocaleDateString('en-US', {
                year: 'numeric',
                month: 'short',
                day: 'numeric'
            });
        },

        // Selection Management
        toggleSelectAll() {
            if (this.selectedAssets.length === this.filteredAssets.length) {
                this.selectedAssets = [];
            } else {
                this.selectedAssets = this.filteredAssets.map(asset => asset.id);
            }
        },

        // Bulk Actions
        applyBulkAction() {
            if (!this.bulkAction || this.selectedAssets.length === 0) return;

            const action = this.bulkAction;
            const count = this.selectedAssets.length;

            if (confirm(`Are you sure you want to ${action} ${count} asset(s)?`)) {
                // Here you would typically make an API call
                console.log(`Applying ${action} to:`, this.selectedAssets);

                // Update local state for demo purposes
                this.assets = this.assets.map(asset => {
                    if (this.selectedAssets.includes(asset.id)) {
                        if (action === 'delete') {
                            return null;
                        } else if (['publish', 'draft', 'archive'].includes(action)) {
                            return { ...asset, status: this.capitalizeFirst(action) };
                        }
                    }
                    return asset;
                }).filter(Boolean);

                this.selectedAssets = [];
                this.bulkAction = '';

                // Show success message (you could integrate a toast notification here)
                alert(`Successfully ${action}ed ${count} asset(s)`);
            }
        },

        capitalizeFirst(string) {
            return string.charAt(0).toUpperCase() + string.slice(1);
        },

        // Asset Actions
        duplicateAsset(assetId) {
            const asset = this.assets.find(a => a.id === assetId);
            if (asset) {
                const newAsset = {
                    ...asset,
                    id: Math.random().toString(36),
                    title: `${asset.title} (Copy)`,
                    status: 'Draft',
                    sales: 0,
                    revenue: 0,
                    created_at: new Date().toISOString(),
                    updated_at: new Date().toISOString()
                };
                this.assets.unshift(newAsset);
                // In a real app, you'd make an API call here
                console.log('Duplicating asset:', newAsset);
            }
        },

        confirmDelete(assetId) {
            const asset = this.assets.find(a => a.id === assetId);
            if (asset && confirm(`Are you sure you want to delete "${asset.title}"? This action cannot be undone.`)) {
                this.assets = this.assets.filter(a => a.id !== assetId);
                // Remove from selected assets if it was selected
                this.selectedAssets = this.selectedAssets.filter(id => id !== assetId);
                // In a real app, you'd make an API call here
                console.log('Deleting asset:', assetId);
            }
        },

        // Filter Management
        hasActiveFilters() {
            return this.searchTerm || this.statusFilter !== 'all' || this.typeFilter !== 'all';
        },

        getActiveFilters() {
            const filters = [];
            if (this.searchTerm) {
                filters.push({ key: 'search', label: `Search: "${this.searchTerm}"` });
            }
            if (this.statusFilter !== 'all') {
                filters.push({ key: 'status', label: `Status: ${this.statusFilter}` });
            }
            if (this.typeFilter !== 'all') {
                filters.push({ key: 'type', label: `Type: ${this.getAssetTypeLabel(this.typeFilter)}` });
            }
            return filters;
        },

        removeFilter(filterKey) {
            switch (filterKey) {
                case 'search':
                    this.searchTerm = '';
                    break;
                case 'status':
                    this.statusFilter = 'all';
                    break;
                case 'type':
                    this.typeFilter = 'all';
                    break;
            }
        },

        clearAllFilters() {
            this.searchTerm = '';
            this.statusFilter = 'all';
            this.typeFilter = 'all';
        },

        // Pagination
        nextPage() {
            if (this.currentPage * this.itemsPerPage < this.filteredAssets.length) {
                this.currentPage++;
            }
        },

        previousPage() {
            if (this.currentPage > 1) {
                this.currentPage--;
            }
        }
    }));

    // Component for the Admin Supporters page
    Alpine.data('adminSupporters', () => ({
        // Core State
        supporters: [],
        searchTerm: '',
        typeFilter: 'all',
        statusFilter: 'all',
        sortBy: 'name',
        sortOrder: 'asc',
        viewMode: 'list',
        selectedSupporters: [],
        bulkAction: '',
        currentPage: 1,
        itemsPerPage: 12,

        // Initialization
        init() {
            try {
                const dataElement = document.getElementById('supporters-data');
                if (dataElement) {
                    this.supporters = JSON.parse(dataElement.textContent);
                    // Ensure each supporter has required fields
                    this.supporters = this.supporters.map(supporter => ({
                        id: supporter.id || Math.random().toString(36),
                        name: supporter.name || 'Anonymous Supporter',
                        email: supporter.email || 'No email',
                        avatar: supporter.avatar || '/static/images/avatar-placeholder.png',
                        join_date: supporter.join_date || new Date().toISOString(),
                        total_spent: supporter.total_spent || 0,
                        purchases: supporter.purchases || 0,
                        is_affiliate: supporter.is_affiliate || false,
                        commission: supporter.commission || 0,
                        is_subscriber: supporter.is_subscriber || false,
                        status: supporter.status || 'active',
                        location: supporter.location || '',
                        notes: supporter.notes || ''
                    }));
                }
            } catch (e) {
                console.error('Error parsing supporters data:', e);
                this.supporters = [];
            }
        },

        // Computed Properties
        get filteredSupporters() {
            let filtered = this.supporters;

            // Apply search filter
            if (this.searchTerm) {
                const term = this.searchTerm.toLowerCase();
                filtered = filtered.filter(supporter =>
                    supporter.name.toLowerCase().includes(term) ||
                    supporter.email.toLowerCase().includes(term) ||
                    (supporter.notes && supporter.notes.toLowerCase().includes(term)) ||
                    (supporter.location && supporter.location.toLowerCase().includes(term))
                );
            }

            // Apply type filter
            if (this.typeFilter !== 'all') {
                filtered = filtered.filter(supporter => {
                    switch (this.typeFilter) {
                        case 'affiliate':
                            return supporter.is_affiliate;
                        case 'customer':
                            return !supporter.is_affiliate && supporter.purchases > 0;
                        case 'subscriber':
                            return supporter.is_subscriber;
                        default:
                            return true;
                    }
                });
            }

            // Apply status filter
            if (this.statusFilter !== 'all') {
                filtered = filtered.filter(supporter => supporter.status === this.statusFilter);
            }

            // Apply sorting
            filtered.sort((a, b) => {
                let aVal, bVal;

                switch (this.sortBy) {
                    case 'recent':
                        aVal = new Date(a.join_date);
                        bVal = new Date(b.join_date);
                        break;
                    case 'spent':
                        aVal = a.total_spent || 0;
                        bVal = b.total_spent || 0;
                        break;
                    case 'purchases':
                        aVal = a.purchases || 0;
                        bVal = b.purchases || 0;
                        break;
                    case 'name':
                    default:
                        aVal = a.name.toLowerCase();
                        bVal = b.name.toLowerCase();
                }

                if (this.sortOrder === 'desc') {
                    return aVal < bVal ? 1 : aVal > bVal ? -1 : 0;
                }
                return aVal > bVal ? 1 : aVal < bVal ? -1 : 0;
            });

            return filtered;
        },

        // Methods
        getTotalRevenue() {
            return this.supporters.reduce((total, supporter) => total + (supporter.total_spent || 0), 0);
        },

        getAffiliateCount() {
            return this.supporters.filter(supporter => supporter.is_affiliate).length;
        },

        getAverageLTV() {
            const activeSupporters = this.supporters.filter(s => s.total_spent > 0);
            if (activeSupporters.length === 0) return 0;
            return this.getTotalRevenue() / activeSupporters.length;
        },

        formatDate(dateString) {
            if (!dateString) return 'N/A';
            const date = new Date(dateString);
            return date.toLocaleDateString('en-US', {
                year: 'numeric',
                month: 'short',
                day: 'numeric'
            });
        },

        // Selection Management
        toggleSelectAll() {
            if (this.selectedSupporters.length === this.filteredSupporters.length) {
                this.selectedSupporters = [];
            } else {
                this.selectedSupporters = this.filteredSupporters.map(supporter => supporter.id);
            }
        },

        // Bulk Actions
        applyBulkAction() {
            if (!this.bulkAction || this.selectedSupporters.length === 0) return;

            const action = this.bulkAction;
            const count = this.selectedSupporters.length;

            if (confirm(`Are you sure you want to ${action} ${count} supporter(s)?`)) {
                // Here you would typically make an API call
                console.log(`Applying ${action} to:`, this.selectedSupporters);

                // Update local state for demo purposes
                if (action === 'affiliate') {
                    this.supporters = this.supporters.map(supporter => {
                        if (this.selectedSupporters.includes(supporter.id)) {
                            return { ...supporter, is_affiliate: true, commission: 10 };
                        }
                        return supporter;
                    });
                }

                this.selectedSupporters = [];
                this.bulkAction = '';

                // Show success message
                alert(`Successfully ${action}ed ${count} supporter(s)`);
            }
        },

        exportSupporters() {
            // Export functionality
            console.log('Exporting supporters data...');
            alert('Export functionality would be implemented here');
        },

        // Supporter Actions
        viewSupporter(supporterId) {
            console.log('Viewing supporter:', supporterId);
            // Navigate to supporter detail page
        },

        editSupporter(supporterId) {
            console.log('Editing supporter:', supporterId);
            // Open edit modal or navigate to edit page
        },

        messageSupporter(supporterId) {
            console.log('Messaging supporter:', supporterId);
            // Open message modal
        },

        // Filter Management
        hasActiveFilters() {
            return this.searchTerm || this.typeFilter !== 'all' || this.statusFilter !== 'all';
        },

        getActiveFilters() {
            const filters = [];
            if (this.searchTerm) {
                filters.push({ key: 'search', label: `Search: "${this.searchTerm}"` });
            }
            if (this.typeFilter !== 'all') {
                filters.push({ key: 'type', label: `Type: ${this.typeFilter}` });
            }
            if (this.statusFilter !== 'all') {
                filters.push({ key: 'status', label: `Status: ${this.statusFilter}` });
            }
            return filters;
        },

        removeFilter(filterKey) {
            switch (filterKey) {
                case 'search':
                    this.searchTerm = '';
                    break;
                case 'type':
                    this.typeFilter = 'all';
                    break;
                case 'status':
                    this.statusFilter = 'all';
                    break;
            }
        },

        clearAllFilters() {
            this.searchTerm = '';
            this.typeFilter = 'all';
            this.statusFilter = 'all';
        },

        // Pagination
        nextPage() {
            if (this.currentPage * this.itemsPerPage < this.filteredSupporters.length) {
                this.currentPage++;
            }
        },

        previousPage() {
            if (this.currentPage > 1) {
                this.currentPage--;
            }
        }
    }));

    Alpine.data('assetDetailAdmin', () => ({
        asset: {},
        init() {
            try {
                const dataElement = document.getElementById('asset-data');
                if (dataElement) {
                    this.asset = JSON.parse(dataElement.textContent);
                }
            } catch (e) { console.error('Error parsing asset data:', e); }
        }
    }));

    Alpine.data('assetForm', () => ({
        step: 1,
        assetType: '',
        asset: {
            title: '',
            description: '',
            cover_image_url: '',
            story_snippet: '',
            price: 0
        },

        // Steps Definition
        steps: [
            { number: 1, title: 'Type', subtitle: 'Choose content type' },
            { number: 2, title: 'Details', subtitle: 'Title & description' },
            { number: 3, title: 'Content', subtitle: 'Add files/links' },
            { number: 4, title: 'Pricing', subtitle: 'Set price & delivery' }
        ],

        // Step-specific Data
        contentItems: [{
            type: 'file',
            title: '',
            description: '',
            file: null,
            link: '',
            releaseDate: '',
            expirationDate: ''
        }],
        customFields: [{
            type: 'text',
            question: ''
        }],
        eventDetails: {
            link: '',
            date: '',
            time: '',
            maxAttendees: ''
        },
        subscriptionDetails: {
            welcomeContent: '',
            benefits: '',
            billingCycle: 'monthly'
        },
        newsletterDetails: {
            welcomeFile: null,
            welcomeDescription: '',
            frequency: 'weekly'
        },
        pricing: {
            type: 'one-time',
            amount: '',
            billingCycle: 'monthly'
        },

        // Asset Type Details
        assetTypeDetails: {
            'video-series': {
                title: 'Video Course',
                description: 'Multi-lesson video content with progress tracking',
                contentDescription: 'Upload videos or add video links',
                guide: ['Use clear titles for each video', 'Add descriptions to help students']
            },
            'ticket': {
                title: 'Event & Webinar',
                description: 'Live events, workshops, or scheduled webinars',
                contentDescription: 'Add event details and attendee questions',
                guide: ['Provide clear joining instructions', 'Set the correct date and time']
            },
            'digital-file': {
                title: 'Digital Product',
                description: 'Templates, presets, e-books, or file packs',
                contentDescription: 'Upload files with release/expiration dates',
                guide: ['Zip multiple files together', 'Test downloads before publishing']
            },
            'subscription': {
                title: 'Subscription',
                description: 'Recurring content with membership access',
                contentDescription: 'Describe what subscribers receive',
                guide: ['Clearly state subscription benefits', 'Set appropriate pricing']
            },
            'newsletter': {
                title: 'Newsletter',
                description: 'Regular updates and exclusive content',
                contentDescription: 'Set up welcome content and frequency',
                guide: ['Provide valuable welcome content', 'Set clear expectations for frequency']
            }
        },

        // Initialization
        init() {
            try {
                const dataElement = document.getElementById('asset-form-data');
                // Check if we are in "Edit" mode (server provided data)
                let isEditMode = false;

                if (dataElement) {
                    const existingData = JSON.parse(dataElement.textContent);
                    // If the server gave us an ID, it's an existing asset
                    if (existingData.id) {
                        this.asset = { ...this.asset, ...existingData };
                        isEditMode = true;
                    }
                    // For new assets, we might still have some defaults or re-rendered invalid form data
                    else if (existingData.type) {
                        this.asset = { ...this.asset, ...existingData };
                    }

                    if (existingData.type) {
                        this.assetType = existingData.type;
                        // Only jump to step 2 if we actually have data (not just a restored empty draft)
                        if (isEditMode) this.step = 2;
                    }
                }

                // Handling Local Storage Verification (Only for NEW assets)
                if (!isEditMode) {
                    const savedDraft = localStorage.getItem('nyota_asset_draft');
                    if (savedDraft) {
                        try {
                            const draft = JSON.parse(savedDraft);
                            // Simple check: is this draft effectively empty? 
                            // Or should we just restore it?
                            // Let's restore it, but maybe imply it? 
                            // for now, just restore it to solve the USER's pain point immediately.
                            this.assetType = draft.assetType || '';
                            this.asset = { ...this.asset, ...draft.asset };
                            this.pricing = draft.pricing || this.pricing;
                            this.contentItems = draft.contentItems || this.contentItems;
                            this.eventDetails = draft.eventDetails || this.eventDetails;
                            this.customFields = draft.customFields || this.customFields;
                            this.subscriptionDetails = draft.subscriptionDetails || this.subscriptionDetails;
                            this.newsletterDetails = draft.newsletterDetails || this.newsletterDetails;
                            this.step = draft.step || 1;

                            console.log('Restored draft from Local Storage');
                        } catch (e) {
                            console.error('Error restoring draft:', e);
                            localStorage.removeItem('nyota_asset_draft');
                        }
                    }
                }

                // Setup Watchers for Auto-Save
                this.$watch('asset', () => this.saveLocally());
                this.$watch('assetType', () => this.saveLocally());
                this.$watch('pricing', () => this.saveLocally());
                this.$watch('contentItems', () => this.saveLocally());
                this.$watch('step', () => this.saveLocally());

            } catch (e) {
                console.error('Error parsing asset form data:', e);
            }
        },

        saveLocally() {
            // Don't save if we are editing an existing asset (optional, but safer to avoid overwriting "new" draft with "edit" data)
            if (this.asset.id) return;

            const payload = {
                assetType: this.assetType,
                asset: this.asset,
                pricing: this.pricing,
                contentItems: this.contentItems,
                step: this.step,
                eventDetails: this.eventDetails,
                customFields: this.customFields,
                subscriptionDetails: this.subscriptionDetails,
                newsletterDetails: this.newsletterDetails
            };
            localStorage.setItem('nyota_asset_draft', JSON.stringify(payload));
        },

        clearDraft() {
            localStorage.removeItem('nyota_asset_draft');
        },

        // Methods
        setAssetType(type) {
            this.assetType = type;
            // Initialize appropriate content based on type
            if (type === 'video-series') {
                this.contentItems = [{ type: 'video', title: '', description: '', link: '' }];
            } else if (type === 'digital-file') {
                this.contentItems = [{ type: 'file', title: '', file: null, releaseDate: '', expirationDate: '' }];
            }
        },

        getAssetTypeDetails() {
            return this.assetTypeDetails[this.assetType] || {
                title: 'Content',
                description: 'Digital content',
                contentDescription: 'Add your content',
                guide: []
            };
        },

        previewCoverImage(event) {
            const file = event.target.files[0];
            if (file) {
                this.asset.cover_image_url = URL.createObjectURL(file);
            }
        },

        refreshPreview() {
            // Force preview update if needed
            console.log('Preview refreshed');
        },

        // Content Management
        addContentItem(type) {
            const newItem = {
                type: type,
                title: '',
                description: '',
                file: null,
                link: ''
            };

            if (type === 'file') {
                newItem.releaseDate = '';
                newItem.expirationDate = '';
            }

            this.contentItems.push(newItem);
        },

        removeContentItem(index) {
            if (this.contentItems.length > 1) {
                this.contentItems.splice(index, 1);
            }
        },

        // Custom Fields Management
        addCustomField() {
            this.customFields.push({ type: 'text', question: '' });
        },

        removeCustomField(index) {
            if (this.customFields.length > 1) {
                this.customFields.splice(index, 1);
            }
        },

        // Validation helpers
        isValidStep(stepNumber) {
            switch (stepNumber) {
                case 2:
                    return this.asset.title && this.asset.description;
                case 3:
                    return this.contentItems.length > 0 &&
                        this.contentItems.every(item => item.title);
                case 4:
                    return this.pricing.amount !== '';
                default:
                    return true;
            }
        },

        submitForm(action) {
            // Backend Enum Mapping
            const typeMapping = {
                'video-series': 'VIDEO_SERIES',
                'ticket': 'TICKET',
                'digital-file': 'DIGITAL_PRODUCT',
                'subscription': 'SUBSCRIPTION',
                'newsletter': 'NEWSLETTER'
            };

            // Prepare the payload
            const payload = {
                action: action,
                asset: this.asset,
                assetTypeEnum: typeMapping[this.assetType],
                pricing: this.pricing,
                contentItems: this.contentItems,
                // Include all potential type-specific data
                eventDetails: this.eventDetails,
                customFields: this.customFields,
                subscriptionDetails: this.subscriptionDetails,
                newsletterDetails: this.newsletterDetails
            };

            // Find or create the hidden input
            let hiddenInput = this.$refs.assetForm.querySelector('input[name="asset_data"]');
            if (!hiddenInput) {
                hiddenInput = document.createElement('input');
                hiddenInput.type = 'hidden';
                hiddenInput.name = 'asset_data';
                this.$refs.assetForm.appendChild(hiddenInput);
            }

            // Set data and submit
            hiddenInput.value = JSON.stringify(payload);

            // Clear the draft, because we are submitting now. 
            // If submission fails (server error), the page will reload and 
            // since we used standard form submit, the browser *might* restore form state, 
            // OR the server re-renders the template with the submitted values.
            // But if we want to be safe against "Back" button, maybe we should clear it ONLY on success?
            // Actually, for better UX, let's NOT clear it here.
            // Instead, we should clear it if the server tells us 'success' on the NEXT page load.
            // BUT, since we can't easily do that cross-page without cookies, 
            // let's clear it here. If the user hits back, they might lose data, BUT they just submitted it.
            // Re-think: If submission fails, the server usually re-renders the page with the data. 
            // So clearing it here is acceptable for a "happy path". 
            // If the user refreshes the page after submission? It's gone. Good.
            this.clearDraft();

            this.$refs.assetForm.submit();
        }
    }));
});