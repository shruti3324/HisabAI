"""
HisabAI - AI Voice Processing Service

Flow:

Browser microphone
        ↓
audio file
        ↓
Groq Whisper
        ↓
transcript
        ↓
LLM transaction extraction
        ↓
structured transaction
        ↓
main.py confirmation UI

This service DOES NOT directly write transactions
to the database.
"""

import json
import os
import re
from datetime import date
from typing import Any, Dict

from dotenv import load_dotenv
from openai import OpenAI

from services.language_service import (
    normalize_extraction,
    normalize_spoken_numbers,
)


# =========================================================
# LOAD .ENV
# =========================================================

# ai_service.py is inside:
# HisabAI/services/ai_service.py
#
# Therefore the project root is one directory above this file.

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

ENV_FILE = os.path.join(
    BASE_DIR,
    ".env",
)

load_dotenv(
    ENV_FILE,
    override=True,
)

print("=" * 60)
print("[ENV] Loading environment")
print("[ENV] Project directory:", BASE_DIR)
print("[ENV] .env file:", ENV_FILE)
print("[ENV] .env exists:", os.path.exists(ENV_FILE))
print(
    "[ENV] GROQ_API_KEY loaded:",
    bool(os.getenv("GROQ_API_KEY")),
)
print("=" * 60)


# =========================================================
# CONFIGURATION
# =========================================================

GROQ_API_KEY = os.getenv(
    "GROQ_API_KEY"
)

GROQ_BASE_URL = os.getenv(
    "GROQ_BASE_URL",
    "https://api.groq.com/openai/v1",
).strip()


# ---------------------------------------------------------
# Whisper model
# ---------------------------------------------------------

WHISPER_MODEL = os.getenv(
    "GROQ_WHISPER_MODEL",
    "whisper-large-v3",
).strip()


# ---------------------------------------------------------
# LLM extraction model
# ---------------------------------------------------------

EXTRACTION_MODEL = os.getenv(
    "GROQ_EXTRACTION_MODEL",
    "openai/gpt-oss-120b",
).strip()


# =========================================================
# CLIENT
# =========================================================

def _client() -> OpenAI:
    """
    Create Groq client only when required.
    """

    # Reload .env in case environment was changed
    # after this module was imported.
    load_dotenv(
        ENV_FILE,
        override=True,
    )

    key = os.getenv(
        "GROQ_API_KEY"
    )

    if not key:
        raise RuntimeError(
            "GROQ_API_KEY is not configured. "
            "Add GROQ_API_KEY to your .env file."
        )

    key = key.strip()

    if not key:
        raise RuntimeError(
            "GROQ_API_KEY is empty. "
            "Add your Groq API key to the .env file."
        )

    print(
        "[AI] Groq API key detected."
    )

    print(
        "[AI] Groq base URL:",
        GROQ_BASE_URL,
    )

    return OpenAI(
        api_key=key,
        base_url=GROQ_BASE_URL,
    )


# =========================================================
# DEFAULT TRANSACTION
# =========================================================

def _empty_transaction(
    transcript: str = "",
) -> Dict[str, Any]:

    return {
        "intent": "unknown",
        "customer_name": None,
        "item": None,
        "total_amount": 0.0,
        "paid_amount": 0.0,
        "outstanding_amount": 0.0,
        "payment_method": None,
        "due_date": None,
        "payment_status": "unclear",
        "language": (
            detect_language(transcript)
            if transcript
            else "unknown"
        ),
        "confidence": 0.0,
    }


# =========================================================
# SAFE JSON
# =========================================================

