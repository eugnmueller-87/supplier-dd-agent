# Hades — SpendLens Integration Handover

**Agent:** Hades (Supplier Due Diligence Agent)
**Repo:** https://github.com/eugnmueller-87/supplier-dd-agent
**Version:** 0.1.0
**Date:** 2026-05-16
**Author:** Eugen Mueller

---

## What Hades Does

Hades is a standalone FastAPI + LangGraph agent that runs autonomous due diligence on any supplier. Give it a company name and get back a structured risk report in under 2 minutes — no manual research needed.

It is designed to be called by SpendLens at two points in the vendor lifecycle:

1. **New vendor onboarding** — before a vendor is approved, SpendLens calls `POST /investigate` to gate the decision
2. **Periodic recheck** — for existing vendors, SpendLens calls with `mode: "recheck"` to refresh the risk profile

Hades shares the same **Upstash Redis** instance as Hermes. It reads Hermes intelligence pre-flight and writes new suppliers to the Hermes watchlist post-report, so Hermes crawlers start covering them automatically.

---

## API Reference

### Base URL

```
https://<hades-railway-url>   # set after Railway deploy
http://localhost:8000         # local development
```

### `POST /investigate`

Run a full due diligence investigation on a supplier.

**Request**

```json
{
  "company": "Robert Bosch GmbH",
  "category": "Electronics",
  "country": "DE",
  "mode": "full"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `company` | string | yes | Legal company name |
| `category` | string | yes | SpendLens category (see category mapping below) |
| `country` | string | no | ISO-2 country code, default `"DE"` |
| `mode` | string | no | `"full"` (default) or `"recheck"` |

**Response**

```json
{
  "company": "Robert Bosch GmbH",
  "hermes_registered": true,
  "risk_scores": {
    "overall_risk_score": 4.7,
    "risk_level": "Medium",
    "recommendation": "Conditional Approval",
    "scores": {
      "sanctions":           { "score": 4, "rationale": "..." },
      "registry":            { "score": 2, "rationale": "..." },
      "news_sentiment":      { "score": 2, "rationale": "..." },
      "lksg_csddd":          { "score": 7, "rationale": "..." },
      "esg_labour":          { "score": 6, "rationale": "..." },
      "hermes_intelligence": { "score": 3, "rationale": "..." }
    },
    "top_risk_factors": ["...", "...", "..."],
    "positive_signals": ["...", "..."]
  },
  "report": {
    "report_date": "2026-05-16",
    "company": "Robert Bosch GmbH",
    "category": "Electronics",
    "country": "DE",
    "overall_risk_score": 4.7,
    "risk_level": "Medium",
    "recommendation": "Conditional Approval",
    "executive_summary": "...",
    "company_overview": {
      "legal_name": "Robert Bosch GmbH",
      "hrb": "HRB14000",
      "amtsgericht": "Amtsgericht Stuttgart",
      "legal_address": "Robert-Bosch-Platz 1, 70839 Gerlingen",
      "company_status": "active",
      "jurisdiction": "DE"
    },
    "sanctions_status": {
      "is_sanctioned": false,
      "priority_hit": false,
      "datasets_matched": [],
      "sources_checked": ["OFAC SDN", "UN SC Consolidated List"],
      "eu_fsf_manual_required": true,
      "manual_review_required": false,
      "summary": "..."
    },
    "news_sentiment": {
      "sentiment": "neutral",
      "total_articles": 0,
      "negative_count": 0,
      "high_severity_count": 0,
      "notable_headlines": [],
      "summary": "..."
    },
    "lksg_csddd_assessment": {
      "compliance_signal": "red_flag",
      "flagged_count": 12,
      "bafa_findings": "...",
      "ncp_complaints": "...",
      "ngo_reports": "...",
      "conclusion": "Red Flag",
      "summary": "..."
    },
    "esg_labour": {
      "esg_rating": "high_risk",
      "negative_count": 4,
      "positive_count": 2,
      "key_findings": ["...", "..."],
      "summary": "..."
    },
    "hermes_intelligence": {
      "tracked_by_hermes": false,
      "signal_count": 0,
      "risk_flags": 0,
      "monitoring_status": "Added to monitoring today",
      "top_signals": [],
      "summary": "..."
    },
    "risk_score_breakdown": {
      "sanctions":           { "score": 4, "weight": "25%", "rationale": "..." },
      "registry":            { "score": 2, "weight": "15%", "rationale": "..." },
      "news_sentiment":      { "score": 2, "weight": "15%", "rationale": "..." },
      "lksg_csddd":          { "score": 7, "weight": "20%", "rationale": "..." },
      "esg_labour":          { "score": 6, "weight": "15%", "rationale": "..." },
      "hermes_intelligence": { "score": 3, "weight": "10%", "rationale": "..." }
    },
    "required_next_steps": ["...", "..."]
  }
}
```

**Key fields for SpendLens to act on**

| Field | Where | Use |
|---|---|---|
| `report.recommendation` | root | `Approve` / `Conditional Approval` / `Block` — gate the onboarding decision |
| `report.overall_risk_score` | root | 1–10 float — store on vendor record for sorting/filtering |
| `report.risk_level` | root | `Low` / `Medium` / `High` / `Critical` — display badge |
| `report.required_next_steps` | root | Surface to the procurement manager as action items |
| `report.sanctions_status.manual_review_required` | nested | Flag for compliance team if `true` |
| `report.lksg_csddd_assessment.compliance_signal` | nested | `no_findings` / `needs_monitoring` / `red_flag` |
| `hermes_registered` | root | `true` = Hades added this vendor to Hermes watchlist |

### `GET /health`

```json
{ "status": "ok", "agent": "hades", "version": "0.1.0" }
```

Use this for Railway health checks and pre-call readiness checks from SpendLens.

---

## Risk Score Weights

| Dimension | Weight | Source |
|---|---|---|
| Sanctions | 25% | OFAC SDN + UN SC Consolidated List (free XML, no key) |
| LkSG / CSDDD | 20% | BAFA, OECD NCP, ECCHR/NGO signals via Serper |
| Company Registry | 15% | NorthData + Unternehmensregister via Serper |
| News Sentiment | 15% | newsapi.ai (Event Registry) — last 90 days |
| ESG & Labour | 15% | EcoVadis, ILO, Transparency Intl, Violation Tracker |
| Hermes Intelligence | 10% | Upstash Redis — shared with Hermes |

**Risk level thresholds:** Low = 1.0–3.9 · Medium = 4.0–6.4 · High = 6.5–7.9 · Critical = 8.0–10.0

**Hard rules (always applied by Claude):**
- `is_sanctioned = true` AND `priority_hit = true` → sanctions score ≥ 9, recommendation = Block
- `compliance_signal = red_flag` → lksg_csddd score ≥ 7
- `company_status = dissolved/insolvent` → registry score ≥ 7

---

## SpendLens Integration Pattern

### Recommended call point

Call Hades from the SpendLens vendor onboarding flow, after the vendor record is created but before approval is granted:

```python
import httpx

