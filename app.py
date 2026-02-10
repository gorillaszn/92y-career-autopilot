import streamlit as st
import google.generativeai as genai
import pypdf
import docx
from docx import Document as DocxDocument
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
import io
import re
import json
import time


# ============================================================
# 1. PAGE CONFIG & SESSION STATE
# ============================================================

st.set_page_config(page_title="92Y Career Auto-Pilot", page_icon="ðŸŽ–ï¸", layout="wide")

STATE_DEFAULTS = {
    "model": None,
    "keywords": None,
    "keywords_confirmed": False,
    "resume_md": None,
    "cover_letter_md": None,
    "interview_md": None,
    "generation_complete": False,
}
for k, v in STATE_DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ============================================================
# 2. MODEL INITIALIZATION (cached per session)
# ============================================================

def init_model(api_key: str):
    """Find a working Gemini model. Tries flash first, then pro."""
    genai.configure(api_key=api_key)
    try:
        for m in genai.list_models():
            if "flash" in m.name:
                return genai.GenerativeModel(m.name)
        for m in genai.list_models():
            if "pro" in m.name:
                return genai.GenerativeModel(m.name)
    except Exception:
        pass
    return genai.GenerativeModel("gemini-1.5-flash")


# ============================================================
# 3. FILE READER
# ============================================================

def read_file(uploaded_file) -> str:
    """Extract text from PDF or DOCX. Raises on failure."""
    name = uploaded_file.name.lower()
    if name.endswith(".pdf"):
        reader = pypdf.PdfReader(uploaded_file)
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages).strip()
        if not text:
            raise ValueError("PDF appears to be scanned/image-only. No extractable text found.")
        return text
    elif name.endswith(".docx"):
        doc = docx.Document(uploaded_file)
        text = "\n".join([p.text for p in doc.paragraphs]).strip()
        if not text:
            raise ValueError("DOCX file appears empty.")
        return text
    raise ValueError(f"Unsupported file type: {uploaded_file.name}")


# ============================================================
# 4. LLM CALL WRAPPER (with retry)
# ============================================================

def call_model(model, prompt: str, retries: int = 2) -> str:
    """Call Gemini with retry logic. Strips markdown fences from JSON responses."""
    last_err = None
    for attempt in range(retries + 1):
        try:
            response = model.generate_content(prompt)
            text = response.text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
            return text
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise last_err


# ============================================================
# 5. KNOWLEDGE BASE
# ============================================================

TRANSLATION_MAP = {
    "Property Book": "Capital Asset Portfolio ($15M+)",
    "Hand Receipt": "Custodial Asset Transfer Protocol",
    "GCSS-Army": "SAP ERP Systems",
    "FLIPL": "Forensic Financial Audit",
    "PLL": "Preventive Maintenance Logistics Program",
    "CIF": "Central Inventory & Distribution Facility",
    "CSDP": "Command Supply Discipline Program / Internal Compliance Audit",
    "PBUSE": "Automated Asset Tracking Systems",
    "NCOER": "Performance Evaluation / Annual Review",
    "TA-50": "Individual Equipment Accountability Program",
    "SSA": "Supply Support Activity / Regional Distribution Hub",
    "UBL": "Unit Basic Load / Critical Stock Reserve",
    "Class I": "Subsistence & Perishable Inventory",
    "Class II": "Administrative & General Supplies",
    "Class IV": "Construction & Barrier Materials",
    "Class IX": "Repair Parts & Supply Chain Maintenance",
    "S4 Shop": "Logistics Operations Center",
    "Motor Pool": "Fleet Maintenance Facility",
    "Battalion": "Regional Business Unit",
    "Brigade": "Divisional Headquarters",
    "Company Commander": "Operations Director",
}