def _extract_json(
    text: str,
) -> Dict[str, Any]:

    """
    Extract JSON from an LLM response.

    Handles:
    - normal JSON
    - ```json ... ```
    - text surrounding JSON
    """

    if not text:
        return {}

    text = text.strip()

    # -----------------------------------------------------
    # Remove markdown code fences
    # -----------------------------------------------------

    text = re.sub(
        r"^```json\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"^```\s*",
        "",
        text,
    )

    text = re.sub(
        r"\s*```$",
        "",
        text,
    )

    text = text.strip()

    # -----------------------------------------------------
    # Direct JSON
    # -----------------------------------------------------

    try:

        value = json.loads(text)

        if isinstance(value, dict):
            return value

    except Exception:
        pass

    # -----------------------------------------------------
    # Locate first JSON object
    # -----------------------------------------------------

    start = text.find("{")
    end = text.rfind("}")

    if (
        start != -1
        and end != -1
        and end > start
    ):

        candidate = text[
            start:end + 1
        ]

        try:

            value = json.loads(
                candidate
            )

            if isinstance(value, dict):
                return value

        except Exception:
            pass

    return {}


# =========================================================
# NUMBER HELPERS
# =========================================================

def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:

    if value is None:
        return default

    if isinstance(value, bool):
        return default

    if isinstance(
        value,
        (int, float),
    ):
        return float(value)

    text = str(value).strip()

    if not text:
        return default

    # Remove currency symbols / commas
    text = text.replace(
        "₹",
        "",
    )

    text = text.replace(
        "rs.",
        "",
    )

    text = text.replace(
        "rs",
        "",
    )

    text = text.replace(
        "inr",
        "",
    )

    text = text.replace(
        ",",
        "",
    )

    text = text.strip()

    # Extract first numeric value
    match = re.search(
        r"-?\d+(?:\.\d+)?",
        text,
    )

    if not match:
        return default

    try:
        return float(
            match.group(0)
        )

    except Exception:
        return default


# =========================================================
# LANGUAGE DETECTION
# =========================================================

def detect_language(
    transcript: str,
) -> str:

    if not transcript:
        return "unknown"

    text = transcript.lower()

    # -----------------------------------------------------
    # Devanagari detection
    # -----------------------------------------------------

    devanagari = len(
        re.findall(
            r"[\u0900-\u097F]",
            transcript,
        )
    )

    if devanagari > 0:

        # Marathi indicators
        marathi_words = [
            "आहे",
            "आहेत",
            "घेतले",
            "घेतला",
            "दिले",
            "देतो",
            "पैसे",
            "उधारी",
            "उधार",
            "रुपये",
            "माल",
            "किती",
            "उद्या",
            "परवा",
        ]

        if any(
            word in transcript
            for word in marathi_words
        ):
            return "marathi"

        return "hindi"

    # -----------------------------------------------------
    # Roman Marathi / Hinglish
    # -----------------------------------------------------

    marathi_roman = [
        "rupaye",
        "rupay",
        "paise",
        "udhari",
        "udhaar",
        "ghyetla",
        "ghetla",
        "ghetle",
        "dile",
        "udya",
        "parva",
        "maal",
    ]

    if any(
        word in text
        for word in marathi_roman
    ):
        return "hinglish"

    # -----------------------------------------------------
    # English
    # -----------------------------------------------------

    english_words = [
        "sold",
        "bought",
        "received",
        "paid",
        "payment",
        "customer",
        "rupees",
        "invoice",
        "sale",
    ]

    if any(
        word in text
        for word in english_words
    ):
        return "english"

    return "hinglish"


# =========================================================
# TRANSCRIPTION
# =========================================================

def transcribe_audio(
    audio_path: str,
) -> Dict[str, Any]:

    """
    Transcribe audio using Groq Whisper.
    """

    if not os.path.exists(
        audio_path
    ):

        raise FileNotFoundError(
            f"Audio file not found: {audio_path}"
        )

    client = _client()

    print(
        "[AI] Transcribing audio:",
        audio_path,
    )

    with open(
        audio_path,
        "rb",
    ) as audio_file:

        result = (
            client.audio.transcriptions.create(
                model=WHISPER_MODEL,
                file=audio_file,
                response_format="verbose_json",
            )
        )

    transcript = getattr(
        result,
        "text",
        None,
    )

    if transcript is None:

        if isinstance(
            result,
            dict,
        ):

            transcript = result.get(
                "text",
                "",
            )

        else:

            transcript = str(
                result
            )

    transcript = (
        transcript or ""
    ).strip()

    language = detect_language(
        transcript
    )

    print(
        "[AI] Transcript:",
        transcript,
    )

    print(
        "[AI] Detected language:",
        language,
    )

    return {
        "text": transcript,
        "transcript": transcript,
        "language": language,
    }


