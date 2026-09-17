# HisabAI Architecture

## Overview

HisabAI is a voice-first bookkeeping system where artificial intelligence converts natural-language voice input into structured financial transactions.

The architecture separates AI interpretation from financial persistence.

## System Flow

```text
                    USER
                     │
                     ▼
             ┌───────────────┐
             │ Voice Recording│
             └───────┬───────┘
                     │
                     ▼
             ┌───────────────┐
             │ Groq Whisper  │
             │ Speech-to-Text│
             └───────┬───────┘
                     │
                     ▼
             ┌───────────────┐
             │   Language    │
             │ Normalization │
             └───────┬───────┘
                     │
                     ▼
             ┌───────────────┐
             │ AI Extraction │
             │ Transaction   │
             │ Information  │
             └───────┬───────┘
                     │
                     ▼
             ┌───────────────┐
             │   Validation  │
             │ + Confirmation│
             └───────┬───────┘
                     │
                     ▼
             ┌───────────────┐
             │   SQLModel    │
             │    Database   │
             └───────┬───────┘
                     │
          ┌──────────┼───────────┐
          ▼          ▼           ▼
      Dashboard   Customers   Reminders
```

## AI Layer

The AI layer performs the primary interpretation work.

### Step 1 — Speech Recognition

The recorded audio is transcribed using Groq Whisper.

### Step 2 — Language Processing

The transcript is normalized to handle:

* Hindi
* Marathi
* English
* Hinglish
* Code-switched speech
* Spoken numbers and currency expressions

### Step 3 — Transaction Extraction

The language model extracts structured information such as:

```json
{
  "customer": "Ramesh",
  "total_amount": 1500,
  "paid_amount": 500,
  "transaction_type": "sale"
}
```

### Step 4 — Human Confirmation

The extracted transaction is shown to the user.

The AI does not silently write the transaction to the ledger.

### Step 5 — Persistence

After confirmation, the backend stores the transaction using SQLModel.

## Database Layer

The database contains information for:

* Customers
* Transactions
* Reminders
* Ledger history

Outstanding balances are derived from transaction data.

## Query Layer

Business questions are mapped to supported database operations.

The application does not allow the language model to generate arbitrary SQL and execute it directly.

## Reminder Layer

The reminder service handles scheduled reminders and communication-provider integration.

## Frontend

NiceGUI provides the operating interface:

* Dashboard
* Voice input
* Customer pages
* Reminder pages
* Transaction confirmation

## Deployment

The application runs as a FastAPI application with NiceGUI mounted on top.

Render provides the public deployment environment.

```text
Internet
   │
   ▼
Render
   │
   ▼
FastAPI
   │
   ├── NiceGUI
   ├── AI Services
   ├── Ledger Services
   └── Reminder Services
          │
          ▼
       Database
```
