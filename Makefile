# Makefile for the Nyota Application

.PHONY: setup-fresh-project start stop logs shell migrate upgrade seed

# ==============================================================================
# FOR A BRAND NEW PROJECT (Run this ONLY ONCE)
# This will reset everything, delete local DB files/migrations, and rebuild.
# ==============================================================================
init:
	@echo "--- WARNING: This will PERMANENTLY delete your local database and migration history. ---"
	@read -p "Press Enter to continue or Ctrl+C to cancel."
	
	@echo "--- Tearing down containers and volumes... ---"
	@docker-compose down -v
	
	@echo "--- Deleting old migration history and local database files... ---"
# 	@rm -rf migrations
# 	@rm -rf instance
# 	@rm -f *.db *.sqlite
	
	@echo "--- Building and starting new containers... ---"
	@docker-compose up --build
	
	@echo "--- Waiting for application to initialize... ---"
	@sleep 5
	
	@echo "--- Initializing new database schema... ---"
	@docker-compose exec app flask db init
	@docker-compose exec app flask db migrate -m "Initial complete database schema"
	@docker-compose exec app flask db upgrade
	
	@echo "--- RESET COMPLETE! Your local database is now clean and up-to-date. ---"
	@echo "--- You can now commit the new 'migrations' folder and deploy. ---"

# ==============================================================================
# FOR DAILY DEVELOPMENT
# Use these commands to manage your running application.
# ==============================================================================

# Start the application and apply any new migrations.
start:
	@echo "--- Starting containers... ---"
	@docker-compose up
	@echo "--- Applying pending migrations... ---"
	@docker-compose exec app flask db upgrade
	@echo "--- Application is running at http://localhost:80 ---"

# Stop the application containers.
stop:
	@echo "--- Stopping containers... ---"
	@docker-compose down

# View the application logs in real-time.
logs:
	@echo "--- Tailing application logs (Press Ctrl+C to exit)... ---"
	@docker-compose logs -f app

# Open a shell inside the running application container.
shell:
	@echo "--- Opening shell into the 'app' container... ---"
	@docker-compose exec app /bin/sh

# ==============================================================================
# FOR DATABASE MIGRATIONS
# Use these after you have changed a model in models/nyota.py.
# ==============================================================================

# Generate a new migration script after changing models.
migrate:
	@read -p "Enter a short, descriptive migration message: " msg; \
	echo "--- Generating new migration script: '$$msg' ---"; \
	docker-compose exec app flask db migrate -m "$$msg"

# Manually apply pending migrations.
upgrade:
	@echo "--- Applying pending database migrations... ---"
	@docker-compose exec app flask db upgrade

# Populate the database with sample data.
seed:
	@echo "--- Seeding database with initial data... ---"
	@docker-compose exec app python seed.py