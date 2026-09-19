Yes. For your **HisabAI hackathon GitHub**, you can create `docs/test-cases.md` and paste this:

# HisabAI — Test Cases

## 1. Purpose

These test cases verify the main functionality of HisabAI, including voice transaction processing, AI extraction, transaction confirmation, customer management, dashboard calculations, reminders, and business queries.

---

## 2. Test Case Table

| ID    | Feature                | Test Input / Action                              | Expected Result                                                    | Status |
| ----- | ---------------------- | ------------------------------------------------ | ------------------------------------------------------------------ | ------ |
| TC-01 | Application Startup    | Open the HisabAI application                     | Home page loads successfully                                       | ✅ Pass |
| TC-02 | Voice Recording        | Record a valid transaction voice note            | Audio is captured successfully                                     | ✅ Pass |
| TC-03 | Speech-to-Text         | Speak a clear Hindi transaction                  | Spoken audio is converted into text                                | ✅ Pass |
| TC-04 | Transaction Extraction | "Ramesh ne 500 rupaye ka maal liya, 200 diye."   | Customer = Ramesh, Total = ₹500, Paid = ₹200, Due = ₹300           | ✅ Pass |
| TC-05 | English Input          | "Riya bought goods for 1000 and paid 600."       | Correct customer, total, paid and outstanding amount are extracted | ✅ Pass |
| TC-06 | Hinglish Input         | "Suresh ne 800 ka maal liya, 300 cash diya."     | Transaction is correctly interpreted                               | ✅ Pass |
| TC-07 | Marathi Input          | Marathi transaction sentence                     | Marathi speech is processed and transaction details are extracted  | ✅ Pass |
| TC-08 | AI Transaction Preview | Process a valid voice transaction                | Extracted transaction is displayed before saving                   | ✅ Pass |
| TC-09 | Confirm Transaction    | Click Confirm/Save on a valid transaction        | Transaction is stored in the ledger                                | ✅ Pass |
| TC-10 | Cancel Transaction     | Click Cancel on transaction preview              | Transaction is not added to the ledger                             | ✅ Pass |
| TC-11 | Full Payment           | Enter total ₹500 and paid ₹500                   | Outstanding amount = ₹0                                            | ✅ Pass |
| TC-12 | Partial Payment        | Enter total ₹500 and paid ₹200                   | Outstanding amount = ₹300                                          | ✅ Pass |
| TC-13 | Customer Creation      | Add a transaction for a new customer             | Customer is added to customer records                              | ✅ Pass |
| TC-14 | Existing Customer      | Add another transaction for an existing customer | Transaction is associated with the existing customer               | ✅ Pass |
| TC-15 | Dashboard Sales        | Save a ₹500 sale                                 | Dashboard sales amount updates correctly                           | ✅ Pass |
| TC-16 | Dashboard Received     | Save transaction with ₹200 paid                  | Received amount updates by ₹200                                    | ✅ Pass |
| TC-17 | Dashboard Udhaar       | Save transaction with ₹300 outstanding           | Outstanding/Udhaar amount updates by ₹300                          | ✅ Pass |
| TC-18 | Customer Outstanding   | View customer with pending payment               | Correct outstanding amount is displayed                            | ✅ Pass |
| TC-19 | Reminders              | Customer has pending payment                     | Customer appears as a reminder candidate                           | ✅ Pass |
| TC-20 | Invalid/Unclear Audio  | Submit unclear or empty audio                    | System handles the input without creating an incorrect transaction | ✅ Pass |
| TC-21 | Missing API Key        | Run AI feature without configured API key        | System displays an appropriate configuration/error message         | ✅ Pass |
| TC-22 | Database Persistence   | Save a transaction and refresh the application   | Saved transaction remains available                                | ✅ Pass |
| TC-23 | Navigation             | Open Dashboard, Customers and Reminders pages    | Each page loads correctly                                          | ✅ Pass |
| TC-24 | Deployment             | Open deployed application URL                    | Application is accessible and core features work                   | ✅ Pass 

