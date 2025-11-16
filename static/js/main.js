// static/js/main.js

document.addEventListener('alpine:init', () => {

    // ========================================================================
    // == GLOBAL & USER-FACING COMPONENTS
    // ========================================================================

    /**
     * Manages the global light/dark/system theme for the entire application.
     * Listens for system preference changes.
     */
    Alpine.data('themeManager', () => ({
        theme: localStorage.getItem('theme') || 'system',
        init() {
            this.applyTheme();
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
                if (this.theme === 'system') this.applyTheme();
            });
        },
        applyTheme() {
            if (this.theme === 'dark' || (this.theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
                document.documentElement.classList.add('dark');
            } else {
                document.documentElement.classList.remove('dark');
            }
        },
        setTheme(newTheme) {
            this.theme = newTheme;
            localStorage.setItem('theme', newTheme);
            this.applyTheme();
        }
    }));

    /**
     * Powers the main public storefront (user/index.html).
     * Handles filtering of digital assets.
     */
    Alpine.data('storefront', (currencySymbol) => ({
        assets: [],
        activeFilter: 'all',
        currency: currencySymbol,
        init() {
            const dataElement = document.getElementById('storefront-data');
            if (dataElement) this.assets = JSON.parse(dataElement.textContent);
        },
        get filteredAssets() {
            if (this.activeFilter === 'all') return this.assets;
            return this.assets.filter(asset => asset.asset_type === this.activeFilter);
        },
        setFilter(type) { this.activeFilter = type; },
        formatCurrency(amount) { /* ... as provided ... */ }
    }));

    /**
     * Powers the asset detail page (user/asset_detail.html).
     * Handles countdowns for events.
     */
    Alpine.data('assetDetail', (currencySymbol) => ({
        // ... This component is unchanged from your provided version ...
    }));
    
    /**
     * Powers the checkout page (user/checkout.html).
     * Handles the asynchronous payment flow with SSE.
     */
    Alpine.data('checkoutForm', (asset, channelId) => ({
        // ... This component is unchanged from your provided version ...
    }));

    /**
     * Powers the customer's library page (user/library.html).
     */
    Alpine.data('userLibrary', (currencySymbol) => ({
        // ... This component is unchanged from your provided version ...
    }));


    // ========================================================================
    // == ADMIN COMPONENTS
    // ========================================================================

    /**
     * Powers the main assets list page for the creator (admin/assets.html).
     * Handles searching, filtering, sorting, and bulk actions.
     */
    Alpine.data('adminAssets', () => ({
        // ... This component is unchanged from my previous complete response ...
        // It provides all the necessary logic for the assets list view.
    }));

    /**
     * Powers the multi-step asset creation and editing form (admin/asset_form.html).
     */
    Alpine.data('assetForm', () => ({
        // ... This component is unchanged from my previous complete response ...
        // It manages the complex state of the 4-step wizard.
    }));

    /**
     * Powers the creator's settings page (admin/settings.html).
     * Manages all tabs, toggles, and interactive states for store configuration.
     */
    Alpine.data('settingsPage', (initialSettings) => ({
        // --- State Properties ---
        mainTab: 'storeProfile',        // 'storeProfile', 'appearance', 'integrations'
        integrationTab: 'notifications',// 'notifications', 'payments', 'ai', etc.
        storeLogo: initialSettings.store_logo_url || '',

        // --- Simulated API/Connection States ---
        telegramTesting: false,
        telegramTested: false,
        telegramTestSuccess: false,
        whatsappTesting: false,
        emailTesting: false,
        emailTested: false,
        emailTestSuccess: false,
        testEmailAddress: '',

        // This allows us to use Alpine's reactivity with the initial data from Flask
        settings: initialSettings,
        
        init() {
            // The theme needs to be managed globally, so we dispatch an event
            // to the themeManager component if a preference is saved.
            const adminTheme = localStorage.getItem('theme') || 'system';
            this.$dispatch('set-theme', adminTheme);

            // Apply consistent styling to all form elements on the page
            this.applyUtilityClasses();
        },

        // --- UI Methods ---
        setTheme(newTheme) {
            // Update local state and dispatch global event
            this.settings.admin_theme = newTheme;
            this.$dispatch('set-theme', newTheme);
        },

        previewStoreLogo(event) {
            const file = event.target.files[0];
            if (file) {
                this.storeLogo = URL.createObjectURL(file);
            }
        },

        applyUtilityClasses() {
            // A helper to apply TailwindCSS classes programmatically for consistency
            const classMap = {
                '.input-label': 'block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5',
                '.input-field': 'w-full px-4 py-2.5 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700/50 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-colors',
                '.checkbox': 'w-4 h-4 text-indigo-600 bg-gray-100 border-gray-300 rounded focus:ring-indigo-500 dark:focus:ring-indigo-600 dark:ring-offset-gray-800 focus:ring-2 dark:bg-gray-700 dark:border-gray-600',
                '.primary-button': 'px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-lg text-sm transition-colors shadow-sm',
                '.secondary-button': 'px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/50 text-sm font-medium transition-colors',
                '.verify-button': 'px-4 py-2 bg-green-600 hover:bg-green-700 text-white font-medium rounded-lg text-sm transition-colors shadow-sm inline-flex items-center'
            };
            for (const selector in classMap) {
                document.querySelectorAll(selector).forEach(el => el.className = classMap[selector]);
            }
        },

        // --- Simulated Test Methods for Integrations ---
        testTelegram() {
            this.telegramTesting = true;
            this.telegramTested = false;
            // In a real app, this would be a fetch() call to a backend API endpoint
            setTimeout(() => {
                this.telegramTesting = false;
                this.telegramTested = true;
                this.telegramTestSuccess = Math.random() > 0.3; // 70% success rate for demo
            }, 2000);
        },
        
        testWhatsApp() {
            this.whatsappTesting = true;
            // In a real app, this would be a fetch() call to a backend API endpoint
            setTimeout(() => {
                this.whatsappTesting = false;
                // This would be set based on API response
                this.settings.whatsapp_verified = true; 
            }, 1500);
        },

        testEmail() {
            if (!this.testEmailAddress) {
                alert('Please enter an email address to send a test message to.');
                return;
            }
            this.emailTesting = true;
            this.emailTested = false;
            // In a real app, this would be a fetch() call to a backend API endpoint
            setTimeout(() => {
                this.emailTesting = false;
                this.emailTested = true;
                this.emailTestSuccess = Math.random() > 0.2; // 80% success rate for demo
            }, 2500);
        },

        // --- Placeholder methods for other tests ---
        testSMS() { alert('A test SMS would be sent via the configured provider.'); },
        testAI() { alert('A test prompt would be sent to the configured AI provider.'); },
        testInstagram() { alert('A test connection to the Instagram API would be made.'); },
        connectInstagram() { this.settings.social_instagram_connected = true; },
        connectGoogle() { this.settings.productivity_google_connected = true; },
    }));
});