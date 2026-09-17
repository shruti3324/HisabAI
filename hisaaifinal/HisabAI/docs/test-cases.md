# HisabAI Evaluation Test Cases

These test cases are designed to verify the complete Voice → AI → Confirmation → Ledger workflow.

---

## Test Case 1 — Fully Paid Sale

### Input

> "Ramesh ne 500 rupaye ka maal liya aur 500 diye."

### Expected

```text
Customer: Ramesh
Total: ₹500
Paid: ₹500
Outstanding: ₹0
Type: Sale
```

### Expected behavior

The application should identify the transaction as fully paid.

---

## Test Case 2 — Partial Payment

### Input

> "Ramesh ne 1500 rupaye ka maal liya, 500 diye."

### Expected

```text
Customer: Ramesh
Total: ₹1500
Paid: ₹500
Outstanding: ₹1000
Type: Credit Sale
```

---

## Test Case 3 — Complete Udhaar

### Input

> "Suresh ne 800 ka saman udhaar liya."

### Expected

```text
Customer: Suresh
Total: ₹800
Paid: ₹0
Outstanding: ₹800
Type: Credit Sale
```

---

## Test Case 4 — Hindi Input

### Input

> "Riya ne do hazaar rupaye ka samaan liya, ek hazaar diye."

### Expected

```text
Customer: Riya
Total: ₹2000
Paid: ₹1000
Outstanding: ₹1000
```

---

## Test Case 5 — Marathi Input

### Input

> Marathi transaction describing a customer purchasing goods on credit.

### Expected behavior

The system should:

1. Transcribe the speech.
2. Preserve the customer name.
3. Identify the transaction amount.
4. Identify the paid amount if present.
5. Calculate outstanding amount.
6. Show the extracted result for confirmation.

---

## Test Case 6 — Hinglish Input

### Input

> "Amit ne 1200 ka maal liya, 400 cash diye."

### Expected

```text
Customer: Amit
Total: ₹1200
Paid: ₹400
Outstanding: ₹800
```

---

## Test Case 7 — Multiple Transactions

Record transactions for:

```text
Ramesh
Suresh
Riya
Amit
```

### Expected behavior

Each customer should be represented correctly in the ledger.

---

## Test Case 8 — Partial Repayment

Existing outstanding:

```text
Customer: Ramesh
Outstanding: ₹1000
```

Record:

> "Ramesh ne 600 rupaye diye."

### Expected

Outstanding should become:

```text
₹400
```

---

## Test Case 9 — Full Repayment

Existing outstanding:

```text
₹400
```

Record:

> "Ramesh ne 400 rupaye diye."

### Expected

Outstanding:

```text
₹0
```

---

## Test Case 10 — Customer Search

Search for:

```text
Ramesh
```

### Expected

The customer page should show the corresponding customer information and transaction history.

---

## Test Case 11 — Business Query

### Input

> "Who owes me more than 500?"

### Expected

The application should return customers whose ledger-derived outstanding balance is greater than ₹500.

The query should use supported database operations rather than arbitrary model-generated SQL.

---

## Test Case 12 — Human Confirmation

Record:

> "Ramesh ne 1500 rupaye ka maal liya, 500 diye."

### Expected behavior

The system should display the proposed transaction before saving it.

The transaction should not be committed until the user confirms.

---

## Test Case 13 — Incorrect AI Extraction

If the AI proposes an incorrect amount or customer:

### Expected behavior

The user should be able to review/correct the proposed information before saving.

Incorrect AI output should not silently become a ledger record.

---

## Test Case 14 — Invalid/Unclear Audio

Provide unclear or incomplete speech.

### Expected behavior

The application should display an error or request clarification rather than creating an unreliable financial transaction.

---

## Test Case 15 — Dashboard Verification

After creating several transactions, verify:

* Today's sales
* Total sales
* Amount received
* Outstanding amount
* Customer count
* Recent transactions

All values should correspond to the ledger.

---

## Test Case 16 — Reminder

Create an eligible outstanding customer.

Trigger the reminder functionality.

### Expected behavior

The system should:

1. Identify the outstanding customer.
2. Create/send the reminder through the configured provider.
3. Record reminder status.
4. Display the reminder result.

---

# Evaluation Checklist

| Area                 | Verified |
| -------------------- | -------- |
| Voice input          | Y        |
| Speech transcription | Y        |
| Hindi                | Y        |
| Marathi              | Y        |
| English              | Y        |
| Hinglish             | Y        |
| AI extraction        | Y        |
| Human confirmation   | Y        |
| Ledger save          | Y        |
| Partial payment      | Y        |
| Full payment         | Y        |
| Outstanding balance  | Y        |
| Customer management  | Y        |
| Dashboard            | Y        |
| Business query       | Y        |
| Reminder             | Y        |
| Error handling       | Y        |