GHOSTWRITER = {
    "E-4": [
        "Data Accuracy & Record Integrity",
        "Technical Execution of Standard Operating Procedures",
        "Inventory Control & Cycle Count Operations",
        "ERP Data Entry & Transaction Processing",
    ],
    "E-5": [
        "Team Leadership (10-20 personnel)",
        "Training Program Development",
        "Risk Assessment & Mitigation",
        "Budget Oversight ($2M-$5M)",
        "Customer/Stakeholder Liaison",
    ],
    "E-6": [
        "Team Leadership (20+ personnel)",
        "Training Program Development & Execution",
        "Operational Risk Management",
        "Budget Administration ($5M-$10M)",
        "Cross-Functional Stakeholder Management",
        "Process Improvement Initiatives",
        "Customer Service & Internal Liaison",
    ],
    "E-7": [
        "Strategic Planning & Organizational Oversight",
        "Audit & Compliance Program Management",
        "Policy Development & Implementation",
        "Budget Authority ($10M-$15M+)",
        "Senior Stakeholder Advisory",
        "Workforce Development Strategy",
    ],
    "E-8": [
        "Enterprise-Level Strategic Operations",
        "Inspector General-Level Audit Oversight",
        "Organizational Policy Architecture",
        "Executive Budget Authority ($15M+)",
        "C-Suite Advisory & Cross-Org Coordination",
    ],
}

INDUSTRY_TONE = {
    "Corporate (General)": (
        "Use business-neutral corporate language. Emphasize ROI, cost savings, efficiency, "
        "and operational excellence. Avoid military jargon entirely. "
        "If the role is Entry/Mid-level (Buyer, Specialist, Coordinator), use OPERATIONAL verbs: "
        "'Executed,' 'Processed,' 'Maintained,' 'Resolved.' "
        "If the role is Senior (Director, VP), use STRATEGIC verbs: 'Directed,' 'Spearheaded,' 'Optimized.'"
    ),
    "Defense Contractor": (
        "Use defense/aerospace industry language. Reference security clearances, ITAR, DFARS, "
        "government contracts, and controlled inventory. Emphasize Warfighter Readiness, "
        "Production Speed, Mission Assurance, and Accelerated Procurement per 2026 Executive Order priorities. "
        "Military familiarity is expected but translate MOS-specific jargon."
    ),
    "Federal (USAJOBS)": (
        "Use federal resume conventions. Be VERBOSE and THOROUGH. Include '40 Hours/Week' for each position. "
        "Use KSA-style detail. Match OPM qualification standards language. "
        "Include supervisor name/phone placeholders. This resume should be 3-5 pages, not 1-2."
    ),
    "Tech / SaaS": (
        "Use tech industry language. Emphasize data-driven decisions, automation, scalability, "
        "agile methodology, cross-functional collaboration, and customer success. "
        "Frame supply chain as 'Operations Management.' Keep it modern and concise."
    ),
}


# ============================================================
# 6. PROMPT BUILDERS
# ============================================================

def _project_header(industry):
    """Dynamic project section header based on target industry."""
    headers = {
        "Defense Contractor": "KEY MILITARY PROJECTS",
        "Corporate (General)": "KEY STRATEGIC INITIATIVES",
        "Federal (USAJOBS)": "RELEVANT PROJECT EXPERIENCE",
        "Tech / SaaS": "MAJOR OPERATIONS PROJECTS",
    }
    return headers.get(industry, "KEY PROJECTS")

def _context_block(rank, years, industry, target_title, keywords, user_data):
    rank_code = rank.split(" ")[0]
    ghost = GHOSTWRITER.get(rank_code, GHOSTWRITER["E-5"])
    trans = "\n".join(f"  - {k} -> {v}" for k, v in TRANSLATION_MAP.items())
    gh = "\n".join(f"  - {s}" for s in ghost)
    kw = "\n".join(f"  {i+1}. {k}" for i, k in enumerate(keywords))

    return f"""
CANDIDATE PROFILE:
  Rank: {rank}
  Years of Service: {years}
  Raw Experience Data:
  ---
  {user_data[:4000]}
  ---

TARGET POSITION:
  Title: {target_title}
  Industry: {industry}
  Industry Tone: {INDUSTRY_TONE.get(industry, INDUSTRY_TONE["Corporate (General)"])}

CONFIRMED JD KEYWORDS TO MIRROR (address ALL of these):
{kw}

MILITARY-TO-CIVILIAN TRANSLATIONS:
{trans}

GHOSTWRITER INFERRED SKILLS FOR {rank_code} (use if candidate data is thin or missing a JD requirement):
{gh}
"""


