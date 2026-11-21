# 🎂 AI-Powered Bakery Order & Advance-Booking Backend

A mobile-first conversational commerce backend built with **Python**, **Google Gemini API (`gemini-3.5-flash-lite`)**, **Pydantic**, **PostgreSQL (Supabase)**, and **Telegram Bot API**, deployed 24/7 on **Render**.

## 🏗️ System Architecture & Key Features
- **Bilingual NLU Pipeline:** Uses `gemini-3.5-flash-lite` with Pydantic structured outputs to parse natural English and Telugu-English ("Tenglish") cake orders into strict JSON schemas.
- **Deterministic Pricing & Guardrails:** Separates probabilistic LLM extraction from deterministic Python price math so the AI can never hallucinate prices or advance rules.
- **2-Tier Customer Trust Engine:** Standard orders allow friction-free *Pay at Pickup*; high-risk custom/2kg+ orders trigger a ₹150 token advance for first-time buyers and automatically waive it once the customer completes their first order (`is_trusted` in PostgreSQL).
- **Zero-Laptop Mobile Admin RBAC:** Whitelisted owner Telegram ID (`OWNER_CHAT_ID`) receives instant kitchen tickets upon confirmation and can query active orders via `/orders`.
- **Cloud-Native Deployment:** Hosted on Render with automated GitHub CI/CD, encrypted environment variables, and a lightweight HTTP health-check server.

## 🚀 Next Upgrades (Roadmap)
- [ ] **Step 4A:** Integrate Razorpay Test Payment Links + HMAC-SHA256 webhook verification for automated UPI token confirmation.
- [ ] **Step 4C:** Add Meta WhatsApp Cloud API adapter alongside Telegram using the same `database.py` and AI parsing core.
- [ ] **Pilot:** Run a 2-week free trial with a local bakery and record real conversion metrics for resume.
