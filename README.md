HisabAI — Voice Ledger for Small Vendors

Orchestrate — September 2026 · PS 01: Voice-Note Ledger for Small Vendors

Live demo: https://hisabai-4p3i.onrender.com/

1. Problem

Indian micro-vendors and shopkeepers often record sales and udhaar through memory or handwritten notebooks because conventional bookkeeping software can be time-consuming to operate.

2. Solution

HisabAI is a voice-first bookkeeping web application. A shopkeeper records a transaction in Hindi, Marathi, English, or Hinglish; the application processes the audio, extracts structured financial information, presents an AI-generated transaction preview, and lets the user confirm it before saving it to the ledger.

Core flow:

Voice Note
   ↓
Browser Audio Recording
   ↓
Speech-to-Text / AI Processing
   ↓
Structured Transaction Extraction
   ↓
Customer + Items + Total + Paid + Outstanding
   ↓
User Confirmation
   ↓
Ledger Database
   ↓
Dashboard / Customers / Reminders

The official PS01 asks for a localized voice bookkeeping application that extracts customer, items, amount, and credit-vs-paid information and updates a running ledger. fileciteturn10file0L90-L104

3. Current Implemented Features

Voice transaction recording from the browser microphone

Hindi, Marathi, English and Hinglish-friendly workflow

AI transcription and structured transaction extraction

Customer detection/creation

Multiple items per transaction

Total, paid and outstanding amount calculation

Paid / partial / pending payment status

AI transaction preview before ledger write

Manual transaction entry

Recent Transactions ledger

Dashboard metrics and Recent Activity

Customer management

Customer update flow

Clear outstanding balance during customer update

Dashboard reflects settlement by increasing Received and reducing Outstanding

Safe deletion protection for customers with active outstanding transactions

Settled transaction history remains available in the dashboard after customer deletion

Consent-aware payment reminders

Reminder candidate generation

Reminder scheduling/history endpoints

Twilio voice reminder integration

Transparent handling of Twilio trial-account restrictions

Dark / light theme

Render deployment

4. Technology Stack

Python

FastAPI

NiceGUI

SQLModel / SQLAlchemy

SQLite by default

Groq through an OpenAI-compatible SDK configuration

Browser MediaRecorder API

Twilio

Uvicorn

Render

5. Repository Structure

HisabAI/
└── hisaaifinal/
    └── HisabAI/
        ├── main.py
        ├── models.py
        ├── db.py
        ├── requirements.txt
        ├── README.md
        ├── ARCHITECTURE.md
        ├── TEST_CASES.md
        ├── SUBMISSION_CHECKLIST.md
        ├── DEMO_SCRIPT.md
        ├── SOLUTION_SUMMARY.txt
        ├── .env.example
        ├── .gitignore
        │
        └── services/
            ├── ai_service.py
            ├── language_service.py
            ├── reminder_service.py
            └── payment_service.py

6. Installation

Clone

git clone <YOUR_PUBLIC_GITHUB_REPOSITORY_URL>
cd HisabAI/hisaaifinal/HisabAI

Virtual environment

Windows:

python -m venv .venv
.venv\Scripts\activate

macOS/Linux:

python3 -m venv .venv
source .venv/bin/activate

Dependencies

pip install -r requirements.txt

Environment

Copy .env.example to .env and add your own credentials.

GROQ_API_KEY=your_key
TWILIO_ACCOUNT_SID=your_sid
TWILIO_AUTH_TOKEN=your_token
TWILIO_PHONE_NUMBER=your_number
PUBLIC_BASE_URL=https://your-public-url.example.com
DATABASE_URL=sqlite:///./ledger.db

Never commit real API keys or .env.

Run locally

python main.py

Open:

http://127.0.0.1:8080/

For Render, the application binds to 0.0.0.0 and uses the platform-provided $PORT.

7. How to Use

Voice transaction

Open Home.

Click Tap to speak.

Allow microphone access.

Speak a transaction such as:

Ramesh ne 500 rupaye ka maal liya, 200 diye.

Review the AI transaction preview.

Confirm and save.

Open Dashboard to verify the updated ledger totals.

Expected financial interpretation for the example:

Total        ₹500
Paid         ₹200
Outstanding  ₹300