# =========================================================
# EXTRACTION PROMPT
# =========================================================

def _build_extraction_prompt(
    transcript: str,
) -> str:

    today = date.today().isoformat()

    return f"""
You are the transaction extraction engine for
HisabAI, a voice ledger application for Indian
small businesses.

The user may speak in:

- Hindi
- Marathi
- English
- Hinglish
- Marathi mixed with English
- Hindi mixed with English

Today's date is:

{today}

VOICE TRANSCRIPT:

{transcript}

Extract the transaction into STRICT JSON.

Return ONLY JSON.

Use exactly these keys:

{{
  "intent": "sale|payment|expense|unknown",
  "customer_name": null,
  "item": null,
  "total_amount": 0,
  "paid_amount": 0,
  "outstanding_amount": 0,
  "payment_method": null,
  "due_date": null,
  "payment_status": "paid|partial|credit|unclear",
  "language": "hindi|marathi|english|hinglish",
  "confidence": 0.0
}}

IMPORTANT RULES:

1. total_amount means the total value of the sale.

2. paid_amount means money actually paid now.

3. outstanding_amount means:
   total_amount - paid_amount

4. Never make outstanding_amount negative.

5. If the customer paid the full amount:
   payment_status = "paid"

6. If some money was paid:
   payment_status = "partial"

7. If nothing was paid and money is owed:
   payment_status = "credit"

8. If there is no clear transaction:
   intent = "unknown"

9. Customer names should be returned exactly
   as understood from the speech.

10. Do not invent a customer name.

11. If no item is mentioned:
    item = null

12. If no payment method is mentioned:
    payment_method = null

13. If the user says:
    "tomorrow", "udya", "kal", etc.,
    convert it to an ISO date.

14. If no due date is mentioned:
    due_date = null

15. Indian currency is INR.

16. Example:
    "500 rupaye ka maal liya, 200 diye"

    means:
    total_amount = 500
    paid_amount = 200
    outstanding_amount = 300
    payment_status = "partial"

17. Example:
    "500 rupaye ka maal liya"

    means:
    total_amount = 500
    paid_amount = 0
    outstanding_amount = 500
    payment_status = "credit"

18. If nothing indicates payment,
    assume paid_amount = 0.

19. Example:
    "500 ka maal liya aur 500 diye"

    means fully paid.

20. Example:
    "500 ka maal liya udhaar"

    means:
    total_amount = 500
    paid_amount = 0
    outstanding_amount = 500
    payment_status = "credit"

21. Return confidence between 0 and 1.

22. Do not explain anything outside JSON.

23. Do not add extra JSON keys.

24. Never invent amounts that are not present
    in the transcript.

25. If only a payment is mentioned, such as:
    "Riya ne 200 rupaye diye"

    set:
    intent = "payment"
    paid_amount = 200

    Do not invent total_amount.

26. If the transaction is a payment against
    existing credit, outstanding_amount should
    be 0 unless the remaining balance is explicitly
    stated in the transcript.

27. Preserve the customer's name exactly as
    understood from the transcript.

28. For Hindi/Marathi speech, understand common
    words such as:

    diya / diye / diye hain
    liya / liye
    udhaar / udhari
    maal
    paise
    rupaye
    kal
    udya
    parva
    payment
    cash
    UPI
    Google Pay
    GPay

29. Confidence should reflect how clearly the
    transaction can be extracted from the speech.

Return ONLY the JSON object.
"""


