import requests
import json
from datetime import datetime, timedelta
from flask import current_app

# Admin-configurable SMS template defaults.
# Each key maps to a CreatorSetting key (sms_tpl_<type>_<lang>).
# Creators can override any of these via the Templates tab in Campaigns.
DEFAULT_TEMPLATES = {
    # Purchase confirmation — {link} will be a magic access link
    'purchase_sw': "Asante! Umepata '{asset_title}'. Fikia sasa: {link}",
    'purchase_en': "Thank you! You got '{asset_title}'. Access now: {link}",

    # Magic link (already owns)
    'magic_sw': "Unamiliki '{asset_title}'! Fikia hapa: {link} (Saa 24, mara 3 tu)",
    'magic_en': "You own '{asset_title}'! Access: {link} (24h, 3 opens)",

    # Subscription reminders — keyed by days bucket
    'reminder_sw_many': "'{asset_title}' inaisha siku {days}. Huisha: {link}",
    'reminder_en_many': "'{asset_title}' expires in {days} days. Renew: {link}",
    'reminder_sw_1':    "'{asset_title}' inaisha KESHO. Huisha sasa: {link}",
    'reminder_en_1':    "'{asset_title}' expires TOMORROW. Renew now: {link}",
    'reminder_sw_0':    "'{asset_title}' inaisha LEO. Huisha: {link}",
    'reminder_en_0':    "'{asset_title}' expires TODAY. Renew: {link}",
}


class SMSProvider:
    def send_sms(self, to_number, message):
        raise NotImplementedError


