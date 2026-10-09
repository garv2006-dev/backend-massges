import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat
from typing import Optional, Tuple

def normalize_phone_number(phone_number: str, default_region: str = "US") -> Tuple[Optional[str], Optional[str]]:
    """
    Normalize and validate a phone number.
    
    Args:
        phone_number: The phone number string to normalize
        default_region: The default region code (e.g., "US", "IN")
    
    Returns:
        Tuple of (normalized_number, error_message)
        If successful, normalized_number is in E.164 format and error_message is None
        If failed, normalized_number is None and error_message contains the reason
    """
    if not phone_number:
        return None, "Phone number is required"
    
    try:
        # Parse the phone number
        parsed = phonenumbers.parse(phone_number, default_region)
        
        # Check if the number is valid
        if not phonenumbers.is_valid_number(parsed):
            return None, "Invalid phone number"
        
        # Format in E.164 format
        normalized = phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
        return normalized, None
        
    except NumberParseException as e:
        return None, f"Invalid phone number format: {str(e)}"
    except Exception as e:
        return None, f"Error processing phone number: {str(e)}"

def format_phone_number_for_display(phone_number: str, default_region: str = "US") -> Optional[str]:
    """
    Format a phone number for display in international format.
    
    Args:
        phone_number: The phone number string (should be in E.164 format)
        default_region: The default region code
    
    Returns:
        Formatted phone number string or None if invalid
    """
    try:
        parsed = phonenumbers.parse(phone_number, default_region)
        return phonenumbers.format_number(parsed, PhoneNumberFormat.INTERNATIONAL)
    except:
        return None