# =========================================================
# TRANSACTION EXTRACTION
# =========================================================

def extract_transaction(
    transcript: str,
) -> Dict[str, Any]:

    if not transcript:
        return _empty_transaction()

    # -----------------------------------------------------
    # Normalize spoken numbers
    # -----------------------------------------------------

    try:

        normalized_text = (
            normalize_spoken_numbers(
                transcript
            )
        )

        if normalized_text:

            transcript_for_ai = (
                normalized_text
            )

        else:

            transcript_for_ai = transcript

    except Exception:

        transcript_for_ai = transcript

    client = _client()

    prompt = _build_extraction_prompt(
        transcript_for_ai
    )

    print(
        "[AI] Extracting transaction..."
    )

    print(
        "[AI] Extraction model:",
        EXTRACTION_MODEL,
    )

    # -----------------------------------------------------
    # Groq LLM
    # -----------------------------------------------------

    response = (
        client.chat.completions.create(
            model=EXTRACTION_MODEL,
            temperature=0,
            response_format={
                "type": "json_object"
            },
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a strict JSON "
                        "transaction extraction engine. "
                        "Return only valid JSON. "
                        "Never add explanations."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        )
    )

    # -----------------------------------------------------
    # Read response
    # -----------------------------------------------------

    content = (
        response.choices[0]
        .message
        .content
        or ""
    )

    print(
        "[AI] Extraction response:",
        content,
    )

    # -----------------------------------------------------
    # Parse JSON
    # -----------------------------------------------------

    data = _extract_json(
        content
    )

    if not data:

        print(
            "[AI] WARNING: Could not parse "
            "LLM JSON response."
        )

        return _empty_transaction(
            transcript
        )

    # =====================================================
    # NORMALIZE NUMBERS
    # =====================================================

    total = _safe_float(
        data.get(
            "total_amount",
            0,
        )
    )

    paid = _safe_float(
        data.get(
            "paid_amount",
            0,
        )
    )

    # Never allow negative values
    total = max(
        total,
        0.0,
    )

    paid = max(
        paid,
        0.0,
    )

    # -----------------------------------------------------
    # Prevent paid > total for sale transactions
    # -----------------------------------------------------

    intent = (
        data.get("intent")
        or "unknown"
    )

    if (
        intent != "payment"
        and total > 0
    ):

        paid = min(
            paid,
            total,
        )

    # =====================================================
    # CALCULATE OUTSTANDING OURSELVES
    # =====================================================

    outstanding = max(
        total - paid,
        0.0,
    )

    # =====================================================
    # PAYMENT STATUS
    # =====================================================

    if (
        intent == "payment"
        and total <= 0
    ):

        status = "unclear"

    elif total > 0:

        if paid >= total:

            status = "paid"

        elif paid > 0:

            status = "partial"

        else:

            status = "credit"

    else:

        status = "unclear"

    # =====================================================
    # CONFIDENCE
    # =====================================================

    confidence = _safe_float(
        data.get(
            "confidence",
            0,
        )
    )

    confidence = min(
        max(
            confidence,
            0.0,
        ),
        1.0,
    )

    # =====================================================
    # LANGUAGE
    # =====================================================

    language = (
        data.get("language")
        or detect_language(
            transcript
        )
    )

    # =====================================================
    # FINAL RESULT
    # =====================================================

    result = {

        "intent": intent,

        "customer_name": (
            data.get(
                "customer_name"
            )
            or None
        ),

        "item": (
            data.get(
                "item"
            )
            or None
        ),

        "total_amount": total,

        "paid_amount": paid,

        "outstanding_amount":
            outstanding,

        "payment_method": (
            data.get(
                "payment_method"
            )
            or None
        ),

        "due_date": (
            data.get(
                "due_date"
            )
            or None
        ),

        "payment_status":
            status,

        "language":
            language,

        "confidence":
            confidence,
    }

    # =====================================================
    # FINAL NORMALIZATION
    # =====================================================

    try:

        normalized = normalize_extraction(
            result
        )

        if normalized:
            result = normalized

    except Exception as exc:

        print(
            "[AI] Normalization warning:",
            exc,
        )

    return result


