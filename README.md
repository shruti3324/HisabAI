# HisabAI — Voice Ledger

### Voice → Ledger → Intelligence → Action

HisabAI is a voice-first bookkeeping application designed for small vendors and shopkeepers in India.

Instead of typing every transaction manually, a vendor can simply speak a transaction naturally in **Hindi, Marathi, English, or Hinglish**.

For example:

> "Ramesh ne 1500 rupaye ka maal liya, 500 diye."

HisabAI converts the voice into structured financial information, shows the extracted information to the user for confirmation, and then updates the running ledger.

---

## Live Demo

**Live Application:**
https://hisabai-4p3i.onrender.com/

---

## Problem Statement

### PS 01 — Voice-Note Ledger for Small Vendors

Small shops and micro-vendors often record daily sales and credit transactions using memory, notebooks, or informal voice notes.

Traditional bookkeeping applications can be difficult to operate during a busy working day.

HisabAI addresses this problem by allowing vendors to maintain their ledger through natural voice input.

---

##  Solution

HisabAI provides an end-to-end voice-based bookkeeping workflow:

```text
Vendor Voice
     ↓
Speech-to-Text
     ↓
Language Normalization
     ↓
AI Transaction Extraction
     ↓
Human Confirmation
     ↓
Ledger Update
     ↓
Dashboard / Customers / Outstanding
     ↓
Reminders
```

The AI is a core part of the transaction pipeline rather than only a chatbot or interface feature.

---

## Key Features

### Voice-Based Transactions

Record transactions using natural speech.

Example:

> "Ramesh ne 1500 rupaye ka maal liya, 500 diye."

The system extracts:

* Customer
* Transaction amount
* Paid amount
* Outstanding amount
* Transaction type
* Relevant transaction information

---

### Multilingual Input

The application supports:

* English
* Hindi
* Marathi
* Hinglish
* Hindi/English code-switching
* Marathi/English code-switching

The original speech/transcript is preserved while normalization helps the AI understand different ways of expressing amounts and transactions.

---

### AI-Powered Extraction

The system uses AI to convert unstructured speech into structured financial information.

The AI pipeline includes:

1. Speech transcription
2. Language detection
3. Multilingual normalization
4. Transaction extraction
5. Structured validation
6. Human confirmation

The AI does not directly write financial records without user confirmation.

---

### Human Confirmation

Before a transaction is saved, the extracted information is presented to the user.

The vendor can review the:

* Customer
* Amount
* Paid amount
* Transaction type
* Outstanding amount

The user must confirm the transaction before it becomes part of the ledger.

---

### Udhaar / Outstanding Tracking

HisabAI calculates outstanding balances from ledger transactions.

Example:

```text
Total Sale:       ₹1500
Paid:              ₹500
Outstanding:      ₹1000
```

Partial payments can update the outstanding balance.

---

### Customer Management

The application maintains customer records and tracks their transactions.

Features include:

* Customer search
* Customer details
* Transaction history
* Outstanding amount
* Reminder information

---

### Dashboard

The dashboard provides a quick overview of:

* Today's sales
* Total sales
* Amount received
* Outstanding amount
* Customer count
* Recent transactions
* Recent customers

---

### Payment Reminders

HisabAI provides reminder functionality for outstanding payments.

The reminder layer tracks:

* Reminder status
* Scheduled reminders
* Reminder attempts
* Provider call information
* Promise-to-pay information
* Reminder history

---

### Natural-Language Business Queries

The application can answer supported business questions using ledger data.

Example:

> "Who owes me more than 500?"

The system maps supported questions to predefined database operations instead of executing model-generated SQL.

---

## AI Architecture

```text
┌──────────────────────────────┐
│       Vendor Voice Note      │
│ Hindi / Marathi / English    │
│ Hinglish / Code-Switching    │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│        Groq Whisper          │
│       Speech-to-Text         │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│   Language Normalization     │
│ Amounts / Numbers / Phrases  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│       AI Extraction          │
│ Customer / Amount / Paid     │
│ Credit / Transaction Type    │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│      Human Confirmation      │
│     Review → Edit → Save     │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│       SQLModel Database      │
│ Transactions / Customers     │
│ Reminders / Ledger History   │
└──────────────┬───────────────┘
               │
       ┌───────┼────────┐
       ▼       ▼        ▼
   Dashboard Customers Reminders
```

---

## Technology Stack

### Backend

* Python
* FastAPI
* Uvicorn
* SQLModel
* SQLite

### AI

* Groq API
* Whisper speech recognition
* LLM-based transaction extraction

### Frontend

* NiceGUI
* HTML
* CSS
* JavaScript

### Communication

* Twilio for reminder calls

### Deployment

* Render

---

## Project Structure

```text
HisabAI/
│
├── main.py
├── db.py
├── models.py
├── requirements.txt
│
├── services/
│   ├── ai_service.py
│   ├── language_service.py
│   ├── reminder_service.py
│   └── ...
│
├── tests/
│   └── ...
│
├── docs/
│   ├── architecture.md
│   └── test-cases.md
│
└── screenshots/
```