HADES_URL = "https://<hades-railway-url>"

def run_due_diligence(vendor_name: str, category: str, country: str) -> dict:
    r = httpx.post(
        f"{HADES_URL}/investigate",
        json={"company": vendor_name, "category": category, "country": country},
        timeout=180,  # Hades takes 60-120s — set timeout accordingly
    )
    r.raise_for_status()
    return r.json()

result = run_due_diligence("Robert Bosch GmbH", "Electronics", "DE")

recommendation = result["report"]["recommendation"]
risk_score     = result["report"]["overall_risk_score"]
risk_level     = result["report"]["risk_level"]
next_steps     = result["report"]["required_next_steps"]
```

### Suggested SpendLens vendor record fields to store

```python
vendor.hades_report_date     = result["report"]["report_date"]
vendor.hades_risk_score      = result["report"]["overall_risk_score"]
vendor.hades_risk_level      = result["report"]["risk_level"]
vendor.hades_recommendation  = result["report"]["recommendation"]
vendor.hades_sanctions_clear = not result["report"]["sanctions_status"]["manual_review_required"]
vendor.hades_lksg_signal     = result["report"]["lksg_csddd_assessment"]["compliance_signal"]
vendor.hades_next_steps      = result["report"]["required_next_steps"]
vendor.hermes_registered     = result["hermes_registered"]
```

### Category mapping

Hades accepts the SpendLens category strings directly. The Hermes client maps them internally:

| SpendLens category | Hermes category |
|---|---|
| Cloud & Compute | Cloud & Infrastructure |
| AI/ML APIs & Data | AI Foundation Labs |
| IT Software & SaaS | SaaS & Dev Tools |
| Hardware & Equipment | Semiconductors & Chips |
| Professional Services | Professional Services |
| Recruitment & HR | HR & Talent |
| Marketing & Campaigns | Marketing Tech |
| Facilities & Office | Facilities |
| Travel & Expenses | Travel & Logistics |

---

## Hermes Read/Write Flow

Hades shares the same Upstash Redis instance as Hermes. The integration is automatic — no extra configuration needed beyond the shared credentials.

```
SpendLens calls POST /investigate
         |
  hermes_preflight
         |-- Redis GET hermes:supplier:<slug>
         |-- if tracked + signal_count > 10: skip NewsAPI (uses Hermes data instead)
         |
  [6 parallel research nodes]
         |
  synthesis + report_generator (Claude Sonnet 4.6)
         |
  hermes_register
         |-- Redis SET hermes:watchlist:<slug>  (idempotent — safe to call multiple times)
         |-- Hermes crawlers will start covering this vendor on next cycle
