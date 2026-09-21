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


def print_remaining_time(processed_items, total_items, start_time):
    # Print elapsed, remaining, and estimated total processing time.
    elapsed_seconds = time.time() - start_time
    if processed_items == 0:
        print(
            f"[Progress] 0/{total_items} entries | "
            "Elapsed: 00m 00s | Remaining: Unknown | Estimated total: Unknown",
            flush=True,
        )
        return

    average_seconds = elapsed_seconds / processed_items
    remaining_seconds = max(0, total_items - processed_items) * average_seconds
    estimated_total_seconds = elapsed_seconds + remaining_seconds

    print(
        f"[Progress] {processed_items}/{total_items} entries | "
        f"Elapsed: {_format_seconds(elapsed_seconds)} | "
        f"Remaining: {_format_seconds(remaining_seconds)} | "
        f"Estimated total: {_format_seconds(estimated_total_seconds)}",
        flush=True,
    )


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
            "llm_generated_program": prog,
            "llm_generated_university": univ,
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
                            "llm_generated_program": rows[0].get(
                                "llm_generated_program",
                                rows[0].get("llm-generated-program", ""),
                            ),
                            "llm_generated_university": rows[0].get(
                                "llm_generated_university",
                                rows[0].get("llm-generated-university", ""),
                            ),
                        }
                        self._cache[program_text] = res
                        return res
            except Exception:
                self._endpoint_available = False  # Switch to fast rule fallback if LLM drops

        res = self._standardize_with_rules(program_text)
        self._cache[program_text] = res
        return res

    def _standardize_batch(self, program_texts, start_time, batch_size=32):
        # Standardize unique programs in batches to avoid one HTTP request per row.
        unique_programs = list(dict.fromkeys(program_texts))
        if not unique_programs or not self._check_endpoint():
            return

        for start in range(0, len(unique_programs), batch_size):
            batch = unique_programs[start:start + batch_size]
            try:
                response = self._session.post(
                    self.llm_endpoint,
                    json={"rows": [{"program": text} for text in batch]},
                    headers={"Content-Type": "application/json"},
                    timeout=60.0,
                )
                response.raise_for_status()
                result_rows = response.json().get("rows", [])

                for program_text, result in zip(batch, result_rows):
                    program_value = result.get(
                        "llm_generated_program",
                        result.get("llm-generated-program", ""),
                    )
                    university_value = result.get(
                        "llm_generated_university",
                        result.get("llm-generated-university", ""),
                    )
                    self._cache[program_text] = {
                        "llm_generated_program": program_value,
                        "llm_generated_university": university_value,
                    }

                for program_text in batch[len(result_rows):]:
                    self._cache[program_text] = self._standardize_with_rules(program_text)

                processed_programs = min(start + batch_size, len(unique_programs))
                elapsed_seconds = time.time() - start_time
                average_seconds = elapsed_seconds / processed_programs
                remaining_seconds = (
                    len(unique_programs) - processed_programs
                ) * average_seconds
                print(
                    f"[Cleaning] Standardized {processed_programs}/{len(unique_programs)} unique programs | "
                    f"Elapsed: {_format_seconds(elapsed_seconds)} | "
                    f"Estimated remaining: {_format_seconds(remaining_seconds)} | "
                    f"Estimated total: {_format_seconds(elapsed_seconds + remaining_seconds)}",
                    flush=True,
                )
            except (requests.RequestException, ValueError, KeyError) as error:
                self._endpoint_available = False
                print(
                    f"[Cleaning] Batch standardization failed ({error}); using rules fallback.",
                    flush=True,
                )
                return

    def clean_dataset(self, dataset): # Clean the entire dataset using the LLM and rules
        cleaned_rows = []
        total_items = len(dataset)
        start_time = time.time()

        print(f"[Cleaning] Starting {total_items} entries.", flush=True)
        if total_items == 0:
            print_remaining_time(0, 0, start_time)
            return cleaned_rows

        program_texts = [item.get("program") or "" for item in dataset]
        self._standardize_batch(program_texts, start_time)

        for idx, item in enumerate(dataset, 1):
            print(
                f"[Cleaning] Processing entry {idx}/{total_items}...",
                flush=True,
            )
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

            prog_val = clean_text(std_fields.get("llm_generated_program"))
            univ_val = clean_text(std_fields.get("llm_generated_university"))

            if prog_val and prog_val != "unknown":
                row["llm_generated_program"] = prog_val

            if univ_val and univ_val != "unknown":
                row["llm_generated_university"] = univ_val

            # Remove items with null or empty string values
            final_row = {}
            for k, v in row.items():
                if v is not None and v != "":
                    final_row[k] = v

            cleaned_rows.append(final_row)

            # Print timing details after every completed entry.
            print_remaining_time(idx, total_items, start_time)

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