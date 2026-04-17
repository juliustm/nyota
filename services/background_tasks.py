"""
background_tasks.py

In-process background worker using a daemon thread + the database as the queue.
No external services required (no Redis, no Celery, no extra Docker containers).

Queue mechanics:
  - Scheduled campaigns: sms_campaign rows with status=SCHEDULED and scheduled_at <= now
  - Subscription reminders: active subscriptions expiring in 5, 1, or 0 days
  - Recurring campaigns: rescheduled automatically after SENT

Start with start_background_worker(app) from create_app().
Guard with FLASK_SKIP_BACKGROUND_WORKER=1 env var to suppress during migrations.
"""

import threading
import time
import logging
from datetime import datetime, timedelta

logger = logging.getLogger('nyota.background')


def start_background_worker(app):
    """Starts a single daemon thread that ticks every 60 seconds."""
    def tick():
        logger.info("Background worker started.")
        while True:
            try:
                with app.app_context():
                    _process_scheduled_campaigns()
                    _process_subscription_reminders(app)
            except Exception as e:
                logger.error(f"Background worker error: {e}", exc_info=True)
            time.sleep(60)

    t = threading.Thread(target=tick, name="nyota-worker", daemon=True)
    t.start()


def _process_scheduled_campaigns():
    from models.nyota import (
        db, SMSCampaign, SMSCampaignStatus, SMSCampaignLog, Creator
    )
    from services.sms_service import get_sms_provider
    from routes import _resolve_campaign_audience

    due = SMSCampaign.query.filter(
        SMSCampaign.status == SMSCampaignStatus.SCHEDULED,
        SMSCampaign.scheduled_at <= datetime.utcnow()
    ).all()

    for campaign in due:
        logger.info(f"Processing scheduled campaign #{campaign.id}: {campaign.name}")
        campaign.status = SMSCampaignStatus.SENDING
        db.session.commit()

        creator = Creator.query.get(campaign.creator_id)
        provider = get_sms_provider(creator)

        if not provider:
            campaign.status = SMSCampaignStatus.FAILED
            db.session.commit()
            continue

        # If smart_exclude_recent_buyers: remove phones that purchased after the campaign
        # was scheduled/created (first send) or after the previous send (recurring).
        exclude_since = None
        if campaign.smart_exclude_recent_buyers:
            exclude_since = campaign.sent_at or campaign.scheduled_at or campaign.created_at

        phones = _resolve_campaign_audience(
            campaign.creator_id, campaign.targeting,
            exclude_buyers_since=exclude_since
        )

        # Idempotency guard: skip phones already successfully sent in this campaign run
        already_sent = set(
            r[0] for r in db.session.query(SMSCampaignLog.phone_number)
            .filter_by(campaign_id=campaign.id, status='sent').all()
        )
        phones = phones - already_sent

        sent, failed = 0, 0
        for phone in phones:
            success, resp = provider.send_sms(phone, campaign.message)
            db.session.add(SMSCampaignLog(
                campaign_id=campaign.id,
                phone_number=phone,
                status='sent' if success else 'failed',
                error_message=None if success else str(resp)[:500],
                sent_at=datetime.utcnow() if success else None
            ))
            provider._log(creator.id, phone, campaign.message, 'CAMPAIGN',
                          success, campaign_id=campaign.id,
                          error=None if success else str(resp)[:500])
            if success:
                sent += 1
            else:
                failed += 1

        campaign.sent_count = (campaign.sent_count or 0) + sent
        campaign.failed_count = (campaign.failed_count or 0) + failed
        campaign.sent_at = datetime.utcnow()

        if campaign.is_recurring and campaign.recurrence_interval_days:
            # Reset to scheduled for the next run
            campaign.status = SMSCampaignStatus.SCHEDULED
            campaign.scheduled_at = datetime.utcnow() + timedelta(days=campaign.recurrence_interval_days)
            campaign.next_run_at = campaign.scheduled_at
            logger.info(f"Recurring campaign #{campaign.id} rescheduled for {campaign.scheduled_at}.")
        else:
            campaign.status = SMSCampaignStatus.SENT

        db.session.commit()
        logger.info(f"Campaign #{campaign.id} done: {sent} sent, {failed} failed.")


def _process_subscription_reminders(app):
    from models.nyota import (
        db, Purchase, PurchaseStatus, DigitalAsset, SMSLog, SMSLogType
    )
    from services.sms_service import get_sms_provider
    from routes import check_subscription_status
    from sqlalchemy import or_

    base_url = app.config.get('BASE_URL', 'https://nyota.co.tz').rstrip('/')
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # Cover every completed purchase that has subscription-like billing:
    # either the asset has is_subscription=True, or the customer selected a
    # recurring tier (stored as ticket_data['tier']['interval']).
    candidates = db.session.query(Purchase).join(DigitalAsset).filter(
        Purchase.status == PurchaseStatus.COMPLETED,
        or_(
            DigitalAsset.is_subscription == True,
            Purchase.ticket_data.isnot(None),
        )
    ).all()

    for purchase in candidates:
        is_active, expiry_date = check_subscription_status(purchase)
        if not expiry_date:
            continue

        days_left = (expiry_date - datetime.utcnow()).days
        if days_left not in [5, 1, 0]:
            continue

        phone = purchase.customer.whatsapp_number
        already_sent_today = db.session.query(SMSLog).filter(
            SMSLog.phone_number == phone,
            SMSLog.log_type == SMSLogType.REMINDER,
            SMSLog.sent_at >= today_start
        ).first()
        if already_sent_today:
            continue

        creator = purchase.asset.creator
        provider = get_sms_provider(creator)
        if not provider or not creator.get_setting('sms_notify_subscription'):
            continue

        asset = purchase.asset
        customer = purchase.customer
        lang = (customer.language or 'sw')[:2].lower()
        link = f"{base_url}/asset/{asset.slug}"
        bucket = 'many' if days_left > 1 else str(days_left)
        tpl = provider._get_tpl(creator, f'reminder_{bucket}', lang)
        try:
            message = tpl.format(asset_title=asset.title, days=days_left, link=link)
        except KeyError:
            message = tpl
        if not message:
            continue

        success, resp = provider.send_sms(customer.whatsapp_number, message)
        provider._log(creator.id, customer.whatsapp_number, message, 'REMINDER', success,
                      error=None if success else str(resp)[:500])
        if not success:
            logger.warning(f"Reminder failed for purchase #{purchase.id}: {resp}")