# =========================================================
# FULL VOICE PIPELINE
# =========================================================

def process_voice_note(
    audio_path: str,
) -> Dict[str, Any]:

    """
    Complete voice processing pipeline.

    Audio
      ↓
    Whisper
      ↓
    Transcript
      ↓
    LLM extraction
      ↓
    Structured transaction
    """

    print("=" * 60)
    print("[AI] PROCESSING VOICE NOTE")
    print("=" * 60)

    # =====================================================
    # STEP 1: TRANSCRIPTION
    # =====================================================

    transcription = transcribe_audio(
        audio_path
    )

    transcript = (
        transcription.get(
            "transcript"
        )
        or ""
    )

    if not transcript:

        return {
            "success": False,
            "message": (
                "I could not understand "
                "the voice recording."
            ),
            "transcript": "",
            "text": "",
            "transaction": None,
        }

    # =====================================================
    # STEP 2: EXTRACTION
    # =====================================================

    transaction = extract_transaction(
        transcript
    )

    # =====================================================
    # STEP 3: FINAL RESPONSE
    # =====================================================

    result = {

        "success": True,

        "message": (
            "Voice transaction processed."
        ),

        "transcript":
            transcript,

        "text":
            transcript,

        "language": (
            transcription.get(
                "language"
            )
            or transaction.get(
                "language"
            )
        ),

        "transaction":
            transaction,

        # -------------------------------------------------
        # Flat fields for frontend
        # -------------------------------------------------

        "intent":
            transaction.get(
                "intent"
            ),

        "customer_name":
            transaction.get(
                "customer_name"
            ),

        "item":
            transaction.get(
                "item"
            ),

        "total_amount":
            transaction.get(
                "total_amount",
                0,
            ),

        "paid_amount":
            transaction.get(
                "paid_amount",
                0,
            ),

        "outstanding_amount":
            transaction.get(
                "outstanding_amount",
                0,
            ),

        "payment_method":
            transaction.get(
                "payment_method"
            ),

        "due_date":
            transaction.get(
                "due_date"
            ),

        "payment_status":
            transaction.get(
                "payment_status"
            ),

        "confidence":
            transaction.get(
                "confidence",
                0,
            ),
    }

    print(
        "[AI] FINAL RESULT:"
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )

    print("=" * 60)

    return result


# =========================================================
# COMPATIBILITY ALIASES
# =========================================================

def transcribe_and_extract(
    audio_path: str,
) -> Dict[str, Any]:

    return process_voice_note(
        audio_path
    )


def process_audio(
    audio_path: str,
) -> Dict[str, Any]:

    return process_voice_note(
        audio_path
    )


# =========================================================
# SIMPLE TEXT EXTRACTION
# =========================================================

def extract_from_text(
    transcript: str,
) -> Dict[str, Any]:

    return extract_transaction(
        transcript
    )


# =========================================================
# TEST HELPER
# =========================================================

if __name__ == "__main__":

    print(
        "HisabAI AI Service"
    )

    print(
        "Project directory:",
        BASE_DIR,
    )

    print(
        "Environment file:",
        ENV_FILE,
    )

    print(
        "GROQ API key loaded:",
        bool(
            os.getenv(
                "GROQ_API_KEY"
            )
        ),
    )

    print(
        "Extraction model:",
        EXTRACTION_MODEL,
    )

    print(
        "Whisper model:",
        WHISPER_MODEL,
    )

    print(
        "Available functions:"
    )

    print(
        "- transcribe_audio()"
    )

    print(
        "- extract_transaction()"
    )

    print(
        "- process_voice_note()"
    )

    print(
        "- transcribe_and_extract()"
    )

    print(
        "- process_audio()"
    )

    print(
        "- extract_from_text()"
    )