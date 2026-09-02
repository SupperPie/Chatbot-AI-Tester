import os
import json
import pandas as pd
import datetime
import streamlit as st
from typing import List, Dict
from fpdf import FPDF
from app.test_engine import TestEngine

# Constants - absolute paths to avoid CWD issues on deployed servers
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(_BASE_DIR, "data", "test_cases.json")

# Ensure data directory exists
os.makedirs(os.path.join(_BASE_DIR, "data"), exist_ok=True)

@st.cache_resource
def get_test_engine():
    """Cache TestEngine to avoid reinitializing GEval metric on every run."""
    return TestEngine()

def generate_tc_id(index: int) -> str:
    return f"TC{str(index + 1).zfill(4)}"


def load_data() -> pd.DataFrame:
    """Load test cases from database (if enabled) or JSON file."""
    # Feature flag - set to True to enable database loading with category support
    ENABLE_CATEGORY_FEATURE = True
    
    df = None
    
    # Try loading from database if feature is enabled
    if ENABLE_CATEGORY_FEATURE:
        try:
            from app.services.test_case_service import TestCaseService
            service = TestCaseService()
            db_cases = service.get_all()
            if db_cases:
                print(f"[load_data] 从数据库加载了 {len(db_cases)} 条记录")
                # Debug: 检查前几条的 category_id
                if len(db_cases) > 0:
                    sample_cats = [(tc.id, tc.category_id) for tc in db_cases[:5]]
                    print(f"[load_data] 前5条记录的 (id, category_id): {sample_cats}")
                
                data = []
                for tc in db_cases:
                    record = {
                        'id': tc.id,
                        'input': tc.input,
                        'expected_output': tc.expected_output,
                        'tags': tc.tags or [],
                        'type': tc.type,
                        'turn_index': tc.turn_index,
                        'category_id': tc.category_id if tc.category_id is not None else 'root',
                        'retrieval_context': tc.retrieval_context,
                        'overall_criteria': tc.overall_criteria,
                        'validation': tc.validation,
                        'assertions': tc.assertions or [],
                        'priority': tc.priority,
                    }
                    data.append(record)
                df = pd.DataFrame(data)
        except Exception as e:
            print(f"[load_data] Failed to load from database: {e}")
            df = None
    
    # Fallback to JSON file
    if df is None:
        data = []
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except:
                data = []
                
        if not data:
            # Return empty structure with Select column
            return pd.DataFrame(columns=["Select", "id", "turn_index", "input", "expected_output", "tags", "category_id", "priority"])

        df = pd.DataFrame(data)
        # Add default category_id for JSON data
        if 'category_id' not in df.columns:
            df['category_id'] = 'root'
        if 'priority' not in df.columns:
            df['priority'] = None
    
    # ID Generation logic: Only generate for explicitly missing IDs.
    # If a row is missing an ID, but it's part of a multi-turn sequence (turn_index > 1), assign it the same ID as the row before it.
    if "id" not in df.columns:
        df["id"] = ""
        
    current_max_id_num = 0
    # Find existing max TCxxxx to avoid collisions
    for existing_id in df["id"].dropna():
        if str(existing_id).startswith("TC"):
            try:
                num = int(str(existing_id)[2:])
                current_max_id_num = max(current_max_id_num, num)
            except:
                pass

    # Ensure turn_index exists and default to 1
    if "turn_index" not in df.columns:
        df["turn_index"] = 1
    df["turn_index"] = df["turn_index"].apply(lambda x: int(x) if not pd.isna(x) else 1)

    last_assigned_id = None
    for idx, row in df.iterrows():
        row_id = str(row.get("id", "")).strip()
        if not row_id or row_id.lower() == "nan":
            turn_idx = row.get("turn_index")
            row_type = row.get("type", "single")
            # If it's a continuing turn of a multi_turn, try to use the last assigned ID
            if row_type == "multi_turn" and turn_idx and int(turn_idx) > 1 and last_assigned_id:
                df.at[idx, "id"] = last_assigned_id
            else:
                # Generate new ID
                current_max_id_num += 1
                new_id = generate_tc_id(current_max_id_num - 1) # fn adds 1
                df.at[idx, "id"] = new_id
                last_assigned_id = new_id
        else:
            last_assigned_id = row_id

    # Add Select column if not present (for row selection in UI)
    if "Select" not in df.columns:
        df.insert(0, "Select", False)
    
    # Ensure columns exist
    for col in ["input", "expected_output", "retrieval_context", "overall_criteria", "validation"]:
        if col not in df.columns:
            df[col] = ""

    if "priority" not in df.columns:
        df["priority"] = None
    else:
        def normalize_priority(v):
            if v is None:
                return None
            s = str(v).strip().upper()
            return s if s in ("P0", "P1", "P2") else None
        df["priority"] = df["priority"].apply(normalize_priority)
    if "tags" not in df.columns:
        df["tags"] = [[] for _ in range(len(df))]
    else:
        # Sanitize tags column to ensure lists
        def ensure_list(x):
            if isinstance(x, list): return x
            if pd.isna(x) or x == "": return []
            try:
                import ast
                # Handle string representation of list "['a', 'b']"
                parsed = ast.literal_eval(str(x))
                if isinstance(parsed, list): return parsed
            except:
                pass
            # Handle plain string "tag" -> ["tag"]
            return [str(x)] if str(x).strip() else []
            
        df["tags"] = df["tags"].apply(ensure_list)
        
    return df

