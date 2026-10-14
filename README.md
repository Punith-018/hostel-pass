# Hostel Pass

A lightweight, zero-build hostel pass coordination system for out-passes and guest passes across residents, wardens, and gate staff.

---

## 1. Problem Chosen and Why

In a student hostel, two things are arranged over WhatsApp and phone calls:
1. **Residents going out past curfew** (late return or nights away).
2. **Guests visiting a resident.**

This causes exactly the problems in the brief:

| Brief says | What it looks like here |
|---|---|
| Misunderstandings about who is staying where | Nobody can say who is out tonight |
| Staff acting on outdated information | Guard lets a guest in on a message from last week |
| Confusion about responsibility and approvals | "The warden said OK" — nobody can show when, or for what |
| Time wasted on follow-ups | Residents chase the warden; guard calls the warden for every guest |

### Why this flow?
These are the only flows where one person decides (warden) and a different person (the guard) acts on that decision later. That gap is where all four pain points in the brief happen. Room allocation changes rarely; facility booking and complaints are convenience, not coordination between residents and staff. We solve these two flows and nothing else.

---

## 2. How It Works (Pass Lifecycle)

```
submit ─► PENDING ─► APPROVED ─► (end time passes) ─► shown as EXPIRED
             │           │
             │           └─► CANCELLED (by resident, before end)
             ├─► REJECTED (by warden, with optional note)
             ├─► CANCELLED (by resident)
             └─► (start time passes, no decision) ─► shown as LAPSED
```

- **Only APPROVED and inside its time window gives permission.** Everything else gives none.
- `EXPIRED` and `LAPSED` are worked out from the clock when reading, not stored. So a stale approval can never show as valid, even if nothing is running in the background.
- Approved passes cannot be edited. Cancel and raise a new one.

---

## 3. Setup and Running

```bash
# 1. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate   # On Windows: .\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create tables + demo users + sample passes
python -m app.seed

# 4. Start the application
uvicorn app.main:app --reload
```

Open:
- App: `http://localhost:8000`
- API Docs: `http://localhost:8000/docs`

---

## 4. Demo Logins & 2-Minute Demo Script

### Demo Logins
- `warden` / `warden123` — Warden
- `guard` / `guard123` — Main Gate Guard
- `r101a` / `pass123` — Rahul Verma (Room 101)
- `r101b` / `pass123` — Aman Gupta (Room 101)
- `r102a` / `pass123` — Priya Nair (Room 102)
- `r102b` / `pass123` — Sneha Patel (Room 102)
- `r103a` / `pass123` — Rohan Mehta (Room 103)

### 2-Minute Demo Script
1. **Resident raises a guest pass:**
   - Log in as `r101a` / `pass123` at `http://localhost:8000`.
   - On the Resident screen, select **Guest pass**. Set date to today, time from now until 2 hours later (before 8 pm).
   - Enter guest name "Vikram Verma", phone `9876543210`, relation "Parent".
   - Submit $\to$ shows in "My Passes" with amber `PENDING` badge.
2. **Warden approves the pass:**
   - Log out, log in as `warden` / `warden123`.
   - On the **Pending** tab, the pass appears at the top.
   - Enter an optional note (e.g. "Verified over call") and click green **Approve**.
   - The pass is approved in one click and removed from pending.
3. **Guard sees live permission on gate board:**
   - Log out, log in as `guard` / `guard123`.
   - On the **Gate Board**, Vikram Verma is listed with a prominent green **ALLOWED NOW** badge.
   - Note: Guard sees host name and room, but cannot see sensitive details like guest phone numbers, destinations, or reasons.
4. **Resident cancellation:**
   - Log in back as `r101a`. Under "My Passes", click **Cancel Pass** (confirm prompt).
   - The pass immediately changes to grey `CANCELLED` and disappears from the guard board.

---

## 5. Running Tests

Run the test suite with:
```bash
pytest -v
```

All tests run against a fresh in-memory SQLite database per test.

---

## 6. Assumptions

- One hostel, one warden, one or more guards.
- Residents and staff are pre-loaded (seed script). No sign-up.
- Every user has a phone with a browser.
- "Out" is **declared**, not verified. The board says "declared out", never "present".
- All times are in IST (Asia/Kolkata).

---

## 7. Not Built (and Why)

| Not built | Why |
|---|---|
| Room allocation and room changes | Separate problem; rooms come from seed data |
| Overnight guests | Day-visitor policy |
| Gate check-in / check-out log | System knows who is allowed, not who arrived. First future ticket |
| Deputy warden | Single-warden assumption |
| SMS / WhatsApp / push notifications | In-app is enough for a demo |
| OTP login | Seeded passwords are enough for a demo |
| Facilities, complaints, mess, fees | Not the coordination problem we chose |