---

# Installation

## 1. Clone the repository

```bash
git clone https://github.com/shruti3324/HisabAI.git
```

Move into the application directory:

```bash
cd HisabAI/hisaaifinal/HisabAI
```

---

## 2. Create a virtual environment

### Windows

```bash
python -m venv .venv
```

```bash
.\.venv\Scripts\Activate.ps1
```

### macOS / Linux

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

---

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

# Environment Variables

Create a `.env` file in the project directory.

```env
GROQ_API_KEY=your_groq_api_key

TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=your_twilio_phone_number

PUBLIC_BASE_URL=http://127.0.0.1:8080
```

Never commit the `.env` file to GitHub.

Use `.env.example` as the template.

---

# Run Locally

```bash
python main.py
```

Open:

```text
http://127.0.0.1:8080
```

---

# Testing

Run:

```bash
pytest -q
```

The project contains tests covering important ledger and AI-related behavior.

Detailed evaluator test cases are documented in:

```text
docs/test-cases.md
```

---

#  Example Voice Inputs

### English

> "Ramesh bought goods worth 1500 rupees and paid 500."

Expected:

```text
Customer: Ramesh
Total: ₹1500
Paid: ₹500
Outstanding: ₹1000
```

### Hindi / Hinglish

> "Ramesh ne 1500 rupaye ka maal liya, 500 diye."

Expected:

```text
Customer: Ramesh
Total: ₹1500
Paid: ₹500
Outstanding: ₹1000
```

### Credit Transaction

> "Suresh ne 800 ka saman udhaar liya."

Expected:

```text
Customer: Suresh
Total: ₹800
Paid: ₹0
Outstanding: ₹800
```

---

#  Realistic Evaluation Scenarios

The system should be tested using:

1. Fully paid transactions
2. Partially paid transactions
3. Credit/udhaar transactions
4. Multiple customers
5. Hindi voice input
6. Marathi voice input
7. English voice input
8. Hinglish voice input
9. Multiple transactions for the same customer
10. Full repayment of outstanding credit
11. Natural-language business queries
12. Unclear or incomplete voice input

Detailed expected outputs are documented in:

```text
docs/test-cases.md
```

---

#  Safety and Data Integrity

HisabAI uses a human-confirmation step before saving AI-extracted financial information.

The AI proposes structured information.

The user decides whether the transaction should be saved.

The application also avoids allowing the AI to directly generate and execute arbitrary SQL queries.

This reduces the risk of an incorrect model interpretation silently becoming a financial record.

---

# Transaction Flow

```text
1. Vendor records voice
        ↓
2. Audio uploaded
        ↓
3. Speech converted to text
        ↓
4. Language normalized
        ↓
5. AI extracts transaction
        ↓
6. User reviews result
        ↓
7. User confirms
        ↓
8. Transaction saved
        ↓
9. Customer balance updated
        ↓
10. Dashboard refreshed
```

---

# Screenshots

## Dashboard

![Dashboard](screenshots/dashboard.png)

## Voice Input

![Voice Input](screenshots/voice-input.png)

## AI Confirmation

![AI Confirmation](screenshots/ai-confirmation.png)

## Customers

![Customers](screenshots/customers.png)

## Reminders

![Reminders](screenshots/reminders.png)

---

#  Deployment

The application is deployed using Render.

Live application:

https://hisabai-4p3i.onrender.com/

Render configuration:

```text
Root Directory:
hisaaifinal/HisabAI

Build Command:
pip install -r requirements.txt

Start Command:
uvicorn main:fastapi_app --host 0.0.0.0 --port $PORT
```

---

# Current Limitations

### SQLite

The current hackathon version uses SQLite for simplicity and local/demo deployment.

For a production multi-user system, a persistent managed database such as PostgreSQL would be more appropriate.

### Reminder Scheduler

The current reminder scheduler runs with the application process.

A production implementation would use a dedicated background job system.

### Authentication

The current hackathon version uses a demo user context rather than a complete production authentication system.

---

# Future Scope

Potential future improvements include:

* Multi-vendor authentication
* PostgreSQL deployment
* Inventory and low-stock tracking
* UPI/payment integration
* WhatsApp reminders
* Advanced analytics
* Export to Excel/PDF
* Offline voice capture
* More Indian languages
* Production-grade background workers
* Role-based access control

---

# Problem Statement Alignment

HisabAI implements PS 01 — Voice-Note Ledger for Small Vendors.

The solution provides:

* Voice-based transaction capture
* Hindi / Marathi / English support
* Speech transcription
* Structured financial extraction
* Customer identification
* Sales tracking
* Credit/udhaar tracking
* Outstanding balance calculation
* Running ledger
* Business queries
* Reminder functionality
* Human confirmation before saving

---

#  Author

**Shruti Pardeshi**

GitHub:

https://github.com/shruti3324

---

## License

This project was developed as an individual project for the Orchestrate — September 2026 AI Build Challenge.
