# EVENZA — Product Requirements Document

## Original Problem
Build EVENZA: a premium, dark-themed (Navy #0B152E / Yellow #FFC928 / White) K–12 & college **opportunity discovery + event-management** platform for Maharashtra, India. USP: "Where opportunities find you." Dual ecosystems (Participant & Organiser), Virtual vs Physical bifurcation, AI discovery assistant, dynamic GST checkout, referrals, notifications.

## Architecture
- **Backend**: FastAPI + MongoDB (Motor), all routes under `/api`. Single `server.py`.
- **Frontend**: React 19 + react-router 7 + Tailwind + framer-motion + shadcn/ui.
- **Auth**: JWT email/password + Emergent-managed Google login (unified `users` collection; bearer token accepts JWT OR Google session_token).
- **AI**: Emergent Universal LLM key → Claude Sonnet 4.6 via `emergentintegrations` (rule-based fallback).
- **Payments**: Razorpay — **MOCKED** (keys not set). Dynamic tax engine computes fee + platform charge + CGST/SGST/IGST; total == sum of components.

## User Personas
1. **Participant** (student/parent): discover, save, register, pay, track, achievements, referrals.
2. **Organiser** (school/club): host, edit, cancel events, manage registrations, send reminders, configure tax.
3. **Owner/Admin**: diyakini1529@gmail.com (organiser role).

## Implemented (2026-06)
- Landing: hero, personalised category tiles (12), AI chat, recommended, dual ecosystems, Why EVENZA, footer.
- Role selection screen + Auth (JWT + Google) with participant profile capture (age→age_group, class, location, interests).
- Discover: 26 seeded events, functional filters (category, sub, location, age, mode, fee, free-only) + search.
- 4 required Bal Bharati events incl. Market Day with visible **Commerce Students** eligibility. 24 distinct cover images.
- Event detail page; Save + Register.
- Checkout: dynamic Payment Summary (fee, platform charge, CGST/SGST or IGST, total), MOCK Razorpay, success + transaction record.
- Participant dashboard: stats + tabs (Recommended, Saved, Registrations, Upcoming, Achievements, Referral EVENZA123). Floating AI launcher (bottom-right).
- Organiser dashboard: Overview stats, Host Event (full form + expanded categories + image presets), Your Events (view/edit/cancel-with-confirm/registrations), Registrations table (name, age, payment mode, status, reminder column), Tax & Fees config.
- Notifications centre with unread badge. Referral tracking. Location selector (16 Maharashtra cities).
- Testing: backend 21/21 passing; frontend flows validated.

## Backlog
- P1: Real Razorpay integration (needs RAZORPAY_KEY_ID/SECRET from user).
- P1: Swap in official EVENZA logo (done — logo uploaded & wired).
- P2: Certificates generation, refunds workflow, organiser analytics charts, email notifications (Resend), ambassador/campaign referral tiers.
- P2: Split server.py into routers; explicit CORS origins for prod.

## Next Tasks
- Provide Razorpay keys to enable live payments.
- Optional: certificates, refunds, richer analytics.