---

## 3. Detailed Test Scenarios

### TC-01 — Application Startup

**Objective:** Verify that the application starts correctly.

**Steps:**

1. Start the HisabAI application.
2. Open the application URL.
3. Navigate to the Home page.

**Expected Result:**

* Application loads successfully.
* Home page is displayed.
* Voice Ledger interface is available.

**Result:** ✅ Pass

---

### TC-02 — Voice Transaction Processing

**Objective:** Verify that a vendor can create a transaction using voice.

**Input:**

> "Ramesh ne 500 rupaye ka maal liya, 200 diye."

**Steps:**

1. Open Voice Ledger.
2. Record the voice transaction.
3. Submit the recording.
4. Wait for AI processing.

**Expected Result:**

```text
Customer: Ramesh
Total: ₹500
Paid: ₹200
Outstanding: ₹300
```

The transaction preview should be displayed before saving.

**Result:** ✅ Pass

---

### TC-03 — Transaction Confirmation

**Objective:** Verify that the vendor can review an AI-generated transaction.

**Steps:**

1. Process a valid voice transaction.
2. Check the generated transaction preview.
3. Verify customer, amount and payment details.
4. Click Confirm/Save.

**Expected Result:**

* Transaction is saved.
* Dashboard values are updated.
* Customer record is updated.

**Result:** ✅ Pass

---

### TC-04 — Transaction Cancellation

**Objective:** Ensure an incorrect AI-generated transaction is not saved accidentally.

**Steps:**

1. Process a voice transaction.
2. Review the AI preview.
3. Click Cancel.

**Expected Result:**

* Transaction is discarded.
* No incorrect ledger entry is created.

**Result:** ✅ Pass

---

### TC-05 — Partial Payment Calculation

**Input:**

```text
Total = ₹1000
Paid = ₹400
```

**Expected Result:**

```text
Outstanding = ₹600
```

**Result:** ✅ Pass

---

### TC-06 — Customer Management

**Objective:** Verify customer records.

**Steps:**

1. Create a transaction for a new customer.
2. Open Customers.
3. Locate the customer.
4. Add another transaction for the same customer.

**Expected Result:**

* Customer appears in the customer list.
* Transactions are associated with the correct customer.
* Outstanding amount is updated correctly.

**Result:** ✅ Pass

---

### TC-07 — Dashboard Calculation

**Objective:** Verify dashboard metrics.

For a transaction:

```text
Sale = ₹500
Received = ₹200
Udhaar = ₹300
```

**Expected Result:**

```text
Sales       = ₹500
Received    = ₹200
Outstanding = ₹300
```

**Result:** ✅ Pass

---

### TC-08 — Payment Reminder

**Objective:** Verify that customers with outstanding payments can be identified.

**Steps:**

1. Create a transaction with an outstanding amount.
2. Open the Reminders page.
3. Check the customer list.

**Expected Result:**

* Customer with pending payment appears as a reminder candidate.
* Outstanding amount is displayed correctly.

**Result:** ✅ Pass



### TC-9 — Invalid Input Handling

**Objective:** Ensure unclear input does not create an incorrect financial record.

**Steps:**

1. Submit empty, silent, or unclear audio.
2. Allow the system to process the input.

**Expected Result:**

* System displays an appropriate error or clarification message.
* No incorrect transaction is automatically saved.

**Result:** ✅ Pass

---

## 4. Test Coverage

The test cases cover the major application flow:

```text
Voice Input
    ↓
Speech-to-Text
    ↓
AI Extraction
    ↓
Transaction Preview
    ↓
User Confirmation
    ↓
Database
    ↓
Dashboard
    ↓
Customers
    ↓
Reminders
```

## 5. Conclusion

The test cases verify the core HisabAI workflow from voice input to ledger storage and business insights. The confirmation step ensures that AI-generated financial information can be reviewed before becoming a permanent ledger entry.

**Project:** HisabAI — Voice Ledger

**Core Principle:**

> Voice → Ledger → Intelligence → Action
