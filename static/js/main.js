document.addEventListener('alpine:init', () => {

    // Component for global theme management
    Alpine.data('themeManager', () => ({
        theme: localStorage.getItem('theme') || 'system',
        isDarkMode: false,
        init() {
            this.applyTheme();
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
            } else { // 'system' theme
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

    Alpine.data('storefront', (currencySymbol) => ({
        assets: [], activeFilter: 'all', currency: currencySymbol,
        init() {
            try {
                const dataElement = document.getElementById('storefront-data');
                if (dataElement) this.assets = JSON.parse(dataElement.textContent);
            } catch (e) { console.error('Error parsing storefront data:', e); }
        },
        get filteredAssets() {
            if (this.activeFilter === 'all') return this.assets;
            return this.assets.filter(asset => asset.asset_type === this.activeFilter);
        },
        setFilter(type) { this.activeFilter = type; },
        formatCurrency(amount) { return new Intl.NumberFormat('en-US', { style: 'decimal', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount || 0); },
        calculateAverageRating(reviews) {
            if (!reviews || reviews.length === 0) return 'N/A';
            const total = reviews.reduce((sum, review) => sum + review.rating, 0);
            return (total / reviews.length).toFixed(1);
        }
    }));

    // Component for the asset_detail.html page
    Alpine.data('assetDetail', (currencySymbol) => ({
        asset: {},
        countdown: 'Loading...',
        currency: currencySymbol,
        visibleReviews: 3, // Start by showing 3 reviews
        init() {
            try {
                const dataElement = document.getElementById('asset-data');
                if (dataElement) this.asset = JSON.parse(dataElement.textContent);
            } catch (e) { console.error('Error parsing asset detail data:', e); }

            if (this.asset.asset_type === 'ticket' && this.asset.event_date) {
                this.countdownInterval = setInterval(() => { this.updateCountdown(); }, 1000);
                this.updateCountdown();
            }
        },
        get averageRating() {
            if (!this.asset.reviews || this.asset.reviews.length === 0) return 'N/A';
            const total = this.asset.reviews.reduce((sum, review) => sum + review.rating, 0);
            return (total / this.asset.reviews.length).toFixed(1);
        },
        showMoreReviews() {
            this.visibleReviews += 5; // Show 5 more reviews on click
        },
        renderMarkdown(text) {
            if (window.marked) return window.marked.parse(text || '');
            return text || '';
        },
        formatCurrency(amount) {
            return new Intl.NumberFormat('en-US', { style: 'decimal', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount || 0);
        },
        updateCountdown() {
            // Countdown logic is unchanged
            const eventDate = new Date(this.asset.event_date).getTime();
            const now = new Date().getTime();
            const distance = eventDate - now;
            if (distance < 0) {
                this.countdown = "EVENT HAS PASSED";
                if (this.countdownInterval) clearInterval(this.countdownInterval);
                return;
            }
            const days = Math.floor(distance / (1000 * 60 * 60 * 24));
            const hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
            const minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
            const seconds = Math.floor((distance % (1000 * 60)) / 1000);
            this.countdown = `${days}d ${hours}h ${minutes}m ${seconds}s`;
        }
    }));

    Alpine.data('checkoutForm', (asset, channelId) => ({
        asset: asset,
        channelId: channelId,
        quantity: 1,
        state: 'ready',
        phoneNumber: '',
        statusMessage: '',
        errorMessage: '',
        eventSource: null,
        paymentUrl: '',
        sessionUrl: '',

        // Computed property to calculate the total price
        get totalPrice() {
            return this.asset.price * this.quantity;
        },

        init() {
            this.paymentUrl = this.$root.dataset.paymentUrl;
            this.sessionUrl = this.$root.dataset.sessionUrl;
            
            // Ensure quantity doesn't go below 1
            this.$watch('quantity', (value) => {
                if (!Number.isInteger(value) || value < 1) {
                    this.quantity = 1;
                }
            });
        },

        async submitPayment() {
            if (!this.phoneNumber.trim()) {
                this.errorMessage = 'Please enter your phone number.';
                return;
            }
            this.state = 'waiting';
            this.errorMessage = '';

            try {
                const response = await fetch(this.paymentUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        phone_number: this.phoneNumber,
                        asset_id: this.asset.id,
                        channel_id: this.channelId,
                        quantity: this.quantity,
                        total_price: this.totalPrice
                    })
                });
                const result = await response.json();
                if (result.success) {
                    this.statusMessage = result.message;
                    this.listenForPaymentResult();
                } else {
                    this.errorMessage = result.message || 'Could not initiate payment.';
                    this.state = 'ready';
                }
            } catch (error) {
                this.errorMessage = 'Server connection error. Please try again.';
                this.state = 'ready';
            }
        },

        listenForPaymentResult() {
            this.eventSource = new EventSource(`/api/payment-stream/${this.channelId}`);
            this.eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.status === 'SUCCESS') {
                    this.statusMessage = data.message;
                    
                    fetch(this.sessionUrl, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ phone_number: this.phoneNumber })
                    }).then(() => {
                        window.location.href = data.redirect_url;
                    });
                } else { // FAILED or TIMEOUT
                    this.errorMessage = data.message;
                    this.state = 'ready';
                }
                this.eventSource.close();
            };
            this.eventSource.onerror = () => {
                this.errorMessage = 'Connection to server lost. Please refresh and try again.';
                this.state = 'ready';
                this.eventSource.close();
            };
        }
    }));

    Alpine.data('userLibrary', (currencySymbol) => ({
        purchasedAssets: [],
        activeTab: 'all',
        currency: currencySymbol,
        init() {
            try {
                const dataElement = document.getElementById('library-data');
                if (dataElement) {
                    this.purchasedAssets = JSON.parse(dataElement.textContent);
                }
            } catch (e) { console.error('Error parsing library data:', e); }
        },
        get filteredAssets() {
            if (this.activeTab === 'all') return this.purchasedAssets;
            return this.purchasedAssets.filter(asset => asset.asset_type === this.activeTab);
        },
        setTab(tab) {
            this.activeTab = tab;
        },
        formatCurrency(amount) {
             return new Intl.NumberFormat('en-US', { style: 'decimal', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount || 0);
        }
    }));
});