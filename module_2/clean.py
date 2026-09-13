"""
Module 2 - Data Cleaner : clean.py
Handles cleaning and standardization of applicant data using LLM and rule-based methods.
"""
import argparse
import json
import os
import re
import time
import requests
from scrape import clean_text, _format_seconds

class DataCleaner: # Handles cleaning and standardization of applicant data using LLM
    # These patterns are used to recognize and standardize common university abbreviations in the dataset for LLM processing.
    # # (?i) makes the pattern case-insensitive, ^ asserts the start of the string, $ asserts the end of the string
    # Example: r"(?i)^mcg(\.|ill)?$" will match "mcg", "mcg.", "mcgill" in a case-insensitive manner.
    UNIVERSITY_ABBREVIATIONS = {
        r"(?i)^mcg(\.|ill)?$": "McGill University",
        r"(?i)^(ubc|u\.?b\.?c\.?)$": "University of British Columbia",
        r"(?i)^uoft$": "University of Toronto",
        r"(?i)^jhu$": "Johns Hopkins University",
        r"(?i)^mit$": "Massachusetts Institute of Technology",
        r"(?i)^cmu$": "Carnegie Mellon University",
        r"(?i)^stanford$": "Stanford University",
        r"(?i)^harvard$": "Harvard University",
        r"(?i)^columbia$": "Columbia University",
    }

    # Spelling and normalization fixes
    SPELLING_FIXES = {
        "Mcgill University": "McGill University",
        "Mcgiill University": "McGill University",
        "University Of British Columbia": "University of British Columbia",
    }

    def __init__(self, llm_endpoint="http://localhost:8000/standardize"):
        self.llm_endpoint = llm_endpoint
        self._session = requests.Session()
        self._cache = {}
        self._endpoint_available = None  # None = untested, True/False after probe

    def _check_endpoint(self):
        """Quick 1-second check to see if local LLM server is online."""
        if self._endpoint_available is not None:
            return self._endpoint_available
        try:
            resp = self._session.get("http://localhost:8000/", timeout=1.0)
            self._endpoint_available = (resp.status_code == 200)
        except Exception:
            self._endpoint_available = False
        return self._endpoint_available

    def _standardize_with_rules(self, program_text): # standardize program and university names using rules
        if program_text:
            raw_text = program_text.strip().rstrip(",")
        else:
            raw_text = ""

        # Split on comma, " at ", or " @ "
        parts = []
        for p in re.split(r",|\bat\b|@", raw_text):
            if p.strip():
                parts.append(p.strip())

        if len(parts) > 0:
            prog = parts[0]
        else:
            prog = "unknown"

        if len(parts) > 1:
            univ = parts[1]
        else:
            univ = "unknown"

        # Expand university abbreviations
        for pattern, full_name in self.UNIVERSITY_ABBREVIATIONS.items():
            if re.search(pattern, univ):
                univ = full_name
                break

        # Apply specific spelling corrections
        univ = self.SPELLING_FIXES.get(univ, univ)

        # Standardize common program names
        prog = re.sub(r"(?i)^info(\s+studies)?$", "Information Studies", prog)
        prog = re.sub(r"(?i)^cs$", "Computer Science", prog)
        prog = re.sub(r"(?i)^math(s|ematics)?$", "Mathematics", prog)

        # Proper casing
        prog = prog.title()
        if univ != "unknown" and univ not in self.SPELLING_FIXES.values() and univ not in self.UNIVERSITY_ABBREVIATIONS.values():
            univ = re.sub(r"\bOf\b", "of", univ.title())

        return {
            "llm-generated-program": prog,
            "llm-generated-university": univ,
        }

    # Clean with LLM
    def _clean_record(self, program_text): # Clean a single record using the LLM endpoint or rules fallback
        if program_text in self._cache:
            return self._cache[program_text]

        if self._check_endpoint():
            try:
                response = self._session.post(
                    self.llm_endpoint,
                    json={"rows": [{"program": program_text}]},
                    headers={"Content-Type": "application/json"},
                    timeout=2.0
                )
                if response.status_code == 200:
                    result = response.json()
                    rows = result.get("rows", [])
                    if rows:
                        res = {
                            "llm-generated-program": rows[0].get("llm-generated-program", ""),
                            "llm-generated-university": rows[0].get("llm-generated-university", ""),
                        }
                        self._cache[program_text] = res
                        return res
            except Exception:
                self._endpoint_available = False  # Switch to fast rule fallback if LLM drops

        res = self._standardize_with_rules(program_text)
        self._cache[program_text] = res
        return res

    def clean_dataset(self, dataset): # Clean the entire dataset using the LLM and rules
        cleaned_rows = []
        total_items = len(dataset)
        start_time = time.time()

        for idx, item in enumerate(dataset, 1):
            row = {}
            for k, v in item.items():
                if isinstance(v, str):
                    cleaned_val = clean_text(v)
                    if cleaned_val:
                        row[k] = cleaned_val
                elif v is not None:
                    row[k] = v

            program_text = row.get("program")
            if not program_text:
                program_text = ""
            std_fields = self._clean_record(program_text)

            prog_val = clean_text(std_fields.get("llm-generated-program"))
            univ_val = clean_text(std_fields.get("llm-generated-university"))

            if prog_val and prog_val != "unknown":
                row["llm-generated-program"] = prog_val

            if univ_val and univ_val != "unknown":
                row["llm-generated-university"] = univ_val

            # Remove items with null or empty string values
            final_row = {}
            for k, v in row.items():
                if v is not None and v != "":
                    final_row[k] = v

            cleaned_rows.append(final_row)

            # Log progress with elapsed and remaining time
            elapsed_sec = time.time() - start_time
            avg_time_per_item = elapsed_sec / idx
            remaining_items = total_items - idx
            remaining_sec = remaining_items * avg_time_per_item

            elapsed_str = _format_seconds(elapsed_sec)
            remaining_str = _format_seconds(remaining_sec)

            log_interval = max(10, total_items // 20)
            if idx == total_items or idx % log_interval == 0 or total_items <= 20:
                print(
                    f"[Cleaning] Processed {idx}/{total_items} entries | "
                    f"Elapsed: {elapsed_str} | Est. Remaining ({remaining_items} left): {remaining_str}"
                )

        return cleaned_rows

    # Save llm-extended JSON file with cleaned data
    def save_formatted_json(self, data, output_filepath="llm_extend_applicant_data.json"):
        with open(output_filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[Saved] {len(data)} cleaned records written to {output_filepath}")

# Top-Level Helpers & Functions
def load_data(filepath="applicant_data.json"): # Load applicant data from JSON file
    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def clean_data(dataset, endpoint="http://localhost:8000/standardize"): # Clean applicant data using LLM standardization
    cleaner = DataCleaner(llm_endpoint=endpoint)
    return cleaner.clean_dataset(dataset)

def save_data(data, filepath="llm_extend_applicant_data.json"): # Save cleaned dataset to JSON file
    cleaner = DataCleaner()
    cleaner.save_formatted_json(data, filepath)

# CLI Entrypoint
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Grad Cafe Applicant Data Cleaner & LLM Standardizer")
    parser.add_argument("--input", "-i", default="applicant_data.json", help="Input JSON path")
    parser.add_argument("--output", "-o", default="llm_extend_applicant_data.json", help="Output JSON path")
    parser.add_argument("--endpoint", "-e", default="http://localhost:8000/standardize", help="LLM API endpoint")
    args = parser.parse_args()

    current_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(current_dir, args.input)
    output_path = os.path.join(current_dir, args.output)

    # 1. Load applicant data from json file
    raw_data = load_data(input_path)
    print(f"[Loading] Read {len(raw_data)} applicant entries.")

    # 2. Clean data into structured format
    cleaned_data = clean_data(raw_data, endpoint=args.endpoint)

    # 3. Save cleaned data into json file
    save_data(cleaned_data, output_path)

# How to use:
# 1. Place your raw applicant data in 'applicant_data.json'.
# 2. Run this script: python clean.py
# 3. The cleaned and standardized data will be saved to 'llm_extend_applicant_data.json' by default.
# 4. You can specify custom input/output paths and LLM endpoint using command-line arguments.