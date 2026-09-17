HisabAI — Evaluator Test Cases

The official challenge asks participants to test realistic and complex sample data and document the cases in the GitHub README. 

ID

Scenario

Test input/action

Expected result

TC01

English paid sale

"Ramesh bought goods for 500 and paid 500."

Total ₹500, paid ₹500, outstanding ₹0, paid status

TC02

Hindi udhaar

"Ramesh ne 500 rupaye ka maal liya, 200 diye."

Total ₹500, paid ₹200, outstanding ₹300

TC03

Marathi input

Speak a Marathi transaction containing customer, items and amounts

AI preview contains structured fields

TC04

Hinglish input

Speak a Hinglish transaction

AI accepts mixed-language input and returns structured data

TC05

Multiple items

Enter Paneer, Tomato, Rice

All items appear as a list in the transaction

TC06

Manual entry

Enter customer, multiple items, total and paid

Transaction saved and visible in Recent Transactions

TC07

AI confirmation

Record a voice note and inspect preview before saving

User sees customer/items/total/paid/outstanding before ledger write

TC08

Customer reuse

Save another transaction for an existing normalized name

Existing customer is reused

TC09

Dashboard

Save a transaction, then open Dashboard

Sales/Received/Outstanding/Customers update

TC10

Recent Activity

Open Dashboard after saving transactions

Transaction rows are visible with item list

TC11

Customer update

Edit customer name/phone/reminder settings

Changes persist

TC12

Clear outstanding

Customer has ₹300 outstanding; tick clear outstanding and save

Remaining ₹300 is settled; Received increases by ₹300; Outstanding becomes ₹0

TC13

Delete after settlement

Delete customer after all active outstanding is cleared

Customer deletion succeeds and settled history remains available in Dashboard

TC14

Delete protection

Try to delete customer with active outstanding transaction

API blocks deletion with a useful message

TC15

Reminder candidate

Customer has eligible outstanding balance and consent/settings

Customer appears in reminder candidates

TC16

Reminder call action

Click Send Reminder

Backend endpoint is called and result is shown in UI

TC17

Twilio trial restriction

Attempt outbound call under a restricted Twilio trial account

UI reports provider restriction instead of false success

TC18

Reminder scheduling

Schedule a future reminder

Reminder is stored as scheduled and scheduler can process it

TC19

Voice confirmation

Confirm the AI transaction

Transaction is persisted and Home ledger refreshes

TC20

Microphone denied

Deny browser mic permission

UI shows microphone-permission error

TC21

Health

GET /api/health

JSON reports service health and configured-provider flags

TC22

Invalid transaction

Enter total <= 0 or paid > total

UI rejects invalid financial input

TC23

Reverse transaction

Reverse an existing transaction

Status becomes reversed and it stops contributing to active ledger totals

Recommended Evidence

Capture screenshots/screen recordings of:

Home voice recording

AI transaction preview

Confirm & Save

Multiple-item transaction in Recent Transactions

Dashboard metrics and Recent Activity

Customer update and clear-outstanding control

Dashboard after settlement

Customer deletion after settlement

Reminder candidate and reminder result

GitHub repository structure

Render live deployment

PS01-Specific Tests Still Needed

The official PS01 also names:

real-time text query filters

low-stock reminders

Those features are not evidenced in the current codebase, so add dedicated tests only after implementing them. 
