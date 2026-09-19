# HisabAI — Voice Ledger

### Speak. Track. Collect.

HisabAI is an AI-powered voice ledger designed for small businesses and local vendors. It allows vendors to record sales and credit transactions naturally using **Hindi, Marathi, English, and Hinglish voice commands** instead of manually maintaining a ledger.

## Problem

Small vendors often manage customer credit (udhaar), payments, and daily sales using notebooks or memory. This can lead to:

* Missed or incorrect transactions
* Difficulty tracking outstanding payments
* Time-consuming manual bookkeeping
* Forgotten payment follow-ups
* Language barriers with traditional accounting software

## Solution

HisabAI converts a simple voice note into a structured transaction.

For example:

> "Ramesh ne 500 rupaye ka maal liya, 200 diye."

HisabAI understands the transaction and generates:

* **Customer:** Ramesh
* **Total:** ₹500
* **Paid:** ₹200
* **Udhaar:** ₹300

The vendor can review the AI-generated transaction before saving it to the ledger.

## Key Features

### Voice-Based Ledger

Record transactions using natural speech instead of typing.

### Multilingual Support

Designed to understand:

* Hindi
* Marathi
* English
* Hinglish

### AI Transaction Extraction

AI converts spoken transactions into structured financial information.

### AI Confirmation

Transactions are shown as a preview before being added to the ledger, helping prevent incorrect entries.

### Dashboard

Track important business information such as:

* Total Sales
* Amount Received
* Outstanding Udhaar
* Customers

### Customer Management

View customer-wise transaction history and outstanding amounts.

### Payment Reminders

Identify customers with pending payments and send reminders.

### AI-Assisted Calling

The system is designed to support automated payment reminder calls for pending amounts.

### Business Queries

Vendors can ask questions about their business data using natural language.

## Technology Stack

### Frontend

* NiceGUI
* HTML/CSS

### Backend

* Python
* FastAPI
* SQLModel

### AI

* Groq API
* Whisper for speech-to-text
* LLM-based transaction extraction

### Database

* SQLite / SQLModel

### Deployment

* Render

## How It Works

```text
Vendor speaks
      ↓
Voice recording
      ↓
Speech-to-Text
      ↓
AI Transaction Extraction
      ↓
Transaction Preview
      ↓
Vendor Confirmation
      ↓
Ledger Database
      ↓
Dashboard / Customers / Reminders
```

## Example

### Voice Input

```text
"Ramesh ne 500 rupaye ka maal liya, 200 diye."
```

### AI Output

```text
Customer: Ramesh
Transaction Type: Sale
Total Amount: ₹500
Paid Amount: ₹200
Outstanding: ₹300
```

After confirmation, the transaction is stored in the ledger.

## Application Modules

### Home — Voice Ledger

The main interface where vendors can record transactions through voice.

### Dashboard

Provides an overview of sales, payments, customers, and outstanding credit.

### Customers

Displays customer information and their transaction history.

### Reminders

Helps identify pending payments and manage payment follow-ups.

## 📸 Screenshots

Screenshots of the working application are available in the `/screenshots` folder.

Included screens:

* Home / Voice Ledger
* AI Transaction Preview
* Dashboard
* Customers
* Reminders

## Demo

A demonstration video showing the working HisabAI application is included with the project submission.

The demo demonstrates the complete flow:

**Voice → AI Understanding → Transaction Preview → Confirmation → Ledger**

## Project Structure

```text
HisabAI/
│
├── main.py
├── requirements.txt
├── README.md
├── .env
│
├── services/
│   ├── language_service.py
│   ├── payment_service.py
│   └── ...
│
├── screenshots/
│   ├── home-voice-ledger.png
│   ├── ai-transaction-preview.png
│   ├── dashboard.png
│   ├── customers.png
│   └── reminders.png
│
└── docs/
    ├── architecture.md
    └── test-cases.md
```

## Innovation

HisabAI focuses on making digital bookkeeping accessible to small vendors who may be more comfortable speaking than typing.

Instead of forcing the vendor to learn a complicated accounting application, HisabAI allows them to communicate with their ledger naturally through voice.

### Voice → Ledger → Intelligence → Action

The goal is not only to record transactions, but also to help vendors understand their outstanding payments and take action on them.

## Safety & Reliability

HisabAI uses an AI confirmation step before writing a transaction to the ledger.

This provides an additional verification layer between:

**AI interpretation → Actual financial record**

The vendor remains in control of the final transaction.

## Future Scope

Future versions can include:

* Inventory and low-stock tracking
* UPI payment integration
* Payment links
* Automated WhatsApp reminders
* Multilingual AI voice calls
* Advanced business analytics
* Daily/weekly business summaries
* Customer payment behavior insights
* Offline-first functionality for low-connectivity areas

## Project

**Project Name:** HisabAI — Voice Ledger

**Category:** AI / FinTech / Small Business Technology

**Built With:** Python, FastAPI, NiceGUI, SQLModel, Groq AI, Whisper

---

### HisabAI

**Speak. Track. Collect.**
