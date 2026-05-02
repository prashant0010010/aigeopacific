# AiGeoPacific — AI Citation Analyser

> **Find out exactly why ChatGPT, Perplexity, and Google AI Overviews are not citing your pages — and get a prioritised fix plan.**

Built with Python + Streamlit. Delivers a client-ready PDF audit report in under 15 seconds.

---

## What It Does

AiGeoPacific audits a webpage against 8 GEO (Generative Engine Optimization) signals,
compares it against top-ranking competitors, and produces a downloadable PDF report
with a ranked fix plan — without requiring any API keys.

**Core output:** A Citation Quality Score (CQS) from 0–100 that predicts how likely
AI systems are to cite your page, with per-metric explanations and action steps.

---

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/aigeopacific.git
cd aigeopacific

# 2. Create a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Add API keys (optional — heuristic fallback works without them)
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit .streamlit/secrets.toml and add your keys

# 5. Run
streamlit run app.py
```

Open `http://localhost:8501` in your browser.

---

## API Keys (Both Optional)

| Key | Service | Get it at | Fallback if missing |
|-----|---------|-----------|-------------------|
| `GEMINI_API_KEY` | Google Gemini 1.5 Flash | [aistudio.google.com](https://aistudio.google.com) | Heuristic enrichment (free, no API) |
| `PERPLEXITY_API_KEY` | Perplexity sonar-small | [perplexity.ai/settings/api](https://perplexity.ai/settings/api) | DuckDuckGo AI Chat |

Add keys to `.streamlit/secrets.toml` (created from the `.example` file above).
The tool runs fully without either key.

---

## The 8 Metrics

| Metric | Weight | What It Checks |
|--------|--------|---------------|
| BLUF Score | 15% | Core answer in the first paragraph |
| Entity Density | 12% | Named entities, dates, specific statistics |
| Link Authority | 15% | Outbound links to .gov/.edu/major publications |
| Formatting Readiness | 12% | H2/H3 structure, lists, scannable content |
| Schema Presence | 10% | JSON-LD, FAQ schema, Open Graph metadata |
| Claim Support | 12% | Claims backed by nearby inline citations |
| Readability | 10% | Flesch approximation, average sentence length |
| Search Presence | 14% | Reality check — is the URL visible in search? |

**CQS = weighted sum of all 8 scores (0–100)**
Score ≥ 70 = Strong AI citation candidate.

---

## Features

### Phase 1 (complete)
- Single URL audit against 8 GEO metrics
- Competitor comparison (top 3 from search results)
- Reality validation via DuckDuckGo search
- Confidence level system (High / Medium / Low)
- PDF report as primary output (ReportLab)
- Optional Gemini AI enrichment (1 batch call per audit)
- Heuristic fallback when no API key is provided

### Phase 2 (complete)
- PDF download wired to `st.download_button()` — the actual deliverable
- Enrichment routing: Gemini → heuristic fallback, automatic
- HTML sanitisation on all scraped content before rendering
- Light / dark mode toggle
- TTL cache for search results (prevents rate-limiting in demos)
- Concurrent competitor fetching (`ThreadPoolExecutor`, 3 workers)
- Local audit history saved to `~/.aigeopacific/audits/`
- Keyword prompt visibility testing (up to 5 prompts)
- AI citation detection via Perplexity API + DuckDuckGo AI fallback
- Before/after score delta comparison (re-audit tracking)
- White-label PDF branding (firm name, accent colour, logo)
- Sidebar audit history panel with compare and delete

---

## Project Structure

```
aigeopacific/
├── app.py                      ← Streamlit entry point (UI only)
├── requirements.txt
├── .streamlit/
│   └── secrets.toml.example    ← Copy to secrets.toml, add your keys
├── assets/
│   ├── fonts/                  ← Syne, DM Sans, DM Mono (optional)
│   └── client_logos/           ← White-label logos (gitignored)
├── core/
│   ├── models.py               ← All Pydantic data models
│   ├── fetcher.py              ← HTML fetch + JS-gate detection
│   ├── scorer.py               ← 8-metric scoring + CQS
│   ├── competitor.py           ← Concurrent competitor analysis
│   ├── audit_runner.py         ← Full pipeline orchestrator
│   ├── confidence.py           ← Confidence level calculation
│   ├── cache.py                ← TTL cache (1 hour)
│   ├── storage.py              ← Local JSON audit history
│   └── delta.py                ← Score comparison between audits
├── services/
│   ├── search_service.py       ← DuckDuckGo search + caching
│   ├── gemini_service.py       ← Gemini enrichment
│   ├── heuristic_service.py    ← Zero-cost fallback enrichment
│   └── citation_service.py     ← AI citation detection
├── reports/
│   ├── theme.py                ← PDF colours and fonts
│   ├── components.py           ← PDF building blocks
│   └── pdf_builder.py          ← Full PDF assembly
└── ui/
    ├── styles.py               ← Streamlit dark/light theme CSS
    ├── components.py           ← Reusable Streamlit widgets
    ├── results_view.py         ← Audit results dashboard
    └── history_view.py         ← Audit history sidebar
```

---

## PDF Report Sections

The generated PDF contains up to 10 sections (conditional sections only appear when relevant data exists):

1. Cover — CQS badge, URL, date, client logo (if white-label)
2. Progress Since Last Audit *(only on re-audits)*
3. Executive Summary — business impact + quick wins
4. AI Citations Detected *(only when citations are found)*
5. Visibility Score — CQS gauge + search presence
6. Prompt Visibility Analysis *(only when keyword prompts tested)*
7. Competitor Comparison — side-by-side table + gap insights
8. Metric Breakdown — 8 scored metrics with explainability
9. Priority Fix Plan — High / Medium / Long-Term actions
10. Appendix — methodology + variance disclaimer

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | Streamlit |
| PDF | ReportLab |
| Search | ddgs (DuckDuckGo, free) |
| AI Enrichment | Google Gemini 1.5 Flash (free tier) |
| Citation Detection | Perplexity sonar-small-online |
| Data models | Pydantic v2 |
| Concurrency | `concurrent.futures.ThreadPoolExecutor` |
| Storage | Local JSON (`~/.aigeopacific/audits/`) |

---

## Roadmap

| Phase | Status | Goal |
|-------|--------|------|
| Phase 1 — MVP | ✅ Complete | 8-metric audit, competitor comparison, PDF output |
| Phase 2 — Polish | ✅ Complete | PDF wiring, citation detection, history, white-label |
| Phase 3 — SaaS | 🔜 Planned | Auth, Stripe, Supabase, hosted URL, scheduler |

---


---

*Built by Prashant — [AiGeoPacific](https://aigeopacific.com)*
