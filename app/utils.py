import os
import json
import pandas as pd
import datetime
import streamlit as st
from typing import List, Dict
from fpdf import FPDF
from app.test_engine import TestEngine

# Constants
DATA_FILE = "data/test_cases.json"
HISTORY_JSON = "data/history.json"

@st.cache_resource
def get_test_engine():
    """Cache TestEngine to avoid reinitializing GEval metric on every run."""
    return TestEngine()

def generate_tc_id(index: int) -> str:
    return f"TC{str(index + 1).zfill(4)}"

def load_data() -> pd.DataFrame:
    # Always try to load or create empty
    data = []
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            data = []
            
    if not data:
        # Return empty structure with Select column
        return pd.DataFrame(columns=["Select", "id", "input", "expected_output", "tags"])

    df = pd.DataFrame(data)
    
    # FORCE ID Regeneration to match requested format TCxxxx for ALL rows
    if "id" not in df.columns:
         df["id"] = [generate_tc_id(i) for i in range(len(df))]
    
    # Add Select column if not present (for row selection in UI)
    if "Select" not in df.columns:
        df.insert(0, "Select", False)
    
    # Ensure columns exist
    for col in ["input", "expected_output"]:
        if col not in df.columns:
            df[col] = ""
    if "tags" not in df.columns:
        df["tags"] = [[] for _ in range(len(df))]
        
    return df

def save_data(df: pd.DataFrame):
    # Remove 'Select' column before saving (it's only for UI)
    to_save_df = df.drop(columns=["Select"], errors='ignore').copy()
    
    should_regenerate = False
    
    # Check: Missing IDs
    if "id" not in to_save_df.columns or to_save_df["id"].isnull().any() or (to_save_df["id"] == "").any():
        should_regenerate = True
    
    if should_regenerate:
        to_save_df["id"] = [generate_tc_id(i) for i in range(len(to_save_df))]
    
    to_save = to_save_df.to_dict(orient="records")
            
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=4, ensure_ascii=False)
    
    return to_save_df

def save_history(results: List[Dict], api_name: str = "Unknown"):
    history = []
    if os.path.exists(HISTORY_JSON):
        try:
            with open(HISTORY_JSON, "r", encoding="utf-8") as f:
                history = json.load(f)
        except:
            history = []
    
    passed_count = sum(1 for r in results if r.get("passed", False))
    total_count = len(results)
    
    entry = {
         "id": datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
         "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         "api_name": api_name,
         "total": total_count,
         "passed": passed_count,
         "failed": total_count - passed_count,
         "results": results
    }
    
    history.insert(0, entry) # Prepend
    
    with open(HISTORY_JSON, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=4, ensure_ascii=False)

def run_tests_sync(selected_cases: List[Dict], api_name: str = "Bundle API", progress_bar=None):
    engine = get_test_engine()  # Use cached instance
    
    def on_progress(current, total):
        if progress_bar:
            percent = min(current / total, 1.0)
            progress_bar.progress(percent, text=f"Running {current}/{total}...")
            
    results = engine.run_batch(selected_cases, api_name=api_name, progress_callback=on_progress)
    save_history(results, api_name=api_name)
    return results

def delete_reports(report_ids: List[str]):
    """Delete reports by their IDs from history.json"""
    if not os.path.exists(HISTORY_JSON):
        return
        
    try:
        with open(HISTORY_JSON, "r", encoding="utf-8") as f:
            history = json.load(f)
            
        new_history = [entry for entry in history if entry.get("id") not in report_ids]
        
        with open(HISTORY_JSON, "w", encoding="utf-8") as f:
            json.dump(new_history, f, indent=4, ensure_ascii=False)
            
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
