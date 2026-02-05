
import csv
import json
import uuid

def migrate():
    test_cases = []
    
    # Try reading CSV with fallback encodings
    rows = []
    encodings = ['utf-8', 'gbk']
    
    for enc in encodings:
        try:
            with open("test_cases.csv", "r", encoding=enc) as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            print(f"Successfully read CSV with {enc}")
            break
        except UnicodeDecodeError:
            continue
            
    if not rows:
        print("Failed to read CSV or file is empty")
        return

    # Convert to new JSON structure
    for row in rows:
        test_cases.append({
            "id": str(uuid.uuid4()),
            "input": row.get("input", ""),
            "expected_output": row.get("expected_output", ""),
            "retrieval_context": row.get("retrieval_context", "").split("\n") if row.get("retrieval_context") else [],
            "tags": ["migrated"],
            "created_at": None
        })
        
    # Write to JSON
    with open("data/test_cases.json", "w", encoding="utf-8") as f:
        json.dump(test_cases, f, indent=4, ensure_ascii=False)
        
    print(f"Migrated {len(test_cases)} cases to data/test_cases.json")

if __name__ == "__main__":
    migrate()
