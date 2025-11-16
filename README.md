# Nyota Digital: The Creator's Digital Storefront Engine

**Nyota Digital** (Swahili for *Star*) is a modern, self-hosted digital distribution engine designed for creators. It empowers photographers, musicians, designers, educators, and any digital producer to sell their work directly to their audience with radical simplicity.

The core philosophy of Nyota is to eliminate friction for both the creator and their customers. It rejects complex account systems in favor of secure, passwordless authentication (TOTP for creators) and instant, access-token-based delivery for buyers via WhatsApp. This project is built on a story that aims to empower modern digital creators with a tool that is both powerful and beautiful.

## Core Features & Philosophy

*   **Self-Hosted & Sovereign:** You own your platform, your data, and your customer relationships. No third-party commissions.
*   **Radically Simple Authentication:**
    *   **Creator (Admin):** Secure, passwordless 2FA using Time-based One-Time Passwords (TOTP).
    *   **Customer (Buyer):** No accounts, no passwords. A unique purchase link sent via WhatsApp grants instant, permanent access to their digital library.
*   **Intuitive Creator Hub:** A clean, multi-step wizard for creating and managing a wide variety of digital assets:
    *   One-time purchases (e-books, photo packs, templates).
    *   Subscriptions (video courses, newsletters).
    *   Event tickets and webinar access.
*   **Asynchronous Payments:** Built to simulate real-world mobile payment flows (like USSD push) using background workers and Server-Sent Events (SSE) for a seamless checkout experience.
*   **Multi-Language Support:** Built from the ground up with internationalization (i18n) for English and Swahili.
*   **Developer-Friendly:**
    *   **Container-First:** Fully containerized with Docker for consistent development and easy deployment.
    *   **Makefile Driven:** Simple `make` commands for common tasks like starting, stopping, and migrating.
    *   **Clean Architecture:** Follows modern Flask best practices with Blueprints, an application factory, and clear separation of concerns.
    *   **Lightweight Frontend:** Uses **Alpine.js** for reactive UI components without the overhead of a heavy framework.

## Tech Stack

*   **Backend:** Python 3.9+, Flask, SQLAlchemy, Gunicorn
*   **Database:** SQLite (default for development), easily swappable to PostgreSQL
*   **Frontend:** HTML5, Tailwind CSS, Alpine.js
*   **Containerization:** Docker, Docker Compose
*   **Asynchronous Tasks:** Python `threading` (for mocking), easily upgradable to Celery/Redis.

## Project Structure

```
.
├── locales/              # Language files (en.json, sw.json)
├── migrations/           # Database migration scripts
├── models/
│   └── nyota.py          # All SQLAlchemy database models
├── static/
│   ├── css/
│   └── js/               # main.js (customer), admin_main.js (creator)
├── templates/
│   ├── admin/            # Templates for the Creator Hub
│   └── user/             # Templates for the public storefront
├── utils/
│   ├── security.py       # Authentication helpers (TOTP, decorators)
│   └── translator.py     # Backend translation utility
├── .env.sample           # Environment variable template
├── config.py             # Flask configuration
├── docker-compose.yml    # Docker service definitions
├── Dockerfile            # Instructions to build the application image
├── main.py               # Flask application factory
├── Makefile              # Developer command shortcuts
├── mock_data.py          # Single source of truth for all mock data
├── requirements.txt      # Python dependencies
├── routes.py             # All Flask routes
└── wsgi.py               # WSGI entry point for Gunicorn
```

## Local Development Setup

### Prerequisites

*   Docker & Docker Compose

### Step-by-Step Instructions

1.  **Clone the Repository**
    ```bash
    git clone <your-repository-url>
    cd nyota-digital
    ```

2.  **Create Environment File**
    Copy the sample file. The default values are sufficient for local development.
    ```bash
    cp .env.sample .env
    ```

3.  **Build and Start the Application**
    This command builds the Docker image and starts the Flask development server in the background.
    ```bash
    make up
    ```

4.  **Run Initial Database Migrations**
    This sequence only needs to be run once for a new project.
    ```bash
    # Step 1: Initialize the migrations folder
    docker-compose exec app flask db init

    # Step 2: Create the first migration script based on models/nyota.py
    docker-compose exec app flask db migrate -m "Initial database schema"

    # Step 3: Apply the migration to the database
    docker-compose exec app flask db upgrade
    ```

5.  **Access the Application**
    *   **Storefront:** [http://localhost:5000](http://localhost:5000)
    *   **Creator Hub:** [http://localhost:5000/admin](http://localhost:5000/admin) (This will redirect to the setup page on the first run).

### Common `make` Commands

*   `make up`: Build and start containers in the background.
*   `make start`: Build and start containers in the foreground (shows live logs).
*   `make stop`: Stop and remove all running containers.
*   `make logs`: View the real-time logs of the running application.
*   `make shell`: Open a shell inside the application container for debugging.

### Database Migration Workflow

After you modify a model in `models/nyota.py`:

1.  **Generate a new migration script:**
    ```bash
    docker-compose exec app flask db migrate -m "A short message describing your changes"
    ```

2.  **Apply the migration to your database:**
    ```bash
    docker-compose exec app flask db upgrade
    ```
    You can also simply run `make up` again, which is configured to automatically apply pending migrations on startup.

## The Story: Key User Journeys

### The Creator's Journey

1.  Visits `/admin` for the first time and is prompted to create a username.
2.  Scans a unique QR code with an authenticator app (e.g., Google Authenticator).
3.  Verifies the setup by entering the first 6-digit code. The creator account is now secure.
4.  Logs in anytime using only their username and the 6-digit code from their app.
5.  Uses the intuitive, multi-step wizard to add new digital assets, defining everything from the price and story to the content files and post-purchase automations.

### The Customer's Journey

1.  Discovers a link to a creator's asset on social media and visits the beautiful, story-driven product page.
2.  Clicks "Purchase" and is taken to a clean checkout page.
3.  Enters their phone number and confirms the payment via a USSD push notification on their phone.
4.  The checkout page automatically updates upon payment confirmation and redirects them to their personal library.
5.  Simultaneously, they receive a WhatsApp message with their receipt and a permanent link to their library.
6.  This link is their key. They can use it anytime to access their purchased content without ever needing a password.