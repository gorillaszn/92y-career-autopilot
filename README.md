# 🎖️ 92Y Career Auto-Pilot

AI-powered resume engine that translates U.S. Army Unit Supply Specialist (92Y) experience into ATS-optimized civilian career packages.

## Features

- **Mirror Protocol** - Extracts keywords from job descriptions and forces the resume to match them
- **Ghostwriter Logic** - Infers skills based on rank (E-4 through E-8) when user data is thin
- **No-Repeat Rule** - Core Competencies and Professional Experience use completely different language
- **4-Industry Targeting** - Adjusts tone for Corporate, Defense Contractor, Federal (USAJOBS), or Tech/SaaS
- **Seniority Calibration** - Detects if the role is Buyer-level vs Director-level and adjusts verbs accordingly
- **3 Input Modes** - Upload resume, paste NCOER bullets, or generate from scratch using rank alone
- **Keyword Confirmation** - Extracted JD keywords are shown to the user for editing before generation
- **Career Package** - Generates Resume + Cover Letter + Interview Prep as separate LLM calls
- **Real .docx Export** - Downloads are formatted Word documents with proper headers, bullets, and styling

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deployment (Streamlit Community Cloud)

1. Push this repo to GitHub (public)
2. Go to [share.streamlit.io](https://share.streamlit.io) and connect the repo
3. Set `app.py` as the main file
4. Optionally add `GOOGLE_API_KEY` in Settings > Secrets

## Requirements

- Python 3.9+
- Google Gemini API key (free tier works)