def prompt_keywords(job_desc):
    return f"""You are an expert ATS analyst.

Extract the 10-15 most important requirements, skills, and keywords from this job description.
Include BOTH hard skills AND soft skills (like Customer Service, Communication, Analytical Skills).
Prioritize skills that appear multiple times or are listed under "Required" / "Must Have."

Return ONLY a JSON array of strings. No preamble, no markdown fences, no explanation.
Order from most critical to least.

Example: ["Supply Chain Management", "SAP ERP", "Customer Service", "Vendor Negotiation"]

JOB DESCRIPTION:
{job_desc}"""


def prompt_resume(rank, years, industry, target_title, keywords, user_data):
    ctx = _context_block(rank, years, industry, target_title, keywords, user_data)
    return f"""You are a Career Architect for U.S. Army 92Y veterans.

{ctx}

RESUME RULES:

1. THE NO-REPEAT PROTOCOL:
   - CORE COMPETENCIES: Short keyword phrases with brief context.
     Example: "Vendor Negotiation: Managed $5M contracts across 15 suppliers."
   - PROFESSIONAL EXPERIENCE: Detailed STAR-method bullets with different wording.
     Example: "Negotiated with 15 external vendors during a supply chain disruption, reducing costs by 20%."
   - The same skill may appear in both sections, but the LANGUAGE must be completely different.

2. SENIORITY CALIBRATION:
   - If the target role is Entry/Mid-level (Buyer, Specialist, Coordinator, Analyst):
     Use operational verbs: Executed, Processed, Maintained, Resolved, Reconciled.
     Do NOT use: Orchestrated, Visionary, Spearheaded, Strategic Strategy.
   - If the target role is Senior (Director, VP, Head of):
     Use strategic verbs: Directed, Engineered, Optimized, Led.

3. HIDDEN REQUIREMENT DETECTION:
   - Scan the JD for soft skills (Customer Service, Communication, Analytical).
   - If the candidate data does not mention them, use Ghostwriter logic to generate a bullet
     based on standard E-6 duties (e.g., "Liaison between vendors and internal units" for Customer Service).

4. Every bullet in Professional Experience must tie to at least one JD keyword.
   Quantify everything (dollars, percentages, personnel counts, timelines).
   Civilianize ALL military terms using the translation map.

5. If User Data is EMPTY or very thin, generate a "Top 10% Performer" resume from scratch
   based on Rank doctrine. Assume excellence: 100% accountability, zero loss, top ratings.

OUTPUT FORMAT (start immediately, no preamble, no "Here is the resume"):

# [Candidate Name]
### **{target_title}**
**[City, State]** | **[Phone]** | **[Email]** | **[LinkedIn URL]**

## PROFESSIONAL SUMMARY
[3 sentences. Power statement: Rank Authority + top 3 JD keywords + Degree/Clearance.]

## CORE COMPETENCIES
* **[JD Keyword 1]:** [8-15 word context]
* **[JD Keyword 2]:** [context]
* **[JD Keyword 3]:** [context]
* **[JD Keyword 4]:** [context]
* **[JD Keyword 5]:** [context]
* **[Soft Skill from JD]:** [context]

## {_project_header(industry)}
* **[Project Name]:** [Action + quantified result matching a JD need]
* **[Project Name]:** [Action + quantified result matching a JD need]

## PROFESSIONAL EXPERIENCE
**[Civilianized Job Title]** (Former {rank}) | **U.S. Army**
*[Start Date] - [End Date]*
* [STAR bullet 1: Deep dive into top JD requirement. Different wording than Core Competencies.]
* [STAR bullet 2: Different JD requirement.]
* [STAR bullet 3: Leadership/mentorship with metrics.]
* [STAR bullet 4: Audit, compliance, or cost-savings metric.]
* [STAR bullet 5: Process improvement or customer service.]

## EDUCATION & CERTIFICATIONS
* [Degree] | [Institution] | [Year]
* [Clearance Level]
"""


