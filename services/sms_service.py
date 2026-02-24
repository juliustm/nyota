import requests
import json
from flask import current_app

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
            # The API expects JSON data
            headers = {'Content-Type': 'application/json'}
            response = requests.post(self.api_url, data=json.dumps(payload), headers=headers, timeout=10)
            
            # Try to parse JSON response
            try:
                response_data = response.json()
            except ValueError:
                response_data = response.text

            if response.status_code == 200:
                # Check for API specific success indicators if known, 
                # but 200 usually implies technical success in reaching the endpoint.
                # OnSMS likely returns a specific JSON structure.
                return True, response_data
            else:
                return False, f"HTTP {response.status_code}: {response_data}"

        except requests.RequestException as e:
            return False, str(e)



    def send_purchase_confirmation(self, purchase, base_url=None):
        """
        Sends a payment confirmation SMS to the customer.
        """
        # Check if feature is enabled
        if not purchase.asset.creator.get_setting('sms_notify_purchase'):
            return False, "Purchase SMS notifications disabled"

        customer = purchase.customer
        asset = purchase.asset
        language = (customer.language or 'sw')[:2].lower() # Default to 'sw' if None
        
        # Use provided base_url or fallback (should be passed from caller)
        base_url = (base_url or "https://nyota.co.tz").rstrip('/')
        link = f"{base_url}/library"
        
        # Gateway External ID (e.g. from UZA)
        gateway_ref = purchase.payment_gateway_ref or "N/A"

        # Strict Language Logic: English ONLY if 'en', else Swahili
        if language == 'en':
            message = f"Payment for {asset.title} successful! Ref: {gateway_ref}. Access your item here: {link}"
        else:
            # Default to Swahili for 'sw' or any other detected/undefined language
            message = f"Malipo ya {asset.title} yamethibitishwa! Kumbukumbu: {gateway_ref}. Fikia bidhaa yako hapa: {link}"
            
        return self.send_sms(customer.whatsapp_number, message)

    def send_subscription_reminder(self, subscription, days_left, base_url=None):
        """
        Sends a subscription expiry reminder.
        """
        # Check if feature is enabled
        if not subscription.asset.creator.get_setting('sms_notify_subscription'):
            return False, "Subscription SMS notifications disabled"

        customer = subscription.customer
        asset = subscription.asset
        language = (customer.language or 'sw')[:2].lower() # Default to 'sw' if None
        
        # Use provided base_url or fallback
        base_url = (base_url or "https://nyota.co.tz").rstrip('/')
        link = f"{base_url}/asset/{asset.slug}"
        
        # Localization logic for reminders: English ONLY if 'en'
        message = ""
        
        if language == 'en':
            if days_left > 1:
                message = f"Hello! Your subscription for {asset.title} expires in {days_left} days. Click here to renew: {link}"
            elif days_left == 1:
                message = f"Heads up! Your subscription for {asset.title} expires TOMORROW. Renew now to keep access: {link}"
            elif days_left <= 0:
                message = f"Your subscription for {asset.title} expires TODAY. Don't lose access, renew here: {link}"
        else:
            # Default to Swahili
            if days_left > 1:
                message = f"Habari! Kifurushi chako cha {asset.title} kinaisha baada ya siku {days_left}. Bofya hapa kuhuisha: {link}"
            elif days_left == 1:
                message = f"Usipitwe! Kifurushi chako cha {asset.title} kinaisha KESHO. Bofya hapa kuhuisha sasa: {link}"
            elif days_left <= 0:
                message = f"Kifurushi chako cha {asset.title} kimeisha LEO. Usikose uhondo, huisha sasa: {link}"

        if message:
            return self.send_sms(customer.whatsapp_number, message)
        return False, "No message generated"

def get_sms_provider(creator):
    """
    Factory function to get the configured SMS provider for a creator.
    """
    provider_name = creator.get_setting('sms_provider')
    
    if provider_name == 'onsms':
        api_key = creator.get_setting('sms_onsms_api_key')
        api_secret = creator.get_setting('sms_onsms_api_secret')
        sender_id = creator.get_setting('sms_onsms_sender_id')
        
        if api_key and api_secret and sender_id:
            return OnSMSProvider(api_key, api_secret, sender_id)
            
    return None