```

**What this means for SpendLens:** Any vendor investigated by Hades is automatically added to Hermes monitoring. On subsequent investigations (`mode: "recheck"`), Hades will find Hermes data pre-loaded and incorporate it into the risk score.

---

## Environment Variables Required

Add these to the SpendLens deployment that calls Hades — they are only needed on the **Hades** service, not SpendLens itself:

```env
ANTHROPIC_API_KEY=sk-ant-...          # Claude Sonnet 4.6
SERPER_API_KEY=...                    # Serper.dev web search
NEWSAPI_KEY=...                       # newsapi.ai (Event Registry) — UUID format
UPSTASH_REDIS_REST_URL=https://cool-pelican-110055.upstash.io
UPSTASH_REDIS_REST_TOKEN=...          # same token as Hermes
```

> The `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` are the **same credentials** used by Hermes. Do not create a new Redis database — Hades must point to the existing one.

---

## Deployment

Hades is configured for Railway via `railway.toml`:

```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "uvicorn main:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/health"
healthcheckTimeout = 30
```

**Steps:**
1. Connect `eugnmueller-87/supplier-dd-agent` repo in Railway
2. Add the 5 environment variables above in the Variables tab
3. Railway auto-deploys on push to `master`
4. Health check at `/health` confirms the service is up

**Important:** Hades validates all 5 env vars at startup and refuses to start if any are missing. Check Railway logs if the deploy fails.

---

## Performance Notes

- **Response time:** 60–120 seconds per investigation (6 parallel web searches + 2 Claude calls)
- **Set `timeout=180`** in any SpendLens HTTP client calling Hades
- **OFAC/UN XML:** Downloaded once on first request, cached in memory for 24 hours — subsequent calls do not re-download
- **Hermes pre-flight:** If a vendor is already tracked in Hermes with >10 signals, NewsAPI is skipped to save tokens
- **newsapi.ai free tier:** 2,000 tokens total — use sparingly in development; consider upgrading before production

---

## Known Limitations

| Limitation | Impact | Workaround |
|---|---|---|
| EU Financial Sanctions File (EU FSF) blocks automated access | EU sanctions not auto-checked | Every report flags `eu_fsf_manual_required: true` — compliance team checks manually at webgate.ec.europa.eu/fsd |
| OpenSanctions API requires paid subscription | Not used | Replaced with free OFAC + UN SC XML |
| newsapi.ai free tier: 2,000 tokens | Limited news coverage in dev | Upgrade to paid tier for production; Hermes coverage offsets this for known vendors |
| No async execution | One investigation blocks a worker | Acceptable for low-volume onboarding; add background task queue (Celery/ARQ) for high volume |
| No persistent report storage | Reports not stored — caller must save | SpendLens should persist the full `report` dict on the vendor record |

---

## File Structure

```
supplier-dd-agent/          # Hades repo
+-- main.py                 # FastAPI entry point, env validation, dotenv load
+-- api/routes.py           # POST /investigate, GET /health
+-- agent/
|   +-- state.py            # DDState TypedDict — full pipeline state schema
|   +-- graph.py            # LangGraph StateGraph — wires all nodes
|   +-- prompts.py          # SYNTHESIS_PROMPT, REPORT_PROMPT (Claude)
|   +-- nodes/
|       +-- _utils.py       # Shared parse_json_response() helper
|       +-- hermes_preflight.py   # Pre-flight: read Hermes Redis
|       +-- web_research.py       # 4 Serper queries, negative flagging
|       +-- news_sentiment.py     # newsapi.ai, last 90 days, EN+DE
|       +-- sanctions_check.py    # OFAC SDN + UN SC, 24h XML cache
|       +-- registry_lookup.py    # NorthData + Unternehmensregister
|       +-- lksg_signals.py       # BAFA, NCP, ECCHR/NGO signals
|       +-- esg_signals.py        # EcoVadis, ILO, TI, Violation Tracker
|       +-- synthesis.py          # Claude: score 6 risk dimensions
|       +-- report_generator.py   # Claude: full structured DD report
|       +-- hermes_register.py    # Post-report: write to Hermes watchlist
+-- integrations/
|   +-- hermes_client.py          # Upstash Redis client (shared with Hermes)
|   +-- serper_client.py          # Shared Serper search function
+-- demo/run_demo.py              # 4-scenario live demo script
```

---

## Contact

**Built by:** Eugen Mueller
**GitHub:** https://github.com/eugnmueller-87/supplier-dd-agent
**Questions:** Open an issue on the repo or reach out directly