def prompt_cover_letter(rank, years, industry, target_title, keywords, user_data):
    ctx = _context_block(rank, years, industry, target_title, keywords, user_data)
    return f"""You are a Career Architect writing a cover letter for a 92Y veteran.

{ctx}

RULES:
- 3 paragraphs: Hook (who you are + why this role), Body (2-3 JD keywords matched to experience), Close (call to action).
- If there is an employment gap (e.g., 2022-Present), frame it as "Professional Development period:
  completed Bachelor's degree, pursued certifications, and upskilled in digital tools."
- Civilianize all military terms. Match the industry tone.
- Under 350 words. Do NOT repeat the resume verbatim.

OUTPUT (start immediately, no preamble):

[Full Name]
[City, State] | [Phone] | [Email]

[Date]

Dear Hiring Manager,

[Paragraph 1: Hook]

[Paragraph 2: Body]

[Paragraph 3: Close]

Respectfully,
[Full Name]
"""


def prompt_interview(rank, years, industry, target_title, keywords, user_data):
    ctx = _context_block(rank, years, industry, target_title, keywords, user_data)
    return f"""You are an Interview Coach for a 92Y veteran.

{ctx}

Generate interview prep. Start immediately, no preamble.

## LIKELY INTERVIEW QUESTIONS

**Q1: [Question targeting top JD keyword]**
*Suggested Answer:* [STAR format, 3-4 sentences, using civilianized military experience.]

**Q2: [Question targeting second JD keyword]**
*Suggested Answer:* [STAR format.]

**Q3: [Behavioral question about leadership]**
*Suggested Answer:* [STAR format.]

**Q4: [Behavioral question about problem-solving or customer service]**
*Suggested Answer:* [STAR format.]

**Q5: [Industry-specific technical question]**
*Suggested Answer:* [STAR format.]

## QUESTIONS TO ASK THE INTERVIEWER
1. [Smart question demonstrating JD knowledge]
2. [Question about team structure or growth]
3. [Question about success metrics for the role]

## MILITARY TRANSLATION CHEAT SHEET
| If They Ask About... | Translate Your Experience As... |
|---|---|
| [Civilian concept 1] | [Military equivalent, civilianized] |
| [Civilian concept 2] | [Military equivalent, civilianized] |
| [Civilian concept 3] | [Military equivalent, civilianized] |
"""


# ============================================================
# 7. DOCX EXPORT
# ============================================================

