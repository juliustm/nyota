# Nyota ✨ Digital: The Creator's Digital Storefront Engine

**Nyota Digital** (Swahili for *Star*) is a modern, self-hosted digital distribution engine designed for creators. It empowers photographers, musicians, designers, educators, and any digital producer to sell their work directly to their audience with radical simplicity.

The core philosophy of Nyota is to eliminate friction for both the creator and their customers. It features secure, passwordless authentication (TOTP for creators) and instant, verified access for buyers via phone + purchase date. This project is built to empower modern digital creators with a tool that is both powerful and beautiful.

## 🌟 Core Features & Philosophy

### Creator Experience
*   **Self-Hosted & Sovereign:** You own your platform, your data, and your customer relationships. No third-party commissions.
*   **Secure Admin Access:** Passwordless 2FA using Time-based One-Time Passwords (TOTP) for creators.
*   **Intuitive Asset Management:** Multi-step wizard for creating and managing:
    *   One-time purchases (e-books, photo packs, templates)
    *   Subscriptions (video courses, newsletters)
    *   Event tickets and webinar access
*   **Real-time Analytics:** Track sales, revenue, and customer engagement
*   **Multi-Language Support:** Built-in internationalization (i18n) for English and Swahili

### Customer Experience
*   **No Accounts Required:** Buyers access their library using their phone number + purchase date - no passwords to remember
*   **Resilient Payment Verification:**
    *   Real-time updates via Server-Sent Events (SSE)
    *   Database polling fallback for reliability
    *   Works even if browser is closed during payment
*   **90-Day Sessions:** Secure, long-lasting sessions with HTTPONLY and SAMESITE protection
*   **Account Switching:** Easy profile display with ability to switch between purchases
*   **Rate-Limited Access:** Aggressive throttling (3 attempts/15min) prevents unauthorized access

### Security & Reliability
*   **UZA Callback Protection:** Webhook verification with configurable secret keys
*   **Session Security:** HTTPONLY cookies, SAMESITE protection, 90-day lifetime
*   **Rate Limiting:** IP-based throttling prevents brute force attacks
*   **Audit Logging:** All access attempts tracked in `AccessAttempt` table
*   **Payment Resilience:** Dual-track verification (SSE + HTTP polling) ensures no missed payments

## 🛠 Tech Stack

*   **Backend:** Python 3.9+, Flask, SQLAlchemy, Gunicorn
*   **Database:** SQLite (development), PostgreSQL-ready
*   **Frontend:** HTML5, Tailwind CSS, Alpine.js
*   **Containerization:** Docker, Docker Compose
*   **Payment Gateway:** UZA Payments integration
*   **Asynchronous:** Server-Sent Events (SSE) for real-time updates

## 📁 Project Structure

```
.
├── locales/              # Language files (en.json, sw.json)
├── migrations/           # Database migration scripts
├── models/
│   └── nyota.py          # All SQLAlchemy models (including AccessAttempt)
├── static/
│   ├── css/
│   └── js/               # main.js (customer), admin_main.js (creator)
├── templates/
│   ├── admin/            # Templates for Creator Hub
│   └── user/             # Public storefront templates
├── utils/
│   ├── security.py       # Authentication helpers (TOTP, decorators)
│   └── translator.py     # Backend translation utility
├── .env.sample           # Environment variable template
├── config.py             # Flask configuration (session security, paths)
├── docker-compose.yml    # Docker service definitions
├── Dockerfile            # Application container definition
├── main.py               # Flask application factory
├── Makefile              # Developer command shortcuts
├── mock_data.py          # Mock data for development
├── requirements.txt      # Python dependencies
├── routes.py             # All Flask routes
└── wsgi.py               # WSGI entry point for Gunicorn
```

## 🚀 Local Development Setup

### Prerequisites

*   Docker & Docker Compose

### Quick Start

1.  **Clone the Repository**
    ```bash
    git clone <your-repository-url>
    cd nyota-digital
    ```

2.  **Create Environment File**
    ```bash
    cp .env.sample .env
    ```

3.  **Build and Start**
    ```bash
    make up
    ```

4.  **Run Database Migrations**
    ```bash
    docker-compose exec app flask db upgrade
    ```

5.  **Access the Application**
    *   **Storefront:** [http://localhost](http://localhost)
    *   **Creator Hub:** [http://localhost/admin](http://localhost/admin)

### Common Commands

*   `make up` - Build and start containers in background
*   `make start` - Start with live logs
*   `make stop` - Stop and remove containers
*   `make logs` - View application logs
*   `make shell` - Open shell in app container

### Database Migrations

After modifying `models/nyota.py`:

```bash
# Generate migration
docker-compose exec app flask db migrate -m "Description of changes"

# Apply migration
docker-compose exec app flask db upgrade
```

## 🔐 Security Configuration

### UZA Payment Webhook Security

1. Go to **Admin > Settings > Integrations > UZA Payments**
2. Set a strong **Callback Secret**
3. Update your UZA dashboard webhook URL:
   ```
   https://your-domain.com/api/uza-callback?secret=YOUR_SECRET
   ```

### Session Configuration

In production, set these environment variables:
```bash
SECRET_KEY=your-strong-secret-key
SESSION_COOKIE_SECURE=True  # Requires HTTPS
```

## 📚 Key User Journeys

### The Creator's Journey

1. Visit `/admin` and create a username
2. Scan QR code with authenticator app (Google Authenticator, Authy)
3. Verify with 6-digit code
4. Log in anytime using username + authenticator code
5. Create and manage digital assets via intuitive wizard

### The Customer's Journey

1. Discover asset on social media
2. Click "Purchase" and enter phone number
3. Complete payment via USSD push
4. Access library instantly (or anytime later)
5. To access again: Enter phone number + purchase date
6. Switch between accounts easily from profile display

## 🔄 Payment Flow Architecture

### Dual-Track Verification
Ensures payment confirmation even in adverse network conditions:

1. **Primary:** Server-Sent Events (SSE) for instant updates
2. **Fallback:** HTTP polling every 5 seconds to `/api/check-payment-status`
3. **Persistence:** Database-backed status survives server restarts

### Session Recovery
No session? No problem:
- Enter phone number + purchase date
- System verifies against completed purchases
- Rate limiting prevents abuse (3 attempts = 15min lockout)
- All attempts logged for security monitoring

## 🌍 Internationalization

Built-in support for multiple languages:
- `locales/en.json` - English
- `locales/sw.json` - Swahili

Template usage:
```html
{{ translate('key_name') }}
```

Backend usage:
```python
from utils.translator import translate
message = translate('key_name')
```

## 🎨 Frontend Architecture

- **Alpine.js** for reactive components
- **Tailwind CSS** for styling
- **Server-Sent Events** for real-time updates
- **Mobile-first** responsive design

## 📊 Database Models

### Key Tables
- `creator` - Admin accounts
- `creator_setting` - Key-value configuration store
- `digital_asset` - Products/content
- `customer` - Buyers (phone-based)
- `purchase` - Transaction records
- `access_attempt` - Rate limiting & security audit

### New in Latest Version
- `AccessAttempt` model for tracking library access attempts
- Enhanced session security configuration
- Payment status check endpoint

## 🙏 Contributing

This project follows modern Flask best practices:
- Blueprint-based routing
- Application factory pattern
- Database migrations with Alembic
- Environment-based configuration

---

Built with ❤️ for digital creators everywhere