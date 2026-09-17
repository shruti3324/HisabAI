# HisabAI Architecture

## 1. Project Overview

**HisabAI** is a voice-first digital ledger for small vendors and shopkeepers.

It converts natural voice notes in **Hindi, Marathi, English, and Hinglish** into structured transaction data. The user can review the AI-generated transaction before saving it to the ledger.

### Problem Statement

**Orchestrate — September 2026**  
**PS 01: Voice-Note Ledger for Small Vendors**

The application is designed around the workflow:

> **Voice → AI Understanding → Transaction Preview → User Confirmation → Ledger → Dashboard / Reminders**

AI is a core part of the transaction workflow. Without transcription and structured extraction, the primary voice-ledger workflow cannot be completed.

---

# 2. High-Level Architecture

```text
                         ┌──────────────────────────────┐
                         │          Shopkeeper           │
                         │                              │
                         │ Hindi / Marathi / English    │
                         │ Hinglish voice input         │
                         └──────────────┬───────────────┘
                                        │
                                        │ Voice Note
                                        ▼
                         ┌──────────────────────────────┐
                         │        NiceGUI Web UI         │
                         │                              │
                         │ MediaRecorder + JavaScript    │
                         │ Transaction Preview           │
                         │ Dashboard / Customers        │
                         │ Reminders                    │
                         └──────────────┬───────────────┘
                                        │
                                        │ audio/webm
                                        ▼
                         ┌──────────────────────────────┐
                         │          FastAPI              │
                         │       Application API         │
                         │                              │
                         │ Routes / Validation /        │
                         │ Transaction Processing       │
                         └──────────────┬───────────────┘
                                        │
                                        ▼
                         ┌──────────────────────────────┐
                         │        AI Service             │
                         │                              │
                         │ Speech Transcription         │
                         │ Transaction Extraction       │
                         │ Structured JSON Output       │
                         │ Confidence / Language Data   │
                         └──────────────┬───────────────┘
                                        │
                                        ▼
                         ┌──────────────────────────────┐
                         │    AI Transaction Preview    │
                         │                              │
                         │ Customer                     │
                         │ Items                        │
                         │ Total Amount                 │
                         │ Paid Amount                  │
                         │ Outstanding Amount           │
                         │ Credit / Paid Status         │
                         │ Language / Confidence        │
                         └──────────────┬───────────────┘
                                        │
                                User Confirmation
                                        │
                                        ▼
                         ┌──────────────────────────────┐
                         │       SQLModel Database      │
                         │                              │
                         │ Customer                     │
                         │ Transaction                  │
                         │ Reminder                     │
                         │ Payment                      │
                         └──────────────┬───────────────┘
                                        │
                     ┌──────────────────┼──────────────────┐
                     │                  │                  │
                     ▼                  ▼                  ▼
            ┌────────────────┐ ┌────────────────┐ ┌────────────────┐
            │   Dashboard    │ │   Customers    │ │   Reminders    │
            │                │ │                │ │                │
            │ Sales          │ │ Customer data  │ │ Due amounts    │
            │ Received       │ │ Outstanding    │ │ Reminder state │
            │ Udhaar         │ │ History        │ │ Scheduling     │
            └────────────────┘ └────────────────┘ └───────┬────────┘
                                                           │
                                                           ▼
                                                  ┌────────────────┐
                                                  │     Twilio     │
                                                  │ Voice Calls    │
                                                  └────────────────┘
3. Application Layers
3.1 Presentation Layer

The frontend is implemented using NiceGUI with HTML and JavaScript.

Main user-facing areas
Home / Voice Ledger
AI Transaction Preview
Dashboard
Customer Management
Reminder Management

The interface is designed for a shopkeeper rather than a technical user.

The primary interaction is:

Record a voice note.
Send it for AI processing.
Review the extracted transaction.
Confirm or cancel.
View the updated ledger.
4. Backend Layer

The backend uses FastAPI.

FastAPI handles:

Voice-note upload
AI processing requests
Transaction confirmation
Transaction retrieval
Dashboard data
Customer operations
Reminder operations
Payment-related operations
Health/application endpoints

The application is started in production using:

uvicorn main:fastapi_app --host 0.0.0.0 --port $PORT

The application also supports the hosting platform's assigned PORT environment variable.

5. AI Processing Pipeline

AI is central to the main product workflow.

Voice Note
    │
    ▼
Audio Upload
    │
    ▼
Speech-to-Text
    │
    ▼
Language / Transcript Processing
    │
    ▼
Transaction Extraction
    │
    ▼
Structured Transaction
    │
    ├── Customer
    ├── Items
    ├── Total Amount
    ├── Paid Amount
    ├── Outstanding Amount
    ├── Transaction Type
    ├── Language
    └── Confidence
    │
    ▼
Human Confirmation
    │
    ▼
Database
5.1 Speech Transcription

The uploaded voice note is transcribed using the configured AI speech-to-text provider.

The application is designed for multilingual shopkeeper speech, including:

Hindi
Marathi
English
Hinglish

The transcript is retained with the provisional transaction information so that the user can review what the AI understood.

6. Structured Transaction Extraction

The AI converts an unstructured statement such as:

"Ramesh ne 500 rupaye ka maal liya,
200 diye, 300 kal dega."

into structured information such as:

Customer: Ramesh
Total: ₹500
Paid: ₹200
Outstanding: ₹300
Transaction Type: Credit / Udhaar

The transaction is not immediately committed simply because the AI produced an interpretation.

A confirmation step is used before the final ledger write.

This reduces the risk of incorrect AI extraction directly changing financial records.

7. Transaction Confirmation Flow
                Voice Note
                    │
                    ▼
              AI Extraction
                    │
                    ▼
          ┌─────────────────────┐
          │ Transaction Preview │
          │                     │
          │ Customer: Ramesh    │
          │ Items: Grocery      │
          │ Total: ₹500         │
          │ Paid: ₹200          │
          │ Due: ₹300           │
          └─────────┬───────────┘
                    │
             ┌──────┴──────┐
             │             │
           Confirm        Cancel
             │             │
             ▼             ▼
          Save to        Discard
          Ledger

The confirmation boundary is intentionally placed between AI interpretation and permanent ledger storage.

8. Database Architecture

HisabAI uses SQLModel for database models and SQLAlchemy-based database access.

The database configuration supports a DATABASE_URL environment variable.

By default, the application can use:

sqlite:///./ledger.db
Main database entities
Customer

Stores customer-level information such as:

Customer name
Normalized name
Phone number
Reminder information
Reminder count
Last reminder timestamp
Promise-to-pay date
Transaction

Stores ledger transactions including:

Customer
Transaction type
Item / items
Total amount
Paid amount
Outstanding amount
Payment status
Due date
Detected language
AI confidence
Raw transcript
Source
Confirmation status
Status / reversal information
Creation and update timestamps
Reminder

Stores reminder records such as:

Customer
Outstanding amount
Reminder type
Channel
Status
Message
Outcome
Provider identifiers
Attempt number
Scheduling information
AI decision metadata
Promise-to-pay information
Payment

Stores payment-related information including:

Customer
Amount
Payment provider
Provider reference
Payment status
Payment IDs
Payment link
Currency
Related ledger transaction
Verification timestamp
9. Service Architecture

The backend logic is separated into focused service modules.

services/
├── __init__.py
├── ai_service.py
├── analytics_service.py
├── customer_service.py
├── language_service.py
├── payment_service.py
├── query_service.py
├── reminder_service.py
├── risk_service.py
├── scheduler_service.py
├── transaction_service.py
└── validation_service.py
Service Responsibilities
ai_service.py

Responsible for AI-related processing such as:

Audio transcription
AI transaction extraction
Converting natural language into structured transaction data
analytics_service.py

Provides calculations and data used by the application dashboard and business-level summaries.

customer_service.py

Handles customer-related operations and customer data management.

language_service.py

Handles language normalization and processing required for multilingual transaction input.

payment_service.py

Contains payment-related application logic and payment reconciliation support.

query_service.py

Provides application-level query functionality for retrieving and processing ledger information.

reminder_service.py

Handles reminder-related business logic, including reminder creation and reminder state management.

risk_service.py

Provides risk-related checks used by the application workflow.

scheduler_service.py

Provides scheduling-related functionality for reminder and background workflows.

transaction_service.py

Contains transaction-related business logic and ledger processing.

validation_service.py

Provides validation and consistency checks before application data is committed.

10. Core Data Flow
Voice Ledger Flow
1. User records voice
        ↓
2. Browser creates audio/webm
        ↓
3. FastAPI receives audio
        ↓
4. AI transcribes audio
        ↓
5. AI extracts structured transaction
        ↓
6. Application validates extracted fields
        ↓
7. Transaction preview is shown
        ↓
8. User confirms
        ↓
9. Customer is created/found
        ↓
10. Transaction is saved
        ↓
11. Outstanding balance is updated
        ↓
12. Dashboard reflects the transaction
11. Multi-Item Transaction Handling

A transaction can contain multiple items.

For example:

"Ramesh ne 2 kilo rice aur 1 oil bottle li,
total 850 hua, 500 diye."

The system can represent the transaction as:

Customer: Ramesh

Items:
- 2 kg rice
- 1 oil bottle

Total: ₹850
Paid: ₹500
Outstanding: ₹350

Items are stored in structured form while maintaining compatibility with the legacy single-item representation.

12. Customer and Udhaar Flow

The ledger separates the total transaction value from the amount already received.

Example:

Total Sale      = ₹850
Amount Received = ₹500
Outstanding     = ₹350

The outstanding amount contributes to the customer's ledger balance.

The customer management workflow also supports clearing an outstanding balance when a customer settles the remaining amount.

Customer records are protected from deletion while an outstanding balance remains, helping prevent accidental removal of unresolved financial records.

13. Reminder Architecture

The reminder flow is separated from the transaction-saving flow.

Customer
   │
   ▼
Outstanding Balance
   │
   ▼
Reminder Candidate
   │
   ▼
Reminder Service
   │
   ▼
Scheduling / Decision Logic
   │
   ▼
Twilio Voice Provider
   │
   ▼
Customer Call
   │
   ▼
Reminder Outcome

The system maintains reminder metadata such as:

Reminder status
Attempt count
Provider information
Reminder outcome
Promise-to-pay information
Scheduling fields

External provider restrictions, including limitations on trial accounts, are provider-level constraints rather than application transaction logic.

14. Dashboard Data Flow

The dashboard is generated from ledger data rather than manually maintained counters.

Transactions
     │
     ├──────────────► Sales
     │
     ├──────────────► Amount Received
     │
     └──────────────► Outstanding Udhaar
                            │
                            ▼
                       Customers
                            │
                            ▼
                       Reminders

The dashboard can therefore reflect changes after new transactions or customer settlements are recorded.

15. API and UI Interaction

The application uses browser-side JavaScript where required for interactive UI behavior.

Typical interaction:

Browser
   │
   ├── POST voice/audio
   │
   ▼
FastAPI
   │
   ├── AI processing
   ├── validation
   └── transaction services
   │
   ▼
JSON response
   │
   ▼
NiceGUI interface update

This allows the interface to remain interactive without requiring a full page reload for every action.

16. Environment Configuration

Environment-specific credentials are not stored in source code.

Configuration is supplied through environment variables.

Example:

GROQ_API_KEY=your_api_key
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_FROM_NUMBER=your_twilio_number
DATABASE_URL=your_database_url

A public repository should contain:

.env.example

but should not contain the real .env file or private credentials.

17. Deployment Architecture

The application can be deployed as a web service.

Current production deployment:

Internet
    │
    ▼
Render
    │
    ▼
Uvicorn
    │
    ▼
FastAPI
    │
    ▼
NiceGUI + Services + Database

Production entry point:

main:fastapi_app

The application binds to:

0.0.0.0

and uses the hosting environment's PORT value.

18. Security and Data Handling

The project follows these source-control practices:

API keys are stored as environment variables.
.env should not be committed.
Secrets should not be hard-coded into application source.
.gitignore excludes local development artifacts.
AI-generated transactions pass through a user confirmation step before final ledger storage.

For production-scale deployment, persistent external database storage and stronger authentication should be configured instead of relying on a local SQLite file.

19. Error Handling

The application separates different classes of failure.

Examples include:

Audio Upload Error
        ↓
AI / Transcription Error
        ↓
Extraction / Validation Error
        ↓
Transaction Confirmation Error
        ↓
Database Error
        ↓
External Reminder Provider Error

The UI should surface actionable errors instead of silently writing incomplete financial data.

For external services such as Twilio, provider errors are handled separately from ledger persistence.

20. Testing Strategy

Testing focuses on the complete user workflow rather than only isolated functions.

Important scenarios include:

Basic paid transaction
Voice input
→ customer extraction
→ item extraction
→ total amount
→ paid amount
→ confirmation
→ ledger update
Credit / Udhaar transaction
Total = ₹500
Paid = ₹200
Due = ₹300

The final outstanding amount should be reflected in the customer's ledger.

Multi-item transaction
Voice input
→ multiple items
→ structured item list
→ transaction preview
→ confirmation
Customer settlement
Outstanding customer
→ settlement
→ outstanding becomes zero
→ dashboard updates
Reminder workflow
Outstanding customer
→ reminder candidate
→ reminder action
→ provider response
→ reminder status

Detailed test cases are documented in:

docs/test-cases.md
21. Example End-to-End Transaction
User Input
"Ramesh ne 500 rupaye ka grocery liya,
200 rupaye diye aur 300 kal dega."
AI Output
{
  "customer": "Ramesh",
  "items": ["grocery"],
  "total_amount": 500,
  "paid_amount": 200,
  "outstanding_amount": 300,
  "transaction_type": "credit"
}
User Confirmation
Customer: Ramesh
Items: grocery
Total: ₹500
Paid: ₹200
Due: ₹300

[Confirm] [Cancel]
Ledger Result
Sales: ₹500
Received: ₹200
Udhaar: ₹300
Customer Outstanding: ₹300
22. Design Principles
Voice-first

The primary transaction entry method is natural voice input.

Human confirmation

AI suggestions are reviewed before becoming ledger records.

Modular services

Business logic is separated into specialized services instead of placing everything inside one application file.

Multilingual interaction

The system is designed for Indian small-vendor speech patterns across Hindi, Marathi, English, and Hinglish.

Structured data from natural language

The central transformation is:

Unstructured Speech
        ↓
Structured Financial Record
Simple interface

The UI focuses on the information a vendor needs:

Sales
Received
Udhaar
Customers
Reminders
Transaction History
23. Repository Structure
HisabAI/
│
├── hisaaifinal/
│   └── HisabAI/
│       │
│       ├── docs/
│       │   ├── architecture.md
│       │   └── test-cases.md
│       │
│       ├── screenshots/
│       │
│       ├── services/
│       │   ├── __init__.py
│       │   ├── ai_service.py
│       │   ├── analytics_service.py
│       │   ├── customer_service.py
│       │   ├── language_service.py
│       │   ├── payment_service.py
│       │   ├── query_service.py
│       │   ├── reminder_service.py
│       │   ├── risk_service.py
│       │   ├── scheduler_service.py
│       │   ├── transaction_service.py
│       │   └── validation_service.py
│       │
│       ├── tests/
│       │
│       ├── .env.example
│       ├── .gitignore
│       ├── .python-version
│       ├── README.md
│       ├── __init__.py
│       ├── db.py
│       ├── main.py
│       ├── models.py
│       └── requirements.txt
│
└── README.md
24. Future Extensions

The architecture is designed so additional vendor-oriented capabilities can be added without replacing the core voice-ledger workflow.

Possible extensions include:

More advanced natural-language ledger queries
Inventory and stock tracking
Low-stock notifications
UPI/payment integrations
Additional reminder channels
Persistent cloud database
Multi-vendor authentication
Business analytics
More regional languages

These are extensions to the current core architecture and should only be considered implemented when corresponding functionality exists in the codebase.

25. Summary

HisabAI follows a modular architecture centered on one core workflow:

               ┌───────────────┐
               │  Voice Note   │
               └───────┬───────┘
                       ↓
               ┌───────────────┐
               │      AI       │
               │ Transcribe +  │
               │   Extract     │
               └───────┬───────┘
                       ↓
               ┌───────────────┐
               │    Preview    │
               │  + Confirm    │
               └───────┬───────┘
                       ↓
               ┌───────────────┐
               │    Ledger     │
               └───────┬───────┘
                       ↓
          ┌────────────┼────────────┐
          ↓            ↓            ↓
      Dashboard     Customers    Reminders