def markdown_to_docx(md_text: str) -> io.BytesIO:
    """Convert markdown resume/letter into a formatted .docx."""
    doc = DocxDocument()
    for section in doc.sections:
        section.top_margin = Inches(0.7)
        section.bottom_margin = Inches(0.7)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)

    style_normal = doc.styles["Normal"]
    style_normal.font.name = "Calibri"
    style_normal.font.size = Pt(10.5)
    style_normal.paragraph_format.space_after = Pt(2)
    style_normal.paragraph_format.space_before = Pt(0)

    lines = md_text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # H1: # Name
        if line.startswith("# ") and not line.startswith("## "):
            text = line.lstrip("# ").strip()
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(text)
            run.bold = True
            run.font.size = Pt(18)
            run.font.name = "Calibri"
            run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x2E)
            p.paragraph_format.space_after = Pt(2)

        # H3: ### Subtitle (Job Title)
        elif line.startswith("### "):
            text = re.sub(r"\*{1,2}", "", line.lstrip("# ").strip())
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(text)
            run.font.size = Pt(12)
            run.font.name = "Calibri"
            run.font.color.rgb = RGBColor(0x44, 0x44, 0x66)
            p.paragraph_format.space_after = Pt(4)

        # H2: ## SECTION HEADER
        elif line.startswith("## "):
            text = line.lstrip("# ").strip()
            p = doc.add_paragraph()
            run = p.add_run(text.upper())
            run.bold = True
            run.font.size = Pt(11)
            run.font.name = "Calibri"
            run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x2E)
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(3)
            # Bottom border
            from docx.oxml.ns import qn
            pPr = p._p.get_or_add_pPr()
            pBdr = pPr.makeelement(qn("w:pBdr"), {})
            bottom = pBdr.makeelement(qn("w:bottom"), {
                qn("w:val"): "single", qn("w:sz"): "4",
                qn("w:space"): "1", qn("w:color"): "1A1A2E",
            })
            pBdr.append(bottom)
            pPr.append(pBdr)

        # Bullet: * text or - text
        elif line.startswith("* ") or line.startswith("- "):
            bullet_text = line[2:].strip()
            p = doc.add_paragraph(style="List Bullet")
            _add_runs(p, bullet_text)
            p.paragraph_format.space_after = Pt(1)
            p.paragraph_format.space_before = Pt(1)

        # Contact line with | separators
        elif "|" in line and ("@" in line or "phone" in line.lower() or "linkedin" in line.lower()):
            text = re.sub(r"\*{1,2}", "", line).strip()
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(text)
            run.font.size = Pt(9.5)
            run.font.name = "Calibri"
            run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
            p.paragraph_format.space_after = Pt(6)

        # Table rows (interview prep cheat sheet)
        elif line.startswith("|") and line.endswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = lines[i].strip()
                if not all(c in "-| :" for c in row):
                    cells = [c.strip() for c in row.split("|")[1:-1]]
                    table_lines.append(cells)
                i += 1
            if table_lines:
                ncols = max(len(r) for r in table_lines)
                table = doc.add_table(rows=len(table_lines), cols=ncols)
                table.style = "Light Grid Accent 1"
                for ri, row_data in enumerate(table_lines):
                    for ci, cell_text in enumerate(row_data):
                        if ci < ncols:
                            cell = table.cell(ri, ci)
                            cell.text = re.sub(r"\*{1,2}", "", cell_text)
                            for par in cell.paragraphs:
                                for run in par.runs:
                                    run.font.size = Pt(9.5)
                                    run.font.name = "Calibri"
            continue

        # Bold line: **text**
        elif line.startswith("**") and "**" in line[2:]:
            p = doc.add_paragraph()
            _add_runs(p, line)
            p.paragraph_format.space_after = Pt(1)

        # Italic line: *text*
        elif line.startswith("*") and line.endswith("*") and not line.startswith("**"):
            text = line.strip("*").strip()
            p = doc.add_paragraph()
            run = p.add_run(text)
            run.italic = True
            run.font.size = Pt(10)
            run.font.name = "Calibri"
            p.paragraph_format.space_after = Pt(1)

        # Regular paragraph
        else:
            p = doc.add_paragraph()
            _add_runs(p, line)
            p.paragraph_format.space_after = Pt(3)

        i += 1

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


def _add_runs(paragraph, text):
    """Parse inline **bold** and *italic* into Word runs."""
    parts = re.split(r"(\*\*.*?\*\*|\*.*?\*)", text)
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        elif part.startswith("*") and part.endswith("*"):
            run = paragraph.add_run(part[1:-1])
            run.italic = True
        else:
            run = paragraph.add_run(part)
        run.font.name = "Calibri"
        run.font.size = Pt(10.5)


# ============================================================
# 8. INPUT VALIDATION
# ============================================================

def validate_inputs(api_key, job_desc, target_title):
    if not api_key:
        return "API Key is required."
    if not job_desc or len(job_desc.split()) < 15:
        return "Job Description is too short. Paste the full JD (minimum ~15 words)."
    if not target_title or len(target_title.strip()) < 3:
        return "Target Job Title is required."
    return None


# ============================================================
# 9. UI LAYOUT
# ============================================================

st.title("ðŸŽ–ï¸ 92Y Career Auto-Pilot")
st.markdown("##### Military-to-Civilian Resume Engine with ATS Keyword Matching")

