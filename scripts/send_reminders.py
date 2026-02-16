import sys
import os
from datetime import datetime, timedelta
from sqlalchemy import func

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import create_app
from models.nyota import db, Subscription, SubscriptionStatus
from services.sms_service import get_sms_provider

app = create_app()

# Configurable Base URL for links in SMS
BASE_URL = os.environ.get('BASE_URL', 'https://nyota.co.tz')

def send_reminders():
    print("Starting subscription reminder job...")
    with app.app_context():
        now = datetime.utcnow().date()
        
        # Define target dates
        targets = {
            0: now,
            1: now + timedelta(days=1),
            5: now + timedelta(days=5)
        }
        
        # We can optimize this query, but for now iterate active subs
        # Filter for active subscriptions
        active_subs = Subscription.query.filter(
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.next_billing_date != None
        ).all()
        
        print(f"Found {len(active_subs)} active subscriptions.")
        
        count = 0
        for sub in active_subs:
            # Check date match
            if not sub.next_billing_date:
                continue
                
            expiry_date = sub.next_billing_date.date()
            days_left = (expiry_date - now).days
            
            if days_left in [0, 1, 5]:
                print(f"Sending reminder to {sub.customer.whatsapp_number} (Days left: {days_left})")
                
                provider = get_sms_provider(sub.asset.creator)
                if provider:
                    success, resp = provider.send_subscription_reminder(sub, days_left, base_url=BASE_URL)
                    if success:
                        print(f" > SENT: {days_left} days reminder")
                        count += 1
                    else:
                        print(f" > FAILED: {resp}")
                else:
                    print(" > SKIPPED: No SMS provider configured")

        print(f"Job complete. Sent {count} reminders.")

if __name__ == "__main__":
    send_reminders()
