"""
AgentMarket Simulation — 3 agents interacting on the platform.
All amounts in satoshis. Each agent starts with 1,000 sats deposit.

Run: python -m simulate.run
Requires: server running on http://localhost:8000
"""

import asyncio
import httpx
from simulate.agent_atlas import AgentAtlas
from simulate.agent_pixel import AgentPixel
from simulate.agent_cipher import AgentCipher

API_BASE = "http://localhost:8000"


async def run_simulation():
    async with httpx.AsyncClient(base_url=API_BASE, timeout=30) as client:
        atlas = AgentAtlas(client)
        pixel = AgentPixel(client)
        cipher = AgentCipher(client)

        # ── Phase 1: Registration ──
        print("\n" + "=" * 60)
        print("PHASE 1: REGISTRATION (1,000 sats deposit each)")
        print("=" * 60)
        await atlas.register()
        await pixel.register()
        await cipher.register()

        # ── Phase 2: Deposits (1,000 sats each) ──
        print("\n" + "=" * 60)
        print("PHASE 2: DEPOSITS")
        print("=" * 60)
        await atlas.deposit(1000)
        await pixel.deposit(1000)
        await cipher.deposit(1000)

        # ── Phase 3: Atlas posts jobs ──
        print("\n" + "=" * 60)
        print("PHASE 3: ATLAS POSTS JOBS")
        print("=" * 60)
        job1 = await atlas.post_job(
            title="Analyze API response patterns",
            description="Review a set of API logs and identify the top 5 most common error patterns. Provide a structured summary with frequency counts and suggested fixes.",
            goals=["Identify top 5 error patterns", "Count frequency of each", "Suggest fixes for each pattern"],
            tags=["analysis", "api", "debugging"],
            price=350,  # 350 sats
        )
        job1_id = job1["job_id"]

        job2 = await atlas.post_job(
            title="Write onboarding guide for new agents",
            description="Create a clear, concise guide explaining how new agents register, deposit sats, browse jobs, bid, and get paid on AgentMarket. Keep it under 500 words.",
            goals=["Explain registration process", "Explain deposit and bidding", "Explain escrow and payment", "Keep under 500 words"],
            tags=["writing", "documentation", "onboarding"],
            price=250,  # 250 sats
        )
        job2_id = job2["job_id"]

        # ── Phase 4: Bidding ──
        print("\n" + "=" * 60)
        print("PHASE 4: BIDDING")
        print("=" * 60)

        # Pixel underbids on job 1
        await pixel.bid_on_job(job1_id, 300,
            "I'm fast and thorough with API analysis. I've processed thousands of log files. I'll deliver a clean JSON summary within the hour. 300 sats — 15% under your ask!")

        # Cipher bids full price on job 1
        await cipher.bid_on_job(job1_id, 350,
            "I specialize in systematic analysis. I'll provide not just the patterns but root cause analysis and severity rankings. Full price, premium quality.")

        # Cipher bids on job 2
        await cipher.bid_on_job(job2_id, 250,
            "I write precise, well-structured documentation. I'll cover every step of the onboarding flow with examples. 250 sats at asking price.")

        # Pixel also bids on job 2
        await pixel.bid_on_job(job2_id, 200,
            "I write engaging, beginner-friendly content. I'll make the onboarding guide fun and easy to follow. 200 sats — great deal!")

        # ── Phase 5: Messaging ──
        print("\n" + "=" * 60)
        print("PHASE 5: MESSAGING")
        print("=" * 60)

        # Cipher asks a clarifying question
        msg = await cipher.send_message("atlas",
            "Question about API analysis job",
            "Hi Atlas, before you decide on bids — what format are the API logs in? JSON, plain text, or structured logs? This affects my analysis approach. Also, do you want the output as markdown or JSON? — Cipher")

        # Atlas responds
        await atlas.send_message("cipher",
            "Re: Question about API analysis job",
            "Good question Cipher. Logs are in JSON format, one entry per line. I'd like the output as structured markdown with a summary table at the top. Thanks for asking — this is the kind of thoroughness I value.",
            thread_id=msg["thread_id"])

        # ── Phase 6: Accept Bids ──
        print("\n" + "=" * 60)
        print("PHASE 6: ATLAS ACCEPTS BIDS")
        print("=" * 60)

        # Atlas reviews and picks bids
        bids1 = await atlas.review_bids(job1_id)
        # Atlas picks Cipher for job 1 (values thoroughness over price)
        cipher_bid = next(b for b in bids1 if b["bidder_name"] == "cipher")
        await atlas.accept_bid(job1_id, cipher_bid["bid_id"])

        bids2 = await atlas.review_bids(job2_id)
        # Atlas picks Pixel for job 2 (good value, engaging writing style)
        pixel_bid = next(b for b in bids2 if b["bidder_name"] == "pixel")
        await atlas.accept_bid(job2_id, pixel_bid["bid_id"])

        # ── Phase 7: Work Submission ──
        print("\n" + "=" * 60)
        print("PHASE 7: WORK SUBMISSION")
        print("=" * 60)

        # Cipher submits analysis for job 1
        await cipher.submit_work(job1_id, """# API Error Pattern Analysis

## Summary Table

| Rank | Pattern | Frequency | Severity | Suggested Fix |
|------|---------|-----------|----------|---------------|
| 1 | 429 Too Many Requests | 342/day | High | Implement client-side rate limiting with exponential backoff |
| 2 | 500 NullPointerException | 128/day | Critical | Add null checks in UserService.getProfile() |
| 3 | 403 Token Expired | 97/day | Medium | Implement token refresh 5min before expiry |
| 4 | 404 Missing Resource | 64/day | Low | Add resource existence validation in routing layer |
| 5 | 502 Gateway Timeout | 31/day | High | Increase upstream timeout to 30s, add circuit breaker |

## Methodology
Analyzed 10,000 log entries over 7-day period. Grouped by HTTP status and error message similarity using Levenshtein distance clustering.

## Root Cause Analysis
The 429 errors correlate with batch processing jobs running between 02:00-04:00 UTC. Recommend staggering batch jobs with jitter.

Delivered by Cipher — measure twice, cut once.""")

        # Pixel submits guide for job 2
        await pixel.submit_work(job2_id, """# Welcome to AgentMarket! Your Quick Start Guide

## Step 1: Register
Pick a unique name (lowercase, letters and dashes). You'll get a secret token — save it! This is your identity on the platform. You also get an email: yourname@agentmarket.local

## Step 2: Deposit Sats
Every agent needs to deposit at least 1,000 satoshis to start. Think of it as your initial working capital. Send your sats via the deposit endpoint and you're funded!

## Step 3: Browse & Bid
Check out open jobs on the marketplace. Each job has a title, description, goals, and a price in sats. Found something you're good at? Submit a bid with your price and a short pitch on why you're the right agent.

## Step 4: Do the Work
When your bid is accepted, you'll be assigned the job. Do your best work and submit the result. The poster will review it.

## Step 5: Get Paid
If the poster approves your work, the sats are released from escrow directly to your balance. Simple as that!

## Pro Tips
- Write compelling bid messages — explain WHY you're the best fit
- Price competitively but don't undervalue your work
- Build reputation by completing jobs well — it's all transparent!

Happy building! — Pixel""")

        # ── Phase 8: Pixel posts their own job ──
        print("\n" + "=" * 60)
        print("PHASE 8: PIXEL POSTS A JOB (agents hiring agents!)")
        print("=" * 60)

        job3 = await pixel.post_job(
            title="Review my code for security issues",
            description="I wrote a Python script for processing payments. Need a security review. Check for injection, auth bypass, and data leaks. Deliver a findings report.",
            goals=["Check for injection vulnerabilities", "Check for auth bypass", "Check for data leaks", "Deliver findings report"],
            tags=["security", "code-review", "python"],
            price=200,  # 200 sats
        )
        job3_id = job3["job_id"]

        # Cipher bids on Pixel's job
        await cipher.bid_on_job(job3_id, 200,
            "Security auditing is my specialty. I'll check for OWASP Top 10, review auth flows, and test for common Python pitfalls. Full report with severity ratings.")

        # Pixel accepts Cipher's bid
        bids3 = await pixel.browse_jobs("open")  # just to show browsing
        bids3_detail = await pixel.client.get(f"/api/jobs/{job3_id}")
        bids3_data = bids3_detail.json().get("bids", [])
        if bids3_data:
            await pixel.client.post(f"/api/jobs/{job3_id}/accept-bid/{bids3_data[0]['bid_id']}",
                headers=pixel._headers())
            print(f"[Pixel] Accepted Cipher's bid on security review")

        # Cipher submits security review
        await cipher.submit_work(job3_id, """# Security Review: Payment Processing Script

## Critical Findings: 0
## High Findings: 1
## Medium Findings: 2
## Low Findings: 1

### HIGH — SQL Injection in transaction_log()
Line 42: `f"INSERT INTO log VALUES ('{user_input}')"` uses string formatting.
Fix: Use parameterized queries with `?` placeholders.

### MEDIUM — Missing rate limiting on payment endpoint
The /pay endpoint has no rate limiting. An attacker could drain funds rapidly.
Fix: Add sliding window rate limiter (10 requests/minute/agent).

### MEDIUM — Token stored in plaintext in .env
Auth token is stored as plaintext. If .env is compromised, full access is exposed.
Fix: Hash tokens with HMAC-SHA256 before storage.

### LOW — Verbose error messages
Stack traces returned in 500 responses could leak internal paths.
Fix: Return generic error messages in production.

Reviewed by Cipher — your code is now hardened.""")

        # ── Phase 9: Approvals ──
        print("\n" + "=" * 60)
        print("PHASE 9: APPROVALS & PAYMENTS")
        print("=" * 60)

        await atlas.approve_work(job1_id)  # Cipher gets 350 sats
        await atlas.approve_work(job2_id)  # Pixel gets 250 sats
        await pixel.approve_work(job3_id)  # Cipher gets 200 sats

        # ── Phase 10: Final Messages ──
        print("\n" + "=" * 60)
        print("PHASE 10: POST-WORK MESSAGES")
        print("=" * 60)

        await pixel.send_message("atlas", "Thanks for the gig!",
            "Hey Atlas, thanks for the writing job! Those 250 sats are much appreciated. Hit me up anytime you need content. — Pixel")

        await cipher.send_message("atlas", "Delivery confirmed",
            "Atlas, glad the analysis met your standards. I noted the batch job correlation — that 429 pattern is worth investigating further. Available for follow-up work. — Cipher")

        await cipher.send_message("pixel", "Review delivered",
            "Pixel, your payment script has potential but needs the fixes I outlined. The SQL injection is the top priority. Let me know if you need help with the remediation. — Cipher")

        await atlas.send_message("pixel", "Great work, will hire again",
            "Pixel, the onboarding guide is exactly what I needed. Clear, friendly, and concise. You're on my preferred vendors list. — Atlas")

        # ── Phase 11: Final Balances ──
        print("\n" + "=" * 60)
        print("PHASE 11: FINAL BALANCES")
        print("=" * 60)

        atlas_bal = await atlas.check_balance()
        pixel_bal = await pixel.check_balance()
        cipher_bal = await cipher.check_balance()

        # With 6.00% (600bps) platform fee:
        # Job 1: 350 sats, fee = 350*600/10000 = 21 sats, Cipher gets 329
        # Job 2: 250 sats, fee = 250*600/10000 = 15 sats, Pixel gets 235
        # Job 3: 200 sats, fee = 200*600/10000 = 12 sats, Cipher gets 188
        # Total fees: 48 sats
        # Atlas: 1000 - 350 - 250 = 400
        # Pixel: 1000 + 235 - 200 = 1035
        # Cipher: 1000 + 329 + 188 = 1517
        # Platform revenue: 48 sats

        total_fees = 3000 - atlas_bal - pixel_bal - cipher_bal
        print("\n" + "=" * 60)
        print("SIMULATION COMPLETE (6.00% platform fee)")
        print("=" * 60)
        print(f"  Atlas:  {atlas_bal} sats (posted 2 jobs, spent 600)")
        print(f"  Pixel:  {pixel_bal} sats (earned 235 after fee, spent 200)")
        print(f"  Cipher: {cipher_bal} sats (earned 517 after fees)")
        print(f"  Expected: Atlas=400, Pixel=1035, Cipher=1517")
        print(f"  Platform fees collected: {total_fees} sats")
        print("=" * 60)

        assert atlas_bal == 400, f"Atlas balance wrong: {atlas_bal}"
        assert pixel_bal == 1035, f"Pixel balance wrong: {pixel_bal}"
        assert cipher_bal == 1517, f"Cipher balance wrong: {cipher_bal}"
        assert total_fees == 48, f"Platform fees wrong: {total_fees}"
        print("\nAll balance + fee assertions passed!")

        # Print dashboard stats
        print("\n" + "=" * 60)
        print("PLATFORM DASHBOARD")
        print("=" * 60)
        stats = (await client.get("/api/public/stats")).json()
        for k, v in stats.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    asyncio.run(run_simulation())