# Sidebar
with st.sidebar:
    st.header("ðŸ”‘ Authorization")
    default_key = ""
    try:
        default_key = st.secrets.get("GOOGLE_API_KEY", "")
    except Exception:
        pass
    if default_key:
        api_key = default_key
        st.success("API key loaded from server.")
    else:
        api_key = st.text_input("Google Gemini API Key", type="password")
        st.caption("Free key at [aistudio.google.com](https://aistudio.google.com/apikey)")
    st.divider()
    st.markdown(
        "**Generates:**\n"
        "1. ATS-optimized Resume (.docx)\n"
        "2. Tailored Cover Letter (.docx)\n"
        "3. Interview Prep Guide (.docx)"
    )
    st.divider()
    st.caption(
        "v3.0 | Mirror Protocol | Ghostwriter | "
        "No-Repeat Rule | 4-Industry Logic | "
        "Seniority Calibration | .docx Export"
    )

# Two-column input
col1, col2 = st.columns(2)

with col1:
    st.subheader("ðŸ“‚ Your Profile")
    c1, c2 = st.columns(2)
    with c1:
        rank = st.selectbox("Rank", ["E-4 (SPC)", "E-5 (SGT)", "E-6 (SSG)", "E-7 (SFC)", "E-8 (MSG)"])
    with c2:
        years = st.number_input("Years of Service", 1, 30, 9)

    input_tab1, input_tab2, input_tab3 = st.tabs(
        ["ðŸ“„ Upload Resume", "âœï¸ Paste Bullets", "âœ¨ Generate from Scratch"]
    )
    user_data = ""
    with input_tab1:
        uploaded_file = st.file_uploader("Upload PDF or DOCX", type=["pdf", "docx"])
        if uploaded_file:
            try:
                user_data = read_file(uploaded_file)
                st.success(f"Loaded {len(user_data.split())} words from {uploaded_file.name}")
            except (ValueError, Exception) as e:
                st.error(str(e))

    with input_tab2:
        manual_text = st.text_area(
            "Paste NCOER bullets, award citations, or brain dump:",
            height=200,
            placeholder="- Maintained 100% accountability of $15M property book\n- Scored 98% on CSDP inspection\n- Processed 15 FLIPLs recovering $200k",
        )
        if manual_text:
            user_data = manual_text

    with input_tab3:
        st.info(
            "No resume? No problem. Leave the other tabs empty. "
            "The AI will build your resume from scratch based on your Rank, "
            "Years of Service, and the Job Description."
        )

with col2:
    st.subheader("ðŸŽ¯ Target Position")
    target_ind = st.selectbox(
        "Target Industry",
        ["Corporate (General)", "Defense Contractor", "Federal (USAJOBS)", "Tech / SaaS"],
    )
    target_title = st.text_input("Target Job Title", placeholder="e.g., Procurement Buyer II")
    job_desc = st.text_area(
        "Paste Full Job Description",
        height=200,
        placeholder="Paste the complete JD here. The AI will scan for every requirement.",
    )


# ============================================================
# 10. STEP 1: KEYWORD EXTRACTION
# ============================================================

st.divider()

if st.button("ðŸ” Step 1: Extract JD Keywords", type="secondary"):
    err = validate_inputs(api_key, job_desc, target_title)
    if err:
        st.warning(err)
    else:
        try:
            with st.spinner("Scanning job description for ATS keywords..."):
                if not st.session_state.model:
                    st.session_state.model = init_model(api_key)
                raw = call_model(st.session_state.model, prompt_keywords(job_desc))
                kws = json.loads(raw)
                if not isinstance(kws, list) or len(kws) < 3:
                    raise ValueError("Too few keywords returned.")
                st.session_state.keywords = kws
                st.session_state.keywords_confirmed = False
                st.session_state.generation_complete = False
                st.session_state.resume_md = None
                st.session_state.cover_letter_md = None
                st.session_state.interview_md = None
        except json.JSONDecodeError:
            st.error("Failed to parse keywords. Try again.")
        except Exception as e:
            st.error(f"Keyword extraction failed: {e}")


