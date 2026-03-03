import os
import json
import argparse
import shutil
from datetime import datetime

def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            print(f"Error decoding JSON from {path}")
            return None

def save_json(data, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def merge_test_cases(source_cases, target_cases):
    if not source_cases:
        return target_cases
    if not target_cases:
        return source_cases
        
    target_dict = {tc.get('id'): tc for tc in target_cases if tc.get('id')}
    
    updated_count = 0
    added_count = 0
    for tc in source_cases:
        tc_id = tc.get('id')
        if not tc_id:
            continue
        if tc_id in target_dict:
            # Overwrite with source (local) as it might be an update
            target_dict[tc_id] = tc
            updated_count += 1
        else:
            target_dict[tc_id] = tc
            added_count += 1
            
    merged = list(target_dict.values())
    
    # Sort by ID
    merged.sort(key=lambda x: str(x.get('id', '')))
    
    print(f"  Test cases: Updated {updated_count}, Added {added_count}. Total is now {len(merged)}")
    return merged

def merge_history(source_hist, target_hist):
    if not source_hist:
        return target_hist
    if not target_hist:
        return source_hist
        
    # Put target first, so source (which might have the same items run locally) gets deduped correctly if we iterate combined.
    # Actually, we want to keep all. Since IDs are timestamps, there shouldn't be much overlap unless copied.
    combined = target_hist + source_hist
    
    # Remove duplicates by id
    seen = set()
    unique_hist = []
    for item in combined:
        item_id = item.get('id')
        if item_id:
            if item_id not in seen:
                seen.add(item_id)
                unique_hist.append(item)
        else:
            unique_hist.append(item)
            
    # Sort descending by id (timestamp)
    unique_hist.sort(key=lambda x: str(x.get('id', '')), reverse=True)
    
    added_count = len(unique_hist) - len(target_hist)
    print(f"  History: Merged {added_count} new records. Total is now {len(unique_hist)}")
    return unique_hist

def merge_blind_reviews(source_rev, target_rev):
    if not source_rev:
        return target_rev
    if not target_rev:
        return source_rev
        
    combined = target_rev + source_rev
    seen = set()
    unique_rev = []
    for item in combined:
        name = item.get('name')
        if name:
            if name not in seen:
                seen.add(name)
                unique_rev.append(item)
        else:
            unique_rev.append(item)
            
    # Sort descending by created_at or name
    unique_rev.sort(key=lambda x: str(x.get('created_at', x.get('name', ''))), reverse=True)
    
    added_count = len(unique_rev) - len(target_rev)
    print(f"  Blind Reviews: Merged {added_count} new records. Total is now {len(unique_rev)}")
    return unique_rev

def main():
    parser = argparse.ArgumentParser(description="Merge local and server JSON data directories.")
    parser.add_argument('--source', '-s', required=True, help="Path to the source data directory (e.g., local data uploaded to server)")
    parser.add_argument('--target', '-t', default='data', help="Path to the target data directory (e.g., server data) (default: 'data')")
    parser.add_argument('--no-backup', action='store_true', help="Disable backup of target directory before merging")
    
    args = parser.parse_args()
    
    source = args.source
    target = args.target
    
    if not os.path.isdir(source):
        print(f"Error: Source directory '{source}' does not exist.")
        return
        
    if not os.path.isdir(target):
        os.makedirs(target, exist_ok=True)
        print(f"Created target directory '{target}'.")
        
    print(f"Merging data from '{source}' into '{target}'...")
    
    # Backup
    if not args.no_backup and os.path.exists(target):
        backup_dir = f"{target}_backup_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        shutil.copytree(target, backup_dir)
        print(f"  Backed up '{target}' to '{backup_dir}'")
    
    # Merge test_cases.json
    src_tc_path = os.path.join(source, 'test_cases.json')
    tgt_tc_path = os.path.join(target, 'test_cases.json')
    src_tc = load_json(src_tc_path)
    if src_tc is not None:
        tgt_tc = load_json(tgt_tc_path)
        merged_tc = merge_test_cases(src_tc, tgt_tc or [])
        save_json(merged_tc, tgt_tc_path)
        print(f"  Saved {tgt_tc_path}")
        
    # Merge history.json
    src_hist_path = os.path.join(source, 'history.json')
    tgt_hist_path = os.path.join(target, 'history.json')
    src_hist = load_json(src_hist_path)
    if src_hist is not None:
        tgt_hist = load_json(tgt_hist_path)
        merged_hist = merge_history(src_hist, tgt_hist or [])
        save_json(merged_hist, tgt_hist_path)
        print(f"  Saved {tgt_hist_path}")
        
    # Merge blind_reviews.json
    src_rev_path = os.path.join(source, 'blind_reviews.json')
    tgt_rev_path = os.path.join(target, 'blind_reviews.json')
    src_rev = load_json(src_rev_path)
    if src_rev is not None:
        tgt_rev = load_json(tgt_rev_path)
        merged_rev = merge_blind_reviews(src_rev, tgt_rev or [])
        save_json(merged_rev, tgt_rev_path)
        print(f"  Saved {tgt_rev_path}")
        
    print("\nMerge completed successfully.")

if __name__ == '__main__':
    main()
