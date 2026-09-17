# VOICE LEDGER

**Voice → Ledger → Intelligence → Action**

Voice Ledger is a voice-first ledger for small vendors. Speak naturally in Hindi, Marathi, English, or code-switched speech; the app proposes a transaction, requires human confirmation, records an auditable ledger, remembers customers, and answers safe business questions.

## Phase 1 features

- Browser microphone recording and Groq Whisper transcription
- Structured AI extraction that never writes the database itself
- Mandatory editable confirmation before every save
- Validated sales, credit sales, and payment entries
- Customer matching and duplicate-name safeguards
- Correct outstanding balance calculation after partial/full payments
- Safe reversal-based Undo; no silent deletion of financial history
- Database-backed dashboard and safe natural-language business-query allow-list

## Phase 2 and multilingual upgrades

- Customer search, customer detail pages, running-balance timelines, and an in-app payment-entry flow
- A multilingual normalization layer runs **before** AI transaction extraction. It supports English, Hindi, Marathi, Hinglish, and Hindi/Marathi-English code-switching while preserving the original transcript and customer names.
- The assistant maps questions to a small allow-list of database-backed operations. It never executes model-generated SQL.
- An explainable payment follow-up indicator uses only ledger facts (outstanding balance and age of the oldest unpaid entry). It is an internal reminder aid, **not** a credit or financial score.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# add GROQ_API_KEY to .env
python main.py
```

Open `http://127.0.0.1:8080`.

## Demo

Say: `Ramesh ne 1500 rupaye ka maal liya, 500 diye.`

Review the detected customer, total, paid amount, and type, then choose **SAVE**. Ask: `Who owes me more than 500?`

The payment/reminder provider layer is intentionally not included in Phase 1. No production payment, SMS, WhatsApp, or call integration is claimed.

## Tests

```powershell
pytest -q
```
