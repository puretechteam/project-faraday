"""
Validation helpers for entry fields.
Non-blocking by default: validation failures warn by default, only block on structurally invalid data.
"""

import re
from typing import Optional, Tuple


def validate_email(email: str) -> Tuple[bool, Optional[str]]:
    """Validate email format (basic regex).
    
    Args:
        email: Email address to validate
        
    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
        Non-blocking: Returns True even for edge cases (international-friendly).
    """
    if not email or not email.strip():
        return True, None  # Empty email is valid (optional field)
    
    # Basic email regex (non-strict, international-friendly)
    pattern = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
    if re.match(pattern, email.strip()):
        return True, None
    return False, "Email format appears invalid (warn only)"


def validate_card_number_length(card_number: str) -> Tuple[bool, Optional[str]]:
    """Validate card number length (13-19 digits).
    
    Args:
        card_number: Card number to validate (digits only expected)
        
    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    digits_only = re.sub(r'\D', '', card_number)
    if len(digits_only) < 13 or len(digits_only) > 19:
        return False, f"Card number must be 13-19 digits (got {len(digits_only)})"
    return True, None


def luhn_checksum(card_number: str) -> bool:
    """Validate card number using Luhn algorithm.
    
    Args:
        card_number: Card number (digits only expected)
        
    Returns:
        True if Luhn checksum is valid
    """
    digits_only = re.sub(r'\D', '', card_number)
    if not digits_only:
        return False
    
    def luhn_sum(n):
        n = n * 2
        return n if n < 10 else n - 9
    
    total = 0
    for i, digit in enumerate(reversed(digits_only)):
        if i % 2 == 1:
            total += luhn_sum(int(digit))
        else:
            total += int(digit)
    
    return total % 10 == 0


def validate_card_number(card_number: str) -> Tuple[bool, Optional[str]]:
    """Validate card number (length + Luhn algorithm).
    
    Args:
        card_number: Card number to validate
        
    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
        Non-blocking: Returns warnings, only blocks if structurally invalid.
    """
    if not card_number or not card_number.strip():
        return False, "Card number is required"
    
    length_valid, length_error = validate_card_number_length(card_number)
    if not length_valid:
        return False, length_error
    
    if not luhn_checksum(card_number):
        return False, "Card number fails Luhn checksum validation"
    
    return True, None


def validate_cvv(cvv: str) -> Tuple[bool, Optional[str]]:
    """Validate CVV length (3-4 digits).
    
    Args:
        cvv: CVV to validate
        
    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    if not cvv or not cvv.strip():
        return False, "CVV is required"
    
    digits_only = re.sub(r'\D', '', cvv)
    if len(digits_only) < 3 or len(digits_only) > 4:
        return False, f"CVV must be 3-4 digits (got {len(digits_only)})"
    return True, None


def validate_required_field(value: str, field_name: str) -> Tuple[bool, Optional[str]]:
    """Validate required field is not empty.
    
    Args:
        value: Field value to validate
        field_name: Name of the field for error message
        
    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    if not value or not value.strip():
        return False, f"{field_name} is required"
    return True, None

