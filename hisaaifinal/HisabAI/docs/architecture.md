HisabAI Architecture

Problem Statement

Orchestrate September 2026 — PS 01: Voice-Note Ledger for Small Vendors.

High-Level Architecture

                         ┌──────────────────────────┐
                         │       Shopkeeper          │
                         │ Hindi / Marathi /         │
                         │ English / Hinglish        │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │      NiceGUI Web UI      │
                         │ MediaRecorder + HTML/JS  │
                         └────────────┬─────────────┘
                                      │ audio/webm
                                      ▼
                         ┌──────────────────────────┐
                         │       FastAPI API        │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │       AI Service         │
                         │ transcription +          │
                         │ structured extraction    │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │   AI Transaction Preview │
                         │ customer / items / money │
                         └────────────┬─────────────┘
                                      │ user confirms
                                      ▼
                         ┌──────────────────────────┐
                         │       SQLModel DB         │
                         │ Customer / Transaction / │
                         │ Reminder / Payment       │
                         └───────┬─────────┬────────┘
                                 │         │
                      ┌──────────┘         └────────────┐
                      ▼                                 ▼
             ┌─────────────────┐               ┌─────────────────┐
             │    Dashboard    │               │    Reminders    │
             │ sales/received/ │               │ candidates +    │
             │ outstanding     │               │ scheduling      │
             └─────────────────┘               └────────┬────────┘
                                                        │
                                                        ▼
                                               ┌─────────────────┐
                                               │     Twilio      │
                                               │ voice provider  │
                                               └─────────────────┘

Core Transaction Flow

Voice
  ↓
Audio upload
  ↓
AI processing
  ↓
Structured transaction
  ↓
User confirmation
  ↓
Save Customer + Transaction
  ↓
Outstanding = Total - Paid
  ↓
Dashboard / Customer / Reminder views

Settlement Flow

Customer has outstanding udhaar
             ↓
Customers → Update
             ↓
Clear outstanding balance
             ↓
Remaining outstanding amount marked collected
             ↓
Dashboard Received increases
Dashboard Outstanding decreases to ₹0
             ↓
Customer may be deleted once no active outstanding remains

Components

UI

NiceGUI hosts the interface. Browser JavaScript handles microphone recording, API requests, rendering, pagination and theme controls.

API

FastAPI handles the voice-processing endpoint, transaction confirmation, dashboard aggregation, customer management, reminders and Twilio callbacks.

AI

services/ai_service.py processes recorded audio and returns structured transaction information. services/language_service.py supports language/number normalization.

Persistence

models.py contains SQLModel entities. db.py creates the database engine/session and performs SQLite schema initialization.

Reminder System

services/reminder_service.py provides reminder candidates, settings, scheduling, execution, history, Twilio voice generation and provider-status handling.

Entity Relationships

Customer 1 ────────< Transaction
Customer 1 ────────< Reminder
Customer 1 ────────< Payment

Deployment

GitHub
  ↓
Render build
  ↓
Python dependencies
  ↓
Uvicorn
  ↓
FastAPI + NiceGUI
  ↓
Public HTTPS URL

Render command:

uvicorn main:fastapi_app --host 0.0.0.0 --port $PORT

Security

Secrets are environment variables. .env and database files are excluded from GitHub by .gitignore.

PS01 Gap Check

PS01 explicitly calls for real-time text query filters and low-stock reminders. These are not represented as completed features in the current codebase and must be added and tested before being claimed in the final submission. 