Multiple items

Manual entry accepts one item per line or comma-separated items:

Paneer
Tomato
Rice

Clear outstanding balance

Open Customers.

Open Update for a customer with outstanding udhaar.

Tick Clear outstanding balance when I save changes.

Click Save Changes.

The remaining outstanding amount is recorded as collected, so Dashboard Received increases and Outstanding becomes ₹0.

The customer can then be deleted when no active outstanding transaction remains.

Reminder workflow

Open Customers.

Add/update the phone number.

Enable reminders and consent.

Open Reminders.

Click Send Reminder.

A Twilio trial account may reject certain outbound application calls. The application reports this provider limitation rather than falsely showing the call as successful.

8. API Endpoints

Health

GET /api/health

Dashboard

GET /api/dashboard

Transactions

GET  /api/transactions
POST /api/transactions/confirm
POST /api/transactions/{transaction_id}/reverse

Voice processing

POST /api/process_voice_note

Customers

GET    /api/customers
POST   /api/customers
GET    /api/customers/{customer_id}
PUT    /api/customers/{customer_id}
DELETE /api/customers/{customer_id}

Reminders

GET  /api/reminder-candidates
POST /api/customers/{customer_id}/reminder
POST /api/customers/{customer_id}/reminder-settings
POST /api/customers/{customer_id}/reminders
GET  /api/customers/{customer_id}/reminders

Twilio callbacks

POST /api/reminders/voice/{reminder_id}
POST /api/reminders/voice-response/{reminder_id}
POST /api/reminders/voice-status

9. AI Core

AI is part of the primary transaction-entry path:

Recorded voice
      ↓
AI speech processing
      ↓
Transaction extraction
      ↓
Customer / items / amounts / language / confidence / transcript
      ↓
Preview for user confirmation
      ↓
Confirmed ledger transaction

Removing the AI voice-processing path removes the main low-friction transaction-entry mechanism of the product. The challenge requires AI to be functionally central rather than a cosmetic wrapper. fileciteturn10file0L61-L74

10. Data Model

Customer
 ├─ name
 ├─ phone
 ├─ reminder settings
 └─ collection memory

Transaction
 ├─ customer
 ├─ items
 ├─ total amount
 ├─ paid amount
 ├─ outstanding amount
 ├─ payment status
 └─ transcript

Reminder
 ├─ customer
 ├─ amount
 ├─ channel
 ├─ status
 ├─ provider call ID
 └─ scheduling/history

Payment
 ├─ provider reference
 ├─ amount
 ├─ status
 └─ reconciliation fields

11. Testing

See TEST_CASES.md. Tests cover realistic multilingual voice input, udhaar, multiple items, manual entry, customer settlement, dashboard updates, reminders, scheduling, and failure handling.

The challenge explicitly asks participants to test realistic and complex sample data and document the test cases in GitHub. fileciteturn10file0L70-L78

12. Deployment

Current public deployment:

https://hisabai-4p3i.onrender.com/

Render start command:

uvicorn main:fastapi_app --host 0.0.0.0 --port $PORT

13. PS01 Requirement Status

Implemented / demonstrated

Localized voice-ledger workflow

Hindi / Marathi / English voice support

Speech-to-text / AI processing

Customer extraction

Item extraction

Transaction amount extraction

Paid / credit / outstanding calculation

Running ledger/dashboard

Multilingual workflow

Multiple items

Collection/reminder workflow

Not yet evidenced in the current codebase

Real-time text query filters and low-stock reminders are explicitly named in PS01. The current repository materials do not demonstrate those features, so they should not be claimed as completed until implemented and tested. fileciteturn10file0L94-L104

14. Academic Integrity

The challenge prohibits copying, cloning, or closely mimicking public projects and states that final code logic, interface integration, and documentation must represent the participant's original work. fileciteturn10file0L75-L84

15. Submission

The official submission requires a public GitHub repository with complete source code, a detailed README, and a 3–4 line solution summary submitted through the designated Google Form. The demo video is optional but encouraged. fileciteturn10file0L43-L52


Author

Shruti Pardeshi

Project: HisabAI — Voice Ledger

Problem Statement: PS 01 — Voice-Note Ledger for Small Vendors
