"""
Age Verification Service for StudyFlow Suite
Missouri SB 1455 (GUARD Act) Compliance

Uses Veratad AgeMatch5.0 API for transactional data age verification.
Verifies identity via name + address + zip against public/private records.
No government ID upload required.

Environment variables:
    VERATAD_USERNAME - API account username
    VERATAD_PASSWORD - API account password
    VERATAD_TEST_MODE - Set to "true" to use test database (free, no live data)
"""

import os
import requests
from datetime import date
from StudyFlow.logging_utils import debug_log

VERATAD_API_URL = "https://production.idresponse.com/process/comprehensive/gateway"
VERATAD_SERVICE = "AgeMatch5.0"
VERATAD_RULESET = "AgeMatch5_0_RuleSet_YOB"  # Base + Year of Birth must match


def calculate_age(birthdate_str: str) -> int:
    """Calculate age from birthdate string (YYYY-MM-DD)"""
    birth = date.fromisoformat(birthdate_str)
    today = date.today()
    age = today.year - birth.year
    if (today.month, today.day) < (birth.month, birth.day):
        age -= 1
    return age


def verify_age_transactional(legal_name: str, zip_code: str, birthdate: str,
                              address: str = "", city: str = "",
                              state: str = "", reference: str = None) -> dict:
    """
    Verify user's age using Veratad AgeMatch5.0 API.

    Args:
        legal_name: User's legal name ("First Last")
        zip_code: User's zip code
        birthdate: User-provided birthdate (YYYY-MM-DD)
        address: Street address (line 1)
        city: City
        state: State abbreviation
        reference: Unique user reference ID

    Returns:
        {
            "verified": bool,
            "method": "transactional_data",
            "provider": "veratad_agematch5",
            "age": int,
            "reason": str (if not verified),
            "confirmation": str (Veratad confirmation number)
        }
    """
    try:
        age = calculate_age(birthdate)

        if age < 18:
            debug_log(f"[-] Age verification failed: user is {age}, must be 18+")
            return {
                "verified": False,
                "method": "transactional_data",
                "provider": "veratad_agematch5",
                "age": age,
                "reason": "User is under 18",
                "confirmation": None
            }

        # Parse legal name into first/last
        name_parts = legal_name.strip().split()
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[-1] if len(name_parts) > 1 else ""

        # Convert birthdate from YYYY-MM-DD to YYYYMMDD
        dob_formatted = birthdate.replace("-", "")

        # Get API credentials
        veratad_user = os.environ.get("VERATAD_USERNAME")
        veratad_pass = os.environ.get("VERATAD_PASSWORD")
        test_mode = os.environ.get("VERATAD_TEST_MODE", "false").lower() == "true"

        if not veratad_user or not veratad_pass:
            debug_log("[-] VERATAD_USERNAME or VERATAD_PASSWORD not configured")
            return {
                "verified": False,
                "method": "transactional_data",
                "provider": "veratad_agematch5",
                "age": age,
                "reason": "Age verification service not configured",
                "confirmation": None
            }

        # Build API request
        payload = {
            "user": veratad_user,
            "pass": veratad_pass,
            "service": VERATAD_SERVICE,
            "rules": VERATAD_RULESET,
            "reference": reference or "",
            "target": {
                "fn": first_name,
                "ln": last_name,
                "addr": address,
                "city": city,
                "state": state,
                "zip": zip_code,
                "dob": dob_formatted,
                "age": "18+"
            }
        }

        # Add test key if in test mode
        if test_mode:
            payload["target"]["test_key"] = "general_identity"
            debug_log("[*] Veratad running in TEST MODE (no live data charges)")

        debug_log(f"[*] Calling Veratad AgeMatch5.0: {first_name} {last_name}, "
                  f"zip={zip_code}, test={test_mode}")

        # Call Veratad API
        response = requests.post(
            VERATAD_API_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )

        response.raise_for_status()
        data = response.json()

        # Parse result
        result = data.get("result", {})
        action = result.get("action", "FAIL")
        detail = result.get("detail", "UNKNOWN")
        confirmation = data.get("meta", {}).get("confirmation")

        verified = action == "PASS"

        # Map detail to user-friendly reason
        reason_map = {
            "NO MATCH": "Identity could not be verified. Please check your information.",
            "AGE NOT VERIFIED": "Your identity was found but age could not be confirmed.",
            "TARGET IS DECEASED": "This identity is flagged as deceased. Please contact support.",
            "AGE NOT SUBMITTED": "Internal error: age parameter missing.",
            "POSSIBLE MINOR": "Verification indicates the user may be under 18.",
            "ALL CHECKS PASSED": None
        }

        reason = reason_map.get(detail, detail) if not verified else None

        debug_log(f"[{'+'if verified else '-'}] Veratad result: action={action}, "
                  f"detail={detail}, confirmation={confirmation}")

        return {
            "verified": verified,
            "method": "transactional_data",
            "provider": "veratad_agematch5",
            "age": age,
            "reason": reason,
            "confirmation": str(confirmation) if confirmation else None
        }

    except requests.Timeout:
        debug_log("[-] Veratad API timeout")
        return {
            "verified": False,
            "method": "transactional_data",
            "provider": "veratad_agematch5",
            "age": calculate_age(birthdate) if birthdate else None,
            "reason": "Verification service timed out. Please try again.",
            "confirmation": None
        }
    except requests.RequestException as e:
        debug_log(f"[-] Veratad API error: {e}")
        return {
            "verified": False,
            "method": "transactional_data",
            "provider": "veratad_agematch5",
            "age": None,
            "reason": "Verification service unavailable. Please try again later.",
            "confirmation": None
        }
    except ValueError as e:
        debug_log(f"[-] Invalid birthdate format: {birthdate}")
        return {
            "verified": False,
            "method": "transactional_data",
            "provider": "veratad_agematch5",
            "age": None,
            "reason": f"Invalid date of birth format.",
            "confirmation": None
        }
    except Exception as e:
        debug_log(f"[-] Age verification error: {e}")
        return {
            "verified": False,
            "method": "transactional_data",
            "provider": "veratad_agematch5",
            "age": None,
            "reason": "Verification service error. Please try again later.",
            "confirmation": None
        }
