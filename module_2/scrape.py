"""
Module 2 - Grad Cafe Web Scraper : scrape.py
Assignment Steps:
1. Confirm robots.txt permits scraping (robots.txt).
2. Use urllib.parse to construct URLs and urllib3 to request data from Grad Cafe.
3. Use BeautifulSoup / regex / string search to parse admissions data.
Output: applicant_data.json
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import html
import json
import os
import random
import re
import time
import urllib.parse
import urllib.robotparser
import urllib3
from bs4 import BeautifulSoup

# Pre-compiled Regex Patterns for High-Performance Parsing
RE_SR_ONLY = re.compile(r"\b(tw-)?sr-only\b")
RE_HAS_STATUS = re.compile(r"\b(Accepted|Rejected|Wait\s*listed|Interview|Other)\b", re.I)
RE_RESULT_LINK = re.compile(r"/result/|\d+")
RE_RESULT_HREF = re.compile(r"/result/")
RE_RESULT_ID = re.compile(r"/result/(\d+)")
RE_SPLIT_PROG = re.compile(
    r"\b(Masters|PhD|Doctorate|MFA|MBA|MS|MA|BS|BA|JD|EdD|PsyD|Fall|Spring|Summer|Winter|American|International|GPA|GRE|GRE\s*V|GRE\s*AW|Accepted|Rejected|Wait\s*listed|Interview)\b",
    re.I
)
RE_STATUS_MATCH = re.compile(
    r"\b((?:Accepted|Rejected|Wait\s*listed|Interview)(?:\s+(?:on|via)\s+(?:[A-Za-z]{3,9}\s+\d{1,2}|\d{1,2}\s+[A-Za-z]{3,9}))?|Wait\s*listed|Interview|Other)\b",
    re.I
)
RE_STATUS_CLEAN = re.compile(r"\s*Total\s+comments.*$", re.I)
RE_TERM = re.compile(r"\b((?:Fall|Spring|Summer|Winter)\s+\d{4})\b", re.I)
RE_NAT = re.compile(r"\b(International\s+with\s+US\s+Degree|International|American)\b", re.I)
RE_OTHER = re.compile(r"\bOther\b", re.I)
RE_DEGREE = re.compile(r"\b(Masters|PhD|Doctorate|MFA|MBA|MS|MA|BS|BA|JD|EdD|PsyD)\b", re.I)
RE_GPA = re.compile(r"\bGPA\s*[:\s]?\s*(\d+\.\d{1,2})\b", re.I)
RE_GRE = re.compile(r"\bGRE\s*(?!V|AW)[:\s]?\s*(\d{3})\b", re.I)
RE_DATE_FULL = re.compile(r"(Added on\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})", re.I)
RE_DATE_MATCH = re.compile(r"\b[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}\b")
RE_DATE_ALT = re.compile(r"\b([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})\b")
RE_NOTE_TAG = re.compile(r"(note|comment|extinfo)", re.I)
RE_COMMENT_IGNORE = re.compile(r"^(Accepted|Rejected|Wait\s*listed|Spring|Fall|Summer|Winter|American|International|GPA|GRE)\b", re.I)

# Grad Cafe Web Scraper Class - Scrapes applicant admissions data from The Grad Cafe
class GradCafeScraper:
    def __init__(self, url="https://www.thegradcafe.com"):
        self.base_url = url.rstrip("/") # Remove trailing slash
        self.survey_path = "/survey/index.php" # https://www.thegradcafe.com/survey/index.php
        self.robots_url = f"{self.base_url}/robots.txt" # https://www.thegradcafe.com/robots.txt

        # Headers for HTTP requests to mimic a real browser and avoid potential blocking
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        # Initialize urllib3 PoolManager for HTTP connection pooling and requests
        self.http = urllib3.PoolManager()

    # A : Check robots.txt permissions before scraping
    def _check_robots_permission(self, user_agent="*"):
        target_url = self._build_url(page=1)
        print(f"[Robots.txt] Checking permissions at {self.robots_url} ...")

        robot_parser = urllib.robotparser.RobotFileParser() # Initialize RobotFileParser for robots.txt parsing
        robot_parser.set_url(self.robots_url)

        # Attempt to fetch and parse robots.txt using urllib3 to confirm permissions
        permitted = False
        try:
            response = self.http.request("GET", self.robots_url, headers=self.headers, timeout=10.0)
            if response.status == 200:
                content = response.data.decode("utf-8", errors="ignore")
                robot_parser.parse(content.splitlines())
                permitted = robot_parser.can_fetch(user_agent, target_url)
            else:
                print(f"[Robots.txt] Received status {response.status}. Defaulting to standard check.")
                permitted = True

        except Exception as e:
            print(f"[Robots.txt] Warning: {e}. Defaulting to standard check.")
            try:
                robot_parser.read()
                permitted = robot_parser.can_fetch(user_agent, target_url)
            except Exception:
                permitted = True

        if permitted:
            status = "ALLOWED"
        else:
            status = "DISALLOWED"
        print(f"[Robots.txt] Result for '{user_agent}' on '{target_url}': {status}")
        return permitted

    # B : Build URLs & Request data from Grad Cafe
    def _build_url(self, page=1, query_text=""):
        params = {}
        if page > 1:
            params["page"] = page
        if query_text:
            params["q"] = query_text

        # Encode query parameters and construct the full URL
        query_string = urllib.parse.urlencode(params)
        full_url = urllib.parse.urljoin(self.base_url, self.survey_path)
        if query_string:
            full_url = f"{full_url}?{query_string}"
        return full_url

    def _fetch_html(self, url): # Fetch HTML content from the given URL
        """Fetch page HTML with urllib3; stops immediately on blocks/errors."""
        try:
            response = self.http.request("GET", url, headers=self.headers, timeout=15.0)

            if response.status == 200: # Successful response
                return response.data.decode("utf-8", errors="ignore")
            elif response.status == 403: # Forbidden / Cloudflare bot challenge
                print(f"\n[HTTP 403 Blocked] Cloudflare bot challenge encountered at:\n  {url}\n")
                return None
            elif response.status == 429: # Too Many Requests / Rate limiting
                print(f"[HTTP 429] Rate limit hit on {url}. Stopping immediately.")
                return None
            else:
                print(f"[HTTP Error] Status {response.status} on {url}")
                return None
        except urllib3.exceptions.HTTPError as e:
            print(f"[urllib3 Error] {e} on {url}")
            return None
        except Exception as e:
            print(f"[Request Error] {e}")
            return None

    # C : Parse admissions data (BeautifulSoup / regex / string search)
    def parse_admissions_data(self, html_content):
        if not html_content:
            return []

        # BeautifulSoup HTML Parsing
        soup = BeautifulSoup(html_content, "html.parser")

        # Decompose screen-reader hidden spans like <span class="tw-sr-only">Total comments</span>
        for sr in soup.find_all(class_=RE_SR_ONLY):
            sr.decompose()

        applicants = []

        # Find all table rows
        rows = soup.find_all("tr")
        i = 0
        while i < len(rows): # Iterate over each table row
            row = rows[i]
            # Extract table cell elements
            cells = row.find_all(["td", "th"])

            # Skip header rows or empty rows
            if not cells or row.find("th") or len(cells) < 2:
                i += 1
                continue

            # Convert element to clean string text
            row_text = row.get_text(" ", strip=True)

            # Validate if row contains relevant applicant status or result link
            has_status = bool(RE_HAS_STATUS.search(row_text))
            has_link = bool(row.find("a", href=RE_RESULT_LINK))
            if not (has_status or has_link or len(cells) >= 3):
                i += 1
                continue

            # Collect sub-rows belonging to this applicant entry
            sub_rows = []
            j = i + 1
            while j < len(rows):
                next_row = rows[j]
                next_cells = next_row.find_all(["td", "th"])
                if "tw-border-none" in next_row.get("class", []) or (next_cells and next_cells[0].has_attr("colspan")):
                    sub_rows.append(next_row)
                    j += 1
                elif len(next_cells) == 1 or next_row.find(class_=RE_NOTE_TAG):
                    sub_rows.append(next_row)
                    j += 1
                else:
                    break

            # Combine main row text and sub-rows text for comprehensive regex search
            sub_rows_text = " ".join([sr.get_text(" ", strip=True) for sr in sub_rows])
            full_entry_text = f"{row_text} {sub_rows_text}".strip()

            record = {} # Initialize an empty dictionary to store applicant data

            # Program and Institution
            inst = clean_text(cells[0].get_text(" ", strip=True))
            if len(cells) > 1:
                prog = clean_text(cells[1].get_text(" ", strip=True))
            else:
                prog = ""

            clean_prog = RE_SPLIT_PROG.split(prog)[0].strip()
            clean_prog = clean_text(clean_prog)

            if clean_prog and inst:
                record["program"] = f"{clean_prog}, {inst}"
            elif inst:
                record["program"] = inst
            elif clean_prog:
                record["program"] = clean_prog
            else:
                record["program"] = None

            # Result URL
            link = row.find("a", href=RE_RESULT_HREF)
            if not link:
                for sub in sub_rows:
                    link = sub.find("a", href=RE_RESULT_HREF)
                    if link:
                        break

            if link and link.get("href"):
                raw_url = urllib.parse.urljoin(self.base_url, link["href"])
                cleaned_url = clean_text(raw_url)
                if cleaned_url:
                    record["url"] = cleaned_url
                else:
                    record["url"] = None
            else:
                id_match = RE_RESULT_ID.search(full_entry_text)
                if id_match:
                    record["url"] = f"{self.base_url}/result/{id_match.group(1)}"
                else:
                    record["url"] = None

            # Decision Status
            status_match = RE_STATUS_MATCH.search(full_entry_text)
            if status_match:
                status_val = clean_text(status_match.group(1))
                status_val = RE_STATUS_CLEAN.sub("", status_val).strip()
                record["status"] = status_val
            else:
                record["status"] = None

            # Term
            term_match = RE_TERM.search(full_entry_text)
            if term_match:
                record["term"] = clean_text(term_match.group(1))
            else:
                record["term"] = None

            # US / International
            nat_match = RE_NAT.search(full_entry_text)
            if nat_match:
                record["US/International"] = clean_text(nat_match.group(1))
            elif "international" in full_entry_text.lower():
                record["US/International"] = "International"
            elif "american" in full_entry_text.lower():
                record["US/International"] = "American"
            elif RE_OTHER.search(full_entry_text):
                record["US/International"] = "Other"
            else:
                record["US/International"] = None

            # Degree
            deg_match = RE_DEGREE.search(full_entry_text)
            if deg_match:
                val = deg_match.group(1)
                if val.lower() in ("phd", "doctorate"):
                    record["Degree"] = "PhD"
                elif val.lower() in ("masters", "ms", "ma"):
                    record["Degree"] = "Masters"
                else:
                    record["Degree"] = clean_text(val)
            else:
                record["Degree"] = None

            # GPA
            gpa_match = RE_GPA.search(full_entry_text)
            if gpa_match:
                record["GPA"] = f"GPA {gpa_match.group(1)}"
            else:
                record["GPA"] = None

            # GRE
            gre_match = RE_GRE.search(full_entry_text)
            if gre_match:
                record["GRE"] = f"GRE {gre_match.group(1)}"
            else:
                record["GRE"] = None

            # Date Added
            date_match = RE_DATE_FULL.search(full_entry_text)
            if date_match:
                record["date_added"] = clean_text(date_match.group(1))
            else:
                if len(cells) > 2:
                    added_text = clean_text(cells[2].get_text(" ", strip=True))
                    if RE_DATE_MATCH.search(added_text):
                        record["date_added"] = f"Added on {added_text}"
                    else:
                        alt_date = RE_DATE_ALT.search(full_entry_text)
                        if alt_date:
                            record["date_added"] = f"Added on {clean_text(alt_date.group(1))}"
                        else:
                            record["date_added"] = None
                else:
                    alt_date = RE_DATE_ALT.search(full_entry_text)
                    if alt_date:
                        record["date_added"] = f"Added on {clean_text(alt_date.group(1))}"
                    else:
                        record["date_added"] = None

            # Comments
            comments = ""
            for sub in sub_rows:
                p_tag = sub.find("p")
                if p_tag:
                    p_text = clean_text(p_tag.get_text(" ", strip=True))
                    if p_text and not RE_COMMENT_IGNORE.match(p_text):
                        comments = p_text
                        break
                    elif p_text and len(p_text.split()) > 4:
                        comments = p_text
                        break
                else:
                    note_tag = sub.find(class_=RE_NOTE_TAG)
                    if note_tag:
                        n_text = clean_text(note_tag.get_text(" ", strip=True))
                        if n_text and not RE_COMMENT_IGNORE.match(n_text):
                            comments = n_text
                            break

            if comments:
                record["comments"] = comments

            # Remove items with null or empty string values
            clean_record = {}
            for k, v in record.items():
                if v is not None and v != "":
                    clean_record[k] = v

            applicants.append(clean_record)
            i = max(j, i + 1)

        return applicants

    # Scrape data and save to JSON
    def scrape(self, max_pages=1, target_row=None, html_file=None, html_dir=None, output_file="applicant_data.json"):
        records = scrape_data(max_pages=max_pages, target_row=target_row, html_file=html_file, html_dir=html_dir)
        if records:
            save_data(records, output_file)
        return records

def clean_text(val): # Clean and normalize text from HTML content
    if val is None:
        return ""
    text = html.unescape(str(val)) # Unescape HTML entities
    # Strip HTML tags and normalize text, removing unnecessary elements and whitespace
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\b(Report|Spam|Delete)\b", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def _format_seconds(seconds):
    """Format seconds into human-readable HH:MM:SS or MM:SS string."""
    if seconds is None:
        return "Unknown"
    if seconds < 0:
        return "Unknown"

    total_secs = int(seconds)
    mins, secs = divmod(total_secs, 60)
    hours, mins = divmod(mins, 60)

    if hours > 0:
        return f"{hours}h {mins:02d}m {secs:02d}s"
    else:
        return f"{mins:02d}m {secs:02d}s"

def scrape_data(max_pages=1, target_row=100, html_file=None, html_dir=None):
    scraper = GradCafeScraper()
    records = []

    # Case A: Saved HTML file - in case you have previously downloaded the page
    if html_file:
        if os.path.exists(html_file):
            start_time = time.time()
            f = open(html_file, "r", encoding="utf-8", errors="ignore")
            parsed = scraper.parse_admissions_data(f.read())
            f.close()
            records.extend(parsed)
            elapsed_sec = time.time() - start_time
            print(f"[File] Extracted {len(parsed)} rows from {html_file} in {_format_seconds(elapsed_sec)}.")
        else:
            return []

    # Case B: Directory of saved HTML files - parallel multi-threaded parsing
    elif html_dir:
        html_files = []
        for f_name in os.listdir(html_dir):
            if f_name.lower().endswith((".html", ".htm")):
                html_files.append(os.path.join(html_dir, f_name))

        def _parse_file(filepath):
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                return scraper.parse_admissions_data(f.read())

        start_time = time.time()
        max_workers = min(8, os.cpu_count() or 4)
        print(f"[Batch] Ingesting {len(html_files)} files using {max_workers} worker threads ...")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {executor.submit(_parse_file, hf): hf for hf in html_files}
            for idx, future in enumerate(as_completed(future_to_file), 1):
                hf = future_to_file[future]
                try:
                    parsed = future.result()
                    records.extend(parsed)
                except Exception as e:
                    print(f"[Batch Error] Failed to parse {os.path.basename(hf)}: {e}")
                    parsed = []

                elapsed_sec = time.time() - start_time
                avg_file_time = elapsed_sec / idx
                remaining_sec = (len(html_files) - idx) * avg_file_time

                print(
                    f"[Batch] Processed {os.path.basename(hf)} ({idx}/{len(html_files)}). "
                    f"Yielded {len(parsed)} entries. Total: {len(records)} | "
                    f"Elapsed: {_format_seconds(elapsed_sec)} | Est. Remaining: {_format_seconds(remaining_sec)}"
                )

    # Case C: Live scraping - fetch data directly from the website [ Real-time ]
    else:
        # Check robots.txt permission before scraping
        if not scraper._check_robots_permission():
            print("[Robots.txt] Access not permitted.")
            return []

        start_time = time.time()
        for page in range(1, max_pages + 1):
            url = scraper._build_url(page=page)
            html = scraper._fetch_html(url)

            if not html:
                print(f"[Halt] Stopping at page {page}.")
                break

            page_records = scraper.parse_admissions_data(html)
            if not page_records:
                print(f"[Notice] No data found on page {page}.")
                break

            records.extend(page_records)

            elapsed_sec = time.time() - start_time
            pages_done = page
            remaining_pages = max_pages - pages_done
            avg_time_per_page = elapsed_sec / pages_done

            # Calculate remaining time based on total pages remaining
            remaining_sec_pages = remaining_pages * avg_time_per_page

            # Also check if target_row limit will be reached earlier
            if target_row and len(records) > 0:
                rate = len(records) / elapsed_sec
                remaining_items = max(0, target_row - len(records))
                if rate > 0:
                    remaining_sec_items = remaining_items / rate
                    remaining_sec = min(remaining_sec_pages, remaining_sec_items)
                else:
                    remaining_sec = remaining_sec_pages
            else:
                remaining_sec = remaining_sec_pages

            elapsed_str = _format_seconds(elapsed_sec)
            remaining_str = _format_seconds(remaining_sec)

            print(
                f"[Progress] Page {page}/{max_pages} yielded {len(page_records)} entries. "
                f"Total rows: {len(records)} | Elapsed: {elapsed_str} | Est. Remaining ({remaining_pages} pages left): {remaining_str}"
            )

            if target_row and len(records) >= target_row:
                print(f"[Goal Reached] Collected {len(records)} entries in {elapsed_str}.")
                break

            if page < max_pages:
                wait_time = random.uniform(2.0, 4.0)
                print(f"[Polite] Waiting {wait_time:.1f}s ...")
                time.sleep(wait_time)

    if target_row and len(records) > target_row:
        records = records[:target_row]

    return records

# save data to JSON file
def save_data(data, filepath="applicant_data.json"):
    f = open(filepath, "w", encoding="utf-8")
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Grad Cafe Admissions Scraper")
    parser.add_argument("--pages", "-p", type=int, default=1, help="Max pages to scrape")
    parser.add_argument("--target_row", "-t", type=int, default=100, help="Target number of entries")
    parser.add_argument("--file", "-f", type=str, help="Path to saved HTML page file")
    parser.add_argument("--dir", "-d", type=str, help="Path to directory containing saved HTML pages")
    parser.add_argument("--output", "-o", default="applicant_data.json", help="Output JSON path")
    args = parser.parse_args()

    current_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(current_dir, args.output)

    # Scrape data from Grad Cafe
    records = scrape_data(
        max_pages=args.pages,
        target_row=args.target_row,
        html_file=args.file,
        html_dir=args.dir,
    )

    # Save data into json file
    if records:
        save_data(records, output_path)

# how to run:
# python scrape.py --pages 1500 --target_row 30000
# python scrape.py --pages 5 --target_row 100 --output applicant_data.json
# python scrape.py --file saved_page.html --output applicant_data.json