# Show editable keywords
if st.session_state.keywords and not st.session_state.keywords_confirmed:
    st.markdown("**Extracted JD Keywords** (edit, remove, or add):")
    edited = []
    cols = st.columns(3)
    for idx, kw in enumerate(st.session_state.keywords):
        with cols[idx % 3]:
            val = st.text_input(f"Keyword {idx+1}", value=kw, key=f"kw_{idx}")
            if val.strip():
                edited.append(val.strip())

    add_kw = st.text_input("Add a keyword (optional):", key="add_kw", placeholder="e.g., Lean Six Sigma")

    kc1, kc2 = st.columns(2)
    with kc1:
        if st.button("âœ… Confirm Keywords & Generate", type="primary"):
            if add_kw.strip():
                edited.append(add_kw.strip())
            st.session_state.keywords = edited
            st.session_state.keywords_confirmed = True
            st.rerun()
    with kc2:
        if st.button("ðŸ”„ Re-extract"):
            st.session_state.keywords = None
            st.rerun()


# ============================================================
# 11. STEP 2: GENERATE ALL THREE SECTIONS (separate calls)
# ============================================================

if st.session_state.keywords_confirmed and not st.session_state.generation_complete:
    model = st.session_state.model
    kws = st.session_state.keywords

    # If no user data, note it for the prompts
    if not user_data:
        user_data = f"[NO DATA PROVIDED. Generate from scratch for {rank} with {years} years of 92Y service. Assume top 10% performer.]"

    progress = st.progress(0, text="Starting generation...")

    try:
        progress.progress(10, text="Generating resume...")
        st.session_state.resume_md = call_model(
            model, prompt_resume(rank, years, target_ind, target_title, kws, user_data)
        )

        progress.progress(45, text="Generating cover letter...")
        st.session_state.cover_letter_md = call_model(
            model, prompt_cover_letter(rank, years, target_ind, target_title, kws, user_data)
        )

        progress.progress(75, text="Generating interview prep...")
        st.session_state.interview_md = call_model(
            model, prompt_interview(rank, years, target_ind, target_title, kws, user_data)
        )

        progress.progress(100, text="Complete!")
        st.session_state.generation_complete = True
        time.sleep(0.5)
        st.rerun()

    except Exception as e:
        progress.empty()
        st.error(f"Generation failed: {e}")
        st.info("Try again. If the error persists, check your API key and quota.")


# ============================================================
# 12. DISPLAY RESULTS
# ============================================================

if st.session_state.generation_complete:
    st.balloons()
    st.divider()
    st.subheader("Your Career Package")

    tab1, tab2, tab3 = st.tabs(["ðŸ“„ Resume", "âœ‰ï¸ Cover Letter", "ðŸŽ¤ Interview Prep"])

    with tab1:
        st.markdown(st.session_state.resume_md)
        resume_docx = markdown_to_docx(st.session_state.resume_md)
        dc1, dc2 = st.columns(2)
        with dc1:
            st.download_button(
                "â¬‡ï¸ Download Resume (.docx)",
                data=resume_docx,
                file_name=f"Resume_{target_title.replace(' ', '_')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        with dc2:
            st.download_button("â¬‡ï¸ Download Resume (.md)", data=st.session_state.resume_md, file_name="Resume.md")

    with tab2:
        st.markdown(st.session_state.cover_letter_md)
        cl_docx = markdown_to_docx(st.session_state.cover_letter_md)
        dc1, dc2 = st.columns(2)
        with dc1:
            st.download_button(
                "â¬‡ï¸ Download Cover Letter (.docx)",
                data=cl_docx,
                file_name=f"Cover_Letter_{target_title.replace(' ', '_')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        with dc2:
            st.download_button("â¬‡ï¸ Download Cover Letter (.md)", data=st.session_state.cover_letter_md, file_name="Cover_Letter.md")

    with tab3:
        st.markdown(st.session_state.interview_md)
        int_docx = markdown_to_docx(st.session_state.interview_md)
        dc1, dc2 = st.columns(2)
        with dc1:
            st.download_button(
                "â¬‡ï¸ Download Interview Prep (.docx)",
                data=int_docx,
                file_name=f"Interview_Prep_{target_title.replace(' ', '_')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        with dc2:
            st.download_button("â¬‡ï¸ Download Interview Prep (.md)", data=st.session_state.interview_md, file_name="Interview_Prep.md")

    st.divider()
    if st.button("ðŸ”„ Start Over"):
        for key in STATE_DEFAULTS:
            st.session_state[key] = STATE_DEFAULTS[key]
        st.rerun()

