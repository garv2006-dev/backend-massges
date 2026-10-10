import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat
from typing import Optional, Tuple
from app.config import settings

def normalize_phone_number(phone_number: str, default_region: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Normalize and validate a phone number.
    Supports international (+...), national formats (India, US), and numbers with un-prefixed country codes.
    
    Args:
        phone_number: The phone number string to normalize
        default_region: The default region code (e.g., "IN", "US"). Defaults to settings.DEFAULT_PHONE_REGION
    
    Returns:
        Tuple of (normalized_number, error_message)
        If successful, normalized_number is in E.164 format and error_message is None
        If failed, normalized_number is None and error_message contains the reason
    """
    if not phone_number:
        return None, "Phone number is required"
    
    # Strip spaces, dashes, parentheses
    cleaned = str(phone_number).strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if not cleaned or cleaned.lower() == "nan":
        return None, "Phone number is required"
    
    pref_region = default_region or getattr(settings, "DEFAULT_PHONE_REGION", "IN")

    # 1. If starts with +, parse with international standard
    if cleaned.startswith("+"):
        try:
            parsed = phonenumbers.parse(cleaned, None)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(parsed, PhoneNumberFormat.E164), None
        except Exception:
            pass

    # 2. Try prepending '+' in case the country code was provided without '+' (e.g. 17069909314 or 918866116398)
    try:
        parsed = phonenumbers.parse("+" + cleaned, None)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, PhoneNumberFormat.E164), None
    except Exception:
        pass

    # 3. Try parsing with preferred region, then fallback to other common regions (IN, US)
    regions_to_try = [pref_region]
    for fallback in ["IN", "US"]:
        if fallback not in regions_to_try:
            regions_to_try.append(fallback)

    for reg in regions_to_try:
        try:
            parsed = phonenumbers.parse(cleaned, reg)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(parsed, PhoneNumberFormat.E164), None
        except Exception:
            continue

    return None, "Invalid phone number"

def format_phone_number_for_display(phone_number: str, default_region: Optional[str] = None) -> Optional[str]:
    """
    Format a phone number for display in international format.
    """
    try:
        pref_region = default_region or getattr(settings, "DEFAULT_PHONE_REGION", "IN")
        parsed = phonenumbers.parse(phone_number, pref_region)
        return phonenumbers.format_number(parsed, PhoneNumberFormat.INTERNATIONAL)
    except Exception:
        return None
