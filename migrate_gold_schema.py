import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.getcwd(), 'services/api'))
sys.path.insert(0, os.getcwd())

from libs.terminology.client import TerminologyClient
from scripts.run_val_41005ba4_terminology_resolve import RESOLVE_BATCH

def migrate_expected_strings():
    fixture_path = Path("tests/fixtures/clinical_extraction_scenarios/expected_strings.json")
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    unique_terms = set()
    for case in data.get("cases", []):
        for s in case.get("expected_strings", []):
            if isinstance(s, str) and s.strip():
                unique_terms.add(s.strip())
                
    print(f"Resolving {len(unique_terms)} unique terms for semantic tags...")
    client = TerminologyClient(timeout=30.0)
    terms_list = sorted(list(unique_terms))
    results = {}
    
    for i in range(0, len(terms_list), RESOLVE_BATCH):
        chunk = terms_list[i : i + RESOLVE_BATCH]
        try:
            results.update(client.resolve(chunk))
        except Exception as e:
            print(f"Batch failed: {e}")
            
    # Default mappings for common terms that might fail to resolve perfectly
    default_tags = {
        "mri scan of the brain": "procedure",
        "mri brain": "procedure",
        "urgent mri scan of the brain": "procedure",
        "altered bowel function": "finding",
        "lower urinary tract symptoms": "finding",
        "abnormal prostate examination": "finding",
        "abnormal cxr": "finding",
        "weight loss": "finding",
        "ca125 raised": "finding"
    }

    updated_cases = 0
    for case in data.get("cases", []):
        new_expected_strings = []
        for s in case.get("expected_strings", []):
            if isinstance(s, dict):
                new_expected_strings.append(s)
                continue
                
            s_str = s.strip()
            tag = "finding" # fallback
            
            # Check for observables (from blood results)
            is_observable = False
            for br in case.get("blood_results", {}).get("results", []):
                if br.get("display_name") == s_str or br.get("test_name") == s_str:
                    is_observable = True
                    break
            
            if is_observable:
                tag = "observable_entity"
            elif s_str.lower() in default_tags:
                tag = default_tags[s_str.lower()]
            else:
                candidates = results.get(s_str, [])
                if candidates:
                    tag = candidates[0].semantic_tag or "finding"
                    
            new_expected_strings.append({"text": s_str, "semantic_tag": tag})
            
        case["expected_strings"] = new_expected_strings
        updated_cases += 1
        
    with open(fixture_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
        
    print(f"Migrated {updated_cases} cases.")

if __name__ == "__main__":
    migrate_expected_strings()