class OnSMSProvider(SMSProvider):
    def __init__(self, api_key, api_secret, sender_id):
        self.api_key = api_key
        self.api_secret = api_secret
        self.sender_id = sender_id
        self.api_url = "https://onsms.co.tz/api/method/always_on_sms.api.sms.send_sms"

    def send_sms(self, recipients, message):
        """
        Sends an SMS to one or more recipients.
        :param recipients: List of phone numbers (strings) or a single phone number string.
        :param message: The message content.
        :return: (success: bool, response: dict/str)
        """
        if isinstance(recipients, str):
            recipients = [recipients]

        payload = {
            "api_key": self.api_key,
            "api_secret": self.api_secret,
            "sender_id": self.sender_id,
            "message": message,
            "recipients": recipients
        }

        try:
            headers = {'Content-Type': 'application/json'}
            response = requests.post(self.api_url, data=json.dumps(payload), headers=headers, timeout=10)

            try:
                response_data = response.json()
            except ValueError:
                response_data = response.text

            if response.status_code == 200:
                return True, response_data
            else:
                return False, f"HTTP {response.status_code}: {response_data}"

        except requests.RequestException as e:
            return False, str(e)

    def _get_tpl(self, creator, key, lang):
        """
        Look up a template: try creator's custom setting first, fall back to DEFAULT_TEMPLATES.
        key is a base key like 'purchase', 'magic', 'reminder_many', etc.
        """
        setting_key = f'sms_tpl_{key}_{lang}'
        if creator:
            custom = creator.get_setting(setting_key)
            if custom:
                return custom
        # Try the requested language, then fall back to Swahili
        return DEFAULT_TEMPLATES.get(f'{key}_{lang}', DEFAULT_TEMPLATES.get(f'{key}_sw', ''))

    def _log(self, creator_id, phone, message, log_type_name, success, campaign_id=None, error=None):
        """Write an entry to the global SMS audit log (best-effort, never raises)."""
        try:
            from models.nyota import db, SMSLog, SMSLogType
            log = SMSLog(
                creator_id=creator_id,
                phone_number=phone,
                message_preview=(message or '')[:200],
                log_type=SMSLogType[log_type_name.upper()],
                status='sent' if success else 'failed',
                campaign_id=campaign_id,
                error_message=error
            )
            db.session.add(log)
            db.session.commit()
        except Exception as e:
            try:
                current_app.logger.warning(f"SMS log write failed: {e}")
            except RuntimeError:
                pass

    def send_purchase_confirmation(self, purchase, base_url=None, creator=None):
        """Sends a thank-you SMS with a magic access link after successful purchase."""
        if not purchase.asset.creator.get_setting('sms_notify_purchase'):
            return False, "Purchase SMS notifications disabled"

        cr = creator or purchase.asset.creator
        customer = purchase.customer
        asset = purchase.asset
        lang = (customer.language or 'sw')[:2].lower()
        base_url = (base_url or "https://nyota.co.tz").rstrip('/')
        ref = purchase.payment_gateway_ref or "N/A"

        # Create a magic access link so the buyer can open their content immediately.
        # Falls back to /library if creation fails.
        link = f"{base_url}/library"
        try:
            from models.nyota import db, SMSMagicLink
            magic = SMSMagicLink(
                phone_number=customer.whatsapp_number,
                asset_id=asset.id,
                opens_remaining=5,
                expires_at=datetime.utcnow() + timedelta(hours=72),
            )
            db.session.add(magic)
            db.session.commit()
            link = f"{base_url}/to/{magic.token}"
        except Exception:
            pass  # use /library fallback

        tpl = self._get_tpl(cr, 'purchase', lang)
        try:
            message = tpl.format(asset_title=asset.title, link=link, ref=ref)
        except KeyError:
            message = tpl

        success, resp = self.send_sms(customer.whatsapp_number, message)
        self._log(cr.id, customer.whatsapp_number, message, 'PURCHASE', success,
                  error=None if success else str(resp)[:500])
        return success, resp

    def send_magic_link(self, phone_number, asset_title, magic_url, language='sw', creator=None):
        """Sends the magic link SMS for users who already own an asset."""
        lang = (language or 'sw')[:2].lower()
        tpl = self._get_tpl(creator, 'magic', lang)
        try:
            message = tpl.format(asset_title=asset_title, link=magic_url)
        except KeyError:
            message = tpl

        success, resp = self.send_sms(phone_number, message)
        if creator:
            self._log(creator.id, phone_number, message, 'MAGIC_LINK', success,
                      error=None if success else str(resp)[:500])
        return success, resp

    def send_subscription_reminder(self, subscription, days_left, base_url=None):
        """Sends a subscription expiry reminder."""
        if not subscription.asset.creator.get_setting('sms_notify_subscription'):
            return False, "Subscription SMS notifications disabled"

        creator = subscription.asset.creator
        customer = subscription.customer
        asset = subscription.asset
        lang = (customer.language or 'sw')[:2].lower()
        base_url = (base_url or "https://nyota.co.tz").rstrip('/')
        link = f"{base_url}/asset/{asset.slug}"

        if days_left > 1:
            bucket = 'many'
        elif days_left == 1:
            bucket = '1'
        else:
            bucket = '0'

        tpl = self._get_tpl(creator, f'reminder_{bucket}', lang)
        try:
            message = tpl.format(asset_title=asset.title, days=days_left, link=link)
        except KeyError:
            message = tpl

        if not message:
            return False, "No message generated"

        success, resp = self.send_sms(customer.whatsapp_number, message)
        self._log(creator.id, customer.whatsapp_number, message, 'REMINDER', success,
                  error=None if success else str(resp)[:500])
        return success, resp


def get_sms_provider(creator):
    """Factory function to get the configured SMS provider for a creator."""
    provider_name = creator.get_setting('sms_provider')

    if provider_name == 'onsms':
        api_key = creator.get_setting('sms_onsms_api_key')
        api_secret = creator.get_setting('sms_onsms_api_secret')
        sender_id = creator.get_setting('sms_onsms_sender_id')

        if api_key and api_secret and sender_id:
            return OnSMSProvider(api_key, api_secret, sender_id)

    return None