def save_data(df: pd.DataFrame):
    # Remove UI/internal columns before saving
    to_save_df = df.drop(columns=["Select", "__row_key"], errors='ignore').copy()
    
    if "id" not in to_save_df.columns:
        to_save_df["id"] = ""
        
    # Ensure turn_index exists and default to 1
    if "turn_index" not in to_save_df.columns:
        to_save_df["turn_index"] = 1
    def safe_turn_index(x):
        try:
            if pd.isna(x):
                return 1
        except (TypeError, ValueError):
            pass
        try:
            return int(x)
        except (TypeError, ValueError):
            return 1
    to_save_df["turn_index"] = to_save_df["turn_index"].apply(safe_turn_index)

    # Find existing max TCxxxx to avoid collisions
    current_max_id_num = 0
    for existing_id in to_save_df["id"].dropna():
        if str(existing_id).startswith("TC"):
            try:
                num = int(str(existing_id)[2:])
                current_max_id_num = max(current_max_id_num, num)
            except:
                pass

    last_assigned_id = None
    for idx, row in to_save_df.iterrows():
        row_id = str(row.get("id", "")).strip()
        if not row_id or row_id.lower() == "nan":
            turn_idx = row.get("turn_index", 1)
            row_type = row.get("type", "single")
            # Only share ID if it is explicitly a multi_turn continuing conversation
            if row_type == "multi_turn" and turn_idx and int(turn_idx) > 1 and last_assigned_id:
                to_save_df.at[idx, "id"] = last_assigned_id
            else:
                current_max_id_num += 1
                new_id = generate_tc_id(current_max_id_num - 1)
                to_save_df.at[idx, "id"] = new_id
                last_assigned_id = new_id
        else:
            last_assigned_id = row_id
    
    to_save = to_save_df.to_dict(orient="records")
    
    # Debug: 检查 category_id
    print(f"[save_data] 准备保存 {len(to_save)} 条记录")
    if to_save:
        cat_ids = [r.get('category_id') for r in to_save[:5]]  # 前5条
        print(f"[save_data] 前5条记录的 category_id: {cat_ids}")

    # 写 DB
    from app.services.test_case_service import TestCaseService
    service = TestCaseService()
    service.upsert_all(to_save)
    
    return to_save_df

def save_records(records: list) -> int:
    """只保存指定的若干条记录到 DB（增量保存）。
    
    不含任何 ID 自动生成/重分配逻辑。
    仅对传入的 records 做 upsert，适用于表格编辑后的增量写入。
    """
    from app.services.test_case_service import TestCaseService
    if not records:
        return 0
    # 清洗 turn_index
    for r in records:
        try:
            ti = r.get('turn_index')
            if ti is None or (isinstance(ti, float) and pd.isna(ti)):
                r['turn_index'] = 1
            else:
                r['turn_index'] = int(ti)
        except (TypeError, ValueError):
            r['turn_index'] = 1
    print(f"[save_records] 增量保存 {len(records)} 条")
    service = TestCaseService()
    return service.upsert_records(records)

def save_history(results: List[Dict], api_name: str = "Unknown"):
    """保存测试执行结果到 DB"""
    from app.services.history_service import HistoryService
    service = HistoryService()
    service.save(results, api_name=api_name)

def run_tests_sync(selected_cases: List[Dict], api_name: str = "Skills", progress_bar=None):
    engine = get_test_engine()  # Use cached instance
    
    def on_progress(result, current, total):
        if progress_bar:
            percent = min(current / total, 1.0)
            progress_bar.progress(percent, text=f"Running {current}/{total}...")
            
    results = engine.run_batch(selected_cases, api_name=api_name, on_step_complete=on_progress)
    save_history(results, api_name=api_name)
    return results

def delete_reports(report_ids: List[str]):
    """Delete reports by their IDs from DB"""
    try:
        from app.services.history_service import HistoryService
        service = HistoryService()
        service.delete(report_ids)
        return True
    except Exception as e:
        print(f"Error deleting reports: {e}")
        return False

def export_pdf(df: pd.DataFrame):
     # FPDF2
     pdf = FPDF()
     pdf.add_page()
     
     # Use a Chinese font (YouYuan - SIMYOU.TTF)
     # We must ensure the file exists. We verified it does.
     # In FPDF2, we add font with fname.
     font_path = "C:/Windows/Fonts/SIMYOU.TTF"
     
     try:
         pdf.add_font("YouYuan", style="", fname=font_path)
         pdf.set_font("YouYuan", size=10)
     except Exception as e:
         # Fallback if font fails (though unlikely if checked)
         pdf.set_font("Helvetica", size=10)
         st.error(f"Could not load Chinese font. PDF might be garbled. Error: {e}")
     
     pdf.cell(200, 10, text="Execution Report", new_x="LMARGIN", new_y="NEXT", align='C')
     
     # Simple Table
     cols = ["id", "input", "expected_output", "passed", "score"]
     # Check cols exist
     cols = [c for c in cols if c in df.columns]
     
     # Header
     for col in cols:
         pdf.cell(30, 10, text=col, border=1)
     pdf.ln()
     
     # Rows
     for _, row in df.iterrows():
         for col in cols:
             # Convert to string and handle basic display
             txt = str(row.get(col, ""))[:15] # Truncate 
             pdf.cell(30, 10, text=txt, border=1)
         pdf.ln()
         
     # return bytes directly via output()
     return bytes(pdf.output())

def get_job_manager():
    from app.job_manager import get_job_manager as _get_mgr
    return _get_mgr()

def update_history_entry(entry_id: str, new_results: List[Dict]):
    """Update a specific history entry with new results (e.g. manual review edits)"""
    try:
        from app.services.history_service import HistoryService
        service = HistoryService()
        return service.update_results(entry_id, new_results)
    except Exception as e:
        print(f"Error updating history: {e}")
        return False
