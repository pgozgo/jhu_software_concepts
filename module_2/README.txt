================================================================================
Module 2 Assignment : Web Scraping (https://www.thegradcafe.com/)
Course: Modern Software Concepts in Python / FA26
Student Name : Sean Bae

Run the site on Windows
-----------------------
HTTPS - https://github.com/pgozgo/jhu_software_concepts.git
SSH - git@github.com:pgozgo/jhu_software_concepts.git
Repository: jhu_software_concepts / module_2
================================================================================

1. INTRODUCTION
This project provides a robust, modular web scraping and data standardization pipeline designed to collect 
graduate school admissions survey results from The Grad Cafe (https://www.thegradcafe.com/survey/index.php).

Key Features:
- Robots.txt Compliance (#6): Verifies permission using urllib.robotparser before requests.
- Polite Web Scraping: Implements randomized pauses (2.0–4.0s delays between requests).
- Cloudflare Block Bypass: Supports reading saved HTML files and directories if live HTTP requests get blocked by Cloudflare (HTTP 403).
- Comprehensive Parsing: Combines BeautifulSoup, regular expressions, and string methods to extract structured fields (Program, University, Status, Term, Degree, Scores, Comments).
- Clean Output Schema: Cleans HTML tags, removes extra spaces, and leaves out null or empty fields.
- LLM Data Standardization: Integrates with an LLM microservice to map messy program and university names into clean, official formats.

--------------------------------------------------------------------------------
2. QUICK START / HOW TO RUN
A. Setup Environment:
    python -m venv venv
    venv\Scripts\activate            # On Windows
    # source venv/bin/activate       # On macOS / Linux
    pip install -r requirements.txt

B. Step 1 — Scrape Admissions Data (scrape.py):
    # Option 1: Live Scraping (e.g. 5 pages up to 100 entries)
    python scrape.py --pages 5 --target_row 100 --output applicant_data.json

    # Option 2: Saved HTML File (Hybrid Capture Mode — Cloudflare Bypass)
    python scrape.py --file saved_page.html --output applicant_data.json

    # Option 3: Directory of Saved HTML Files
    python scrape.py --dir ./html_pages/ --output applicant_data.json

C. Step 2 — Clean and Standardize Data (clean.py):
    # 1. Start the LLM microservice in a separate terminal
    python llm_hosting/app.py

    # 2. Run the cleaner script
    python clean.py --input applicant_data.json --output llm_extend_applicant_data.json

--------------------------------------------------------------------------------
3. PROJECT ARCHITECTURE & WORKFLOW
The project is split into two modular scripts:

  Part 1: scrape.py
  - Step 1: Confirms robots.txt permissions with urllib.robotparser and urllib3.
  - Step 2: Builds Grad Cafe URLs with urllib.parse and fetches data using urllib3.
  - Step 3: Parses admissions data using BeautifulSoup, regex, and string search.
  - Output: applicant_data.json

  Part 2: clean.py
  - Step 4: Cleans and standardizes degree programs and universities with an LLM.
  - Step 5: Formats and outputs structured JSON data.
  - Output: llm_extend_applicant_data.json


--------------------------------------------------------------------------------
4. FUNCTION SUMMARIES & EXECUTION CASES
Functions in scrape.py:
  - _check_robots_permission(user_agent="*"): Checks robots.txt permission.
  - _build_url(page=1, query_text=""): Constructs query URLs using urllib.parse.
  - _fetch_html(url): Requests page HTML using urllib3 and handles HTTP status codes.
  - parse_admissions_data(html_content): Parses raw HTML with BeautifulSoup and regex.
  - scrape_data(max_pages, target_row, html_file, html_dir): Manages and runs the scraping process.
  - clean_text(val): Strips tags, unescapes entities, and normalizes whitespace.
  - _format_seconds(seconds): Formats seconds into human-readable elapsed and estimated remaining time.
  - save_data(data, filepath): Writes formatted JSON records to file.

Execution Cases in scrape_data():
  - Case A (html_file): Reads a single previously saved HTML page (saved_page.html).
  - Case B (html_dir): Reads all saved HTML files in a folder (e.g. ./html_pages/).
  - Case C (Live Scraping): Performs live HTTP requests across multiple survey pages.

Functions in clean.py:
  - load_data(filepath): Reads applicant_data.json (falls back to sample_data.json if empty).
  - clean_data(dataset, endpoint): Sends rows to LLM or rule-based fallback with real-time progress, elapsed time, and estimated remaining time tracking.
  - _clean_record(program_text): Connects to http://localhost:8000/standardize or rules.
  - _standardize_with_rules(program_text): Regex/dictionary rule-based fallback.
  - save_data(data, filepath): Saves standardized output to JSON.

--------------------------------------------------------------------------------
5. THINGS USERS SHOULD BE AWARE OF
1. Cloudflare Bot Challenges (HTTP 403):
   The Grad Cafe frequently enforces Cloudflare bot protection on automated scripts.
   If live scraping returns HTTP 403, use Hybrid Capture Mode:
     a. Open https://www.thegradcafe.com/survey/index.php in Chrome.
     b. Pass Cloudflare verification once manually.
     c. Save the page HTML (Ctrl+S -> saved_page.html).
     d. Run: python scrape.py --file saved_page.html

2. Page Yields & Target Row Logic:
   Each HTML survey page yields ~20 applicant entries.
   - For 100 entries: Set --pages 5 --target_row 100.
   - For 50,000 entries: Set --pages 2500 --target_row 50000. The --target_row argument will automatically stop scraping once the target count is reached.

3. Clean Schema & Null/Empty Omission:
   Fields containing null or empty string values ("") are automatically removed
   from the output JSON to ensure clean, lightweight records.

4. LLM Service & Standardization Notes:
   If the local LLM microservice (llm_hosting/app.py) is offline, clean.py
   automatically falls back to rule-based regex and dictionary standardization.
   - Canonical Lists: Located in llm_hosting/canon_universities.txt and canon_programs.txt.
   - Post-Processing: Uses difflib fuzzy matching and regex rules to normalize university abbreviations (e.g. "JHU" -> "Johns Hopkins University").
   - Edge Cases & Imperfections: Non-English institution names, obscure program abbreviations, or entries where school name is omitted in raw input may return "unknown" or remain unexpanded.

--------------------------------------------------------------------------------
6. ROBOTS.TXT COMPLIANCE & EVIDENCE
Before making any requests, scrape.py checks:
  https://www.thegradcafe.com/robots.txt

robots.txt permissions:
- User-agent: *
- Allow: /
- Content-Signal: search=yes, ai-train=no, use=reference
- Survey data at /survey/index.php is publicly permitted.

Evidence:
- Verified programmatically via urllib.robotparser.RobotFileParser.
- Verification screenshot saved as screenshot.jpg in the module_2 directory.

--------------------------------------------------------------------------------
7. POLITE SCRAPING PRACTICES & ERROR HANDLING
- Random delays between requests (2.0 - 4.0 seconds) avoid overwhelming the server.
- The scraper monitors HTTP status codes and immediately stops upon:
    - HTTP 403 (Cloudflare block)
    - HTTP 429 (Rate limiting)
    - Network connectivity rejections

--------------------------------------------------------------------------------
8. DATA SCHEMAS
Raw Scraped Data (applicant_data.json):
[
  {
    "program": "Information Studies, McGill University",
    "url": "https://www.thegradcafe.com/result/935454",
    "status": "Wait listed",
    "term": "Fall 2024",
    "US/International": "International",
    "Degree": "Masters",
    "date_added": "Added on March 31, 2024",
    "comments": "Fellowship applicant"
  }
]

Cleaned Data (llm_extend_applicant_data.json):
[
  {
    "program": "Information Studies, McGill University",
    "url": "https://www.thegradcafe.com/result/935454",
    "status": "Wait listed",
    "term": "Fall 2024",
    "US/International": "International",
    "Degree": "Masters",
    "date_added": "Added on March 31, 2024",
    "comments": "Fellowship applicant",
    "llm-generated-program": "Information Studies",
    "llm-generated-university": "McGill University"
  }
]
