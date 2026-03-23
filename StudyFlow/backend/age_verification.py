"""
Age Verification Service for StudyFlow Suite
Missouri SB 1455 (GUARD Act) Compliance

Uses "transactional data" method: verifies age via name + zip code
against third-party data sources (Ondato, LexisNexis, etc.)

Current implementation: Placeholder that accepts all verifications.
Replace verify_age_transactional() with real API call when ready.
"""

from datetime import date
from StudyFlow.logging_utils import debug_log


def calculate_age(birthdate_str: str) -> int:
    """Calculate age from birthdate string (YYYY-MM-DD)"""
    birth = date.fromisoformat(birthdate_str)
    today = date.today()
    age = today.year - birth.year
    if (today.month, today.day) < (birth.month, birth.day):
        age -= 1
    return age


def verify_age_transactional(legal_name: str, zip_code: str, birthdate: str) -> dict:
    """
    Verify user's age using transactional data.

    This is a PLACEHOLDER implementation. Replace the body of this function
    with a real API call to Ondato, LexisNexis, or similar provider.

    The real integration would:
    1. Send legal_name + zip_code to the provider's API
    2. Provider cross-references against utility bills, credit headers,
       university enrollment databases, etc.
    3. Provider returns confirmed age or date of birth
    4. We compare against the user-provided birthdate

    Args:
        legal_name: User's legal name (first + last)
        zip_code: User's zip code
        birthdate: User-provided birthdate (YYYY-MM-DD)

    Returns:
        {
            "verified": bool,
            "method": "transactional_data",
            "provider": "placeholder",
            "age": int,
            "reason": str (if not verified)
        }
    """
    try:
        age = calculate_age(birthdate)

        if age < 18:
            debug_log(f"[-] Age verification failed: user is {age}, must be 18+")
            return {
                "verified": False,
                "method": "transactional_data",
                "provider": "placeholder",
                "age": age,
                "reason": "User is under 18"
            }

        # ============================================================
        # PLACEHOLDER: Replace this block with real API integration
        #
        # Example with Ondato:
        #   response = ondato_client.verify_identity({
        #       "full_name": legal_name,
        #       "zip_code": zip_code,
        #       "date_of_birth": birthdate
        #   })
        #   verified = response.get("identity_confirmed", False)
        #
        # Example with LexisNexis:
        #   response = lexisnexis_client.instant_verify({
        #       "name": legal_name,
        #       "address": {"zip": zip_code},
        #       "dob": birthdate
        #   })
        #   verified = response.get("verified", False)
        #
        # For now, accept all users who are 18+ as verified.
        # ============================================================
        verified = True

        debug_log(f"[+] Age verification {'passed' if verified else 'failed'}: "
                  f"{legal_name}, zip={zip_code}, age={age}")

        return {
            "verified": verified,
            "method": "transactional_data",
            "provider": "placeholder",
            "age": age,
            "reason": None if verified else "Transactional data verification failed"
        }

    except ValueError as e:
        debug_log(f"[-] Invalid birthdate format: {birthdate}")
        return {
            "verified": False,
            "method": "transactional_data",
            "provider": "placeholder",
            "age": None,
            "reason": f"Invalid birthdate: {e}"
        }
    except Exception as e:
        debug_log(f"[-] Age verification error: {e}")
        return {
            "verified": False,
            "method": "transactional_data",
            "provider": "placeholder",
            "age": None,
            "reason": f"Verification service error: {e}"
        }
