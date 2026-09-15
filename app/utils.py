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
                        'input_cn': tc.input_cn or "",
                        'expected_output': tc.expected_output,
                        'expected_output_cn': tc.expected_output_cn or "",
                        'description': tc.description,
                        'tags': tc.tags or [],
                        'type': tc.type,
                        'turn_index': tc.turn_index,
                        'category_id': tc.category_id if tc.category_id is not None else 'root',
                        'retrieval_context': tc.retrieval_context,
                        'overall_criteria': tc.overall_criteria,
                        'validation': tc.validation,
                        'assertions': tc.assertions or [],
                        'priority': tc.priority,
                        'module': tc.module,
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
            return pd.DataFrame(columns=["Select", "id", "turn_index", "input", "expected_output", "tags", "category_id", "priority", "module"])

        df = pd.DataFrame(data)
        # Add default category_id for JSON data
        if 'category_id' not in df.columns:
            df['category_id'] = 'root'
        if 'priority' not in df.columns:
            df['priority'] = None
        if 'module' not in df.columns:
            df['module'] = None
        if 'description' not in df.columns:
            df['description'] = None
    
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
    if "module" not in df.columns:
        df["module"] = None
    else:
        df["module"] = df["module"].apply(lambda v: str(v).strip() if v is not None and not (isinstance(v, float) and pd.isna(v)) else None)
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


# =====================================================================
# 日期刷新工具：将测试用例中的过去/较远日期替换为未来 90 天内的日期
# 支持中文 / 英文 / 葡萄牙语；覆盖 input / input_cn / expected_output /
# expected_output_cn / retrieval_context，同一条记录内相同日期替换一致
# 多日期场景保持原有先后顺序与间隔（整体平移），不会出现"退房早于入住"
# =====================================================================
import re as _re
import random as _random
from datetime import datetime as _dt, timedelta as _td

# 月份名
_EN_MONTHS = ['january','february','march','april','may','june',
              'july','august','september','october','november','december']
_EN_MON_ABBR = ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec']
_PT_MONTHS = ['janeiro','fevereiro','março','abril','maio','junho',
              'julho','agosto','setembro','outubro','novembro','dezembro']

# 刷新目标区间（天）
_PAST_DAYS_MIN, _PAST_DAYS_MAX = 1, 30        # 带年份的过期/远期日期 → 未来 1~30 天
_NOYEAR_DAYS_MIN, _NOYEAR_DAYS_MAX = 1, 90    # 无年份的较远日期 → 未来 3 个月内
_FAR_FUTURE_DAYS = 90                        # 超过未来 90 天视为"较远"
_MAX_GROUP_GAP = 30                          # 多日期组的间隔上限（保证全组落在 90 天内）


def _detect_lang(text: str) -> str:
    """根据特征词判断语言：zh / en / pt"""
    t = text.lower()
    # 中文字符
    if _re.search(r'[\u4e00-\u9fff]', text):
        return 'zh'
    # 葡语特征词
    pt_markers = [' de ', ' às ', ' para ', ' com ', ' no ', ' na ', ' em ', ' dia ',
                  'reservar', 'quero', 'agendar', 'transfer', 'hotel', 'check-in',
                  'adulto', 'criança', 'crianca', 'bagagem', 'voo', 'partida', 'chegada']
    if any(m in t for m in pt_markers):
        return 'pt'
    # 英语兜底（check-in/book/hotel/flight 等在葡语里也会出现，但葡语带 de 介词）
    return 'en'


def _bj_today():
    """北京时间今天的 date"""
    return (_dt.utcnow() + _td(hours=8)).date()


def _future_date(min_days=1, max_days=30, ref=None):
    """返回未来 [min_days, max_days] 范围内的一个 date"""
    ref = ref or _dt.utcnow() + _td(hours=8)  # 用北京时间做参考
    delta = _random.randint(min_days, max_days)
    return (ref + _td(days=delta)).date()


def _nearest_future_date(month: int, day: int, today):
    """无年份日期按"最近未来"补全年份（今年不行则明年）；无效日期返回 None"""
    for year in (today.year, today.year + 1):
        try:
            d = _dt(year, month, day).date()
        except ValueError:
            return None
        if d >= today:
            return d
    return None


def _mk_date_key(y, mo, d, time_part=None):
    """带年份日期的共享 key（跨语言统一：中/英/葡同一日期同 key）"""
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}:{time_part or ''}"


def _mk_noyear_key(mo, d, time_part=None):
    """无年份日期的共享 key（跨语言统一）"""
    return f"noyear:{int(mo):02d}-{int(d):02d}:{time_part or ''}"


# 英文月份正则片段（全称/缩写）
_EN_MON_PAT = (
    r'(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
    r'Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
)


def _replace_all_dates(text: str, shared_map: dict = None) -> tuple:
    """替换文本中的日期，返回 (new_text, replaced_count)。

    特性：
    - 同一文本多日期：整组保持先后顺序与相对间隔整体平移
    - 无年份日期：按最近未来补全年份判断远近；较远(>90天)则刷新到 3 个月内
    - shared_map 跨字段/跨语言共享（key 不带语言前缀），
      保证原文 "1 May 2023" 与翻译 "2023年5月1日" 刷新后仍是同一天
    """
    if not isinstance(text, str) or not text.strip():
        return text, 0

    shared_map = shared_map if isinstance(shared_map, dict) else {}
    matches = []

    def _add_match(start, end, dt_obj, fmt, key, no_year=False):
        matches.append({
            'start': start,
            'end': end,
            'dt': dt_obj,          # 带年份时的真实日期；无年份时 None
            'fmt': fmt,
            'key': key,
            'no_year': bool(no_year),
            'resolved': None,      # 补全后的日期（含无年份），判定用
        })

    # --- 1. 中文 yyyy年m月d日/号 [ H:MM] ---
    zh_pat = _re.compile(r'(\d{4})年(\d{1,2})月(\d{1,2})[日号](?:\s*(\d{1,2}:\d{2}))?')
    for m in zh_pat.finditer(text):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            dt_obj = _dt(y, mo, d).date()
        except ValueError:
            continue
        time_part = m.group(4)

        def _fmt_zh(nd, tp=time_part):
            base = f"{nd.year}年{nd.month}月{nd.day}日"
            return base + ((tp or "") if tp else "")

        _add_match(m.start(), m.end(), dt_obj, _fmt_zh, _mk_date_key(y, mo, d, time_part), no_year=False)

    # --- 1b. 中文 m月d日/号 [ H:MM]（无年份） ---
    zh_no_year_pat = _re.compile(r'(?<!\d)(\d{1,2})月(\d{1,2})[日号](?:\s*(\d{1,2}:\d{2}))?')
    for m in zh_no_year_pat.finditer(text):
        mo, d = int(m.group(1)), int(m.group(2))
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            continue
        time_part = m.group(3)

        def _fmt_zh_no_year(nd, tp=time_part):
            base = f"{nd.month}月{nd.day}日"
            return base + ((tp or "") if tp else "")

        _add_match(m.start(), m.end(), None, _fmt_zh_no_year, _mk_noyear_key(mo, d, time_part), no_year=True)

    # --- 2. 葡语 d de mês de yyyy [ às HH:MM] ---
    pt_pat = _re.compile(
        r'(\d{1,2})\s+de\s+([a-zç]+)\s+de\s+(\d{4})(?:\s+às\s+(\d{1,2}:\d{2}))?',
        _re.IGNORECASE,
    )
    for m in pt_pat.finditer(text):
        d, mname, y = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        if mname not in _PT_MONTHS:
            continue
        mo = _PT_MONTHS.index(mname) + 1
        try:
            dt_obj = _dt(y, mo, d).date()
        except ValueError:
            continue
        time_part = m.group(4)
        day_pad = (len(m.group(1)) == 2)

        def _fmt_pt(nd, tp=time_part, pad=day_pad):
            day = f"{nd.day:02d}" if pad else str(nd.day)
            base = f"{day} de {_PT_MONTHS[nd.month - 1]} de {nd.year}"
            return base + (f" às {tp}" if tp else "")

        _add_match(m.start(), m.end(), dt_obj, _fmt_pt, _mk_date_key(y, mo, d, time_part), no_year=False)

    # --- 2b. 葡语 d de mês [ às HH:MM]（无年份） ---
    pt_no_year_pat = _re.compile(
        r'(\d{1,2})\s+de\s+([a-zç]+)(?:\s+às\s+(\d{1,2}:\d{2}))?',
        _re.IGNORECASE,
    )
    for m in pt_no_year_pat.finditer(text):
        d, mname = int(m.group(1)), m.group(2).lower()
        if mname not in _PT_MONTHS:
            continue
        mo = _PT_MONTHS.index(mname) + 1
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            continue
        time_part = m.group(3)
        day_pad = (len(m.group(1)) == 2)

        def _fmt_pt_no_year(nd, tp=time_part, pad=day_pad):
            day = f"{nd.day:02d}" if pad else str(nd.day)
            base = f"{day} de {_PT_MONTHS[nd.month - 1]}"
            return base + (f" às {tp}" if tp else "")

        _add_match(m.start(), m.end(), None, _fmt_pt_no_year, _mk_noyear_key(mo, d, time_part), no_year=True)

    # --- 3. 英文 dd Mmm yyyy [ at HH:MM]（数字前置） ---
    en_pat = _re.compile(
        r'(\d{1,2})\s+' + _EN_MON_PAT + r'\s+(\d{4})(?:\s+at\s+(\d{1,2}:\d{2}))?',
        _re.IGNORECASE,
    )
    for m in en_pat.finditer(text):
        d, mname, y = int(m.group(1)), m.group(2)[:3].lower(), int(m.group(3))
        mo = _EN_MON_ABBR.index(mname) + 1
        try:
            dt_obj = _dt(y, mo, d).date()
        except ValueError:
            continue
        time_part = m.group(4)
        day_pad = (len(m.group(1)) == 2)
        orig_month = m.group(2)

        def _fmt_en(nd, tp=time_part, pad=day_pad, om=orig_month):
            day = f"{nd.day:02d}" if pad else str(nd.day)
            if len(om) <= 4:
                m_str = _EN_MON_ABBR[nd.month - 1].capitalize()
            else:
                m_str = _EN_MONTHS[nd.month - 1].capitalize()
            base = f"{day} {m_str} {nd.year}"
            return base + (f" at {tp}" if tp else "")

        _add_match(m.start(), m.end(), dt_obj, _fmt_en, _mk_date_key(y, mo, d, time_part), no_year=False)

    # --- 3b. 英文 dd Mmm [ at HH:MM]（数字前置，无年份） ---
    en_no_year_pat = _re.compile(
        r'(?<!\d)(\d{1,2})\s+' + _EN_MON_PAT + r'(?:\s+at\s+(\d{1,2}:\d{2}))?(?!\s*\d)',
        _re.IGNORECASE,
    )
    for m in en_no_year_pat.finditer(text):
        d, mname = int(m.group(1)), m.group(2)[:3].lower()
        mo = _EN_MON_ABBR.index(mname) + 1
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            continue
        time_part = m.group(3)
        day_pad = (len(m.group(1)) == 2)
        orig_month = m.group(2)

        def _fmt_en_no_year(nd, tp=time_part, pad=day_pad, om=orig_month):
            day = f"{nd.day:02d}" if pad else str(nd.day)
            if len(om) <= 4:
                m_str = _EN_MON_ABBR[nd.month - 1].capitalize()
            else:
                m_str = _EN_MONTHS[nd.month - 1].capitalize()
            base = f"{day} {m_str}"
            return base + (f" at {tp}" if tp else "")

        _add_match(m.start(), m.end(), None, _fmt_en_no_year, _mk_noyear_key(mo, d, time_part), no_year=True)

    # --- 3c. 英文 Mmm dd[st|nd|rd|th][,] yyyy [ at HH:MM]（月份前置带年份） ---
    en_md_y_pat = _re.compile(
        _EN_MON_PAT + r'\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})(?:\s+at\s+(\d{1,2}:\d{2}))?',
        _re.IGNORECASE,
    )
    for m in en_md_y_pat.finditer(text):
        mname, d, y = m.group(1)[:3].lower(), int(m.group(2)), int(m.group(3))
        mo = _EN_MON_ABBR.index(mname) + 1
        try:
            dt_obj = _dt(y, mo, d).date()
        except ValueError:
            continue
        time_part = m.group(4)
        orig_month = m.group(1)
        has_comma = (',' in m.group(0))

        def _fmt_en_md_y(nd, tp=time_part, om=orig_month, hc=has_comma, dd=d):
            day = f"{nd.day:02d}" if len(str(dd)) == 2 else str(nd.day)
            if len(om) <= 4:
                m_str = _EN_MON_ABBR[nd.month - 1].capitalize()
            else:
                m_str = _EN_MONTHS[nd.month - 1].capitalize()
            comma = "," if hc else ""
            base = f"{m_str} {day}{comma} {nd.year}"
            return base + (f" at {tp}" if tp else "")

        _add_match(m.start(), m.end(), dt_obj, _fmt_en_md_y, _mk_date_key(y, mo, d, time_part), no_year=False)

    # --- 3d. 英文 Mmm dd[st|nd|rd|th] [ at HH:MM]（月份前置，无年份） ---
    en_md_pat = _re.compile(
        _EN_MON_PAT + r'\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+at\s+(\d{1,2}:\d{2}))?(?!\s*\d)',
        _re.IGNORECASE,
    )
    for m in en_md_pat.finditer(text):
        mname, d = m.group(1)[:3].lower(), int(m.group(2))
        mo = _EN_MON_ABBR.index(mname) + 1
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            continue
        time_part = m.group(3)
        orig_month = m.group(1)

        def _fmt_en_md(nd, tp=time_part, om=orig_month, dd=d):
            day = f"{nd.day:02d}" if len(str(dd)) == 2 else str(nd.day)
            if len(om) <= 4:
                m_str = _EN_MON_ABBR[nd.month - 1].capitalize()
            else:
                m_str = _EN_MONTHS[nd.month - 1].capitalize()
            base = f"{m_str} {day}"
            return base + (f" at {tp}" if tp else "")

        _add_match(m.start(), m.end(), None, _fmt_en_md, _mk_noyear_key(mo, d, time_part), no_year=True)

    # --- 4. yyyy-m-d / yyyy-mm-dd ---
    iso_pat = _re.compile(r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b')
    for m in iso_pat.finditer(text):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            dt_obj = _dt(y, mo, d).date()
        except ValueError:
            continue
        mo_pad = (len(m.group(2)) == 2)
        d_pad = (len(m.group(3)) == 2)

        def _fmt_iso(nd, mp=mo_pad, dp=d_pad):
            m_str = f"{nd.month:02d}" if mp else str(nd.month)
            d_str = f"{nd.day:02d}" if dp else str(nd.day)
            return f"{nd.year}-{m_str}-{d_str}"

        _add_match(m.start(), m.end(), dt_obj, _fmt_iso, _mk_date_key(y, mo, d), no_year=False)

    # --- 5. M/D/YYYY ---
    md_pat = _re.compile(r'(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)')
    for m in md_pat.finditer(text):
        mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= mo <= 12 and 1 <= d <= 31 and y >= 2020):
            continue
        if m.start() > 0 and text[m.start() - 1] == '-':
            continue
        try:
            dt_obj = _dt(y, mo, d).date()
        except ValueError:
            continue
        mo_pad = (len(m.group(1)) == 2)
        d_pad = (len(m.group(2)) == 2)

        def _fmt_md(nd, mp=mo_pad, dp=d_pad):
            m_str = f"{nd.month:02d}" if mp else str(nd.month)
            d_str = f"{nd.day:02d}" if dp else str(nd.day)
            return f"{m_str}/{d_str}/{nd.year}"

        _add_match(m.start(), m.end(), dt_obj, _fmt_md, _mk_date_key(y, mo, d), no_year=False)

    # --- 5b. M/D（无年份；第一组>12 时按 D/M 欧式解读） ---
    md_no_year_pat = _re.compile(r'(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)')
    for m in md_no_year_pat.finditer(text):
        a, b = int(m.group(1)), int(m.group(2))
        if a <= 12:
            mo, d = a, b
        elif b <= 12:
            mo, d = b, a  # D/M 欧式
        else:
            continue
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            continue
        a_pad = (len(m.group(1)) == 2)
        b_pad = (len(m.group(2)) == 2)
        was_dm = (a > 12)

        def _fmt_md_no_year(nd, ap=a_pad, bp=b_pad, dm=was_dm):
            if dm:
                d_str = f"{nd.day:02d}" if ap else str(nd.day)
                m_str = f"{nd.month:02d}" if bp else str(nd.month)
                return f"{d_str}/{m_str}"
            m_str = f"{nd.month:02d}" if ap else str(nd.month)
            d_str = f"{nd.day:02d}" if bp else str(nd.day)
            return f"{m_str}/{d_str}"

        _add_match(m.start(), m.end(), None, _fmt_md_no_year, _mk_noyear_key(mo, d), no_year=True)

    # 去重：按起始位置、优先更长匹配（带年份优先于无年份）
    matches.sort(key=lambda x: (x['start'], -(x['end'] - x['start'])))
    dedup = []
    last_end = -1
    for item in matches:
        if item['start'] >= last_end:
            dedup.append(item)
            last_end = item['end']
    matches = dedup

    if not matches:
        return text, 0

    today = _bj_today()

    # --- 6. 补全 resolved 日期（无年份：优先继承前一个带年份日期的年份，其次最近未来） ---
    prev_resolved = None
    prev_year = None
    for item in matches:
        if item['dt'] is not None:
            item['resolved'] = item['dt']
            prev_resolved = item['dt']
            prev_year = item['dt'].year
            continue

        # 无年份：从 key 解析月日（noyear:MM-DD:time）
        try:
            md_part = item['key'].split(':', 1)[1].rsplit(':', 1)[0]
            mo_s, d_s = md_part.split('-')
            mo, d = int(mo_s), int(d_s)
        except Exception:
            item['resolved'] = None
            continue

        resolved = None
        # 尝试继承上下文年份（含跨年 +1）
        if prev_year is not None:
            fallback = None
            for y in (prev_year, prev_year + 1):
                try:
                    cand = _dt(y, mo, d).date()
                except ValueError:
                    continue
                if fallback is None:
                    fallback = cand
                if prev_resolved is None or cand >= prev_resolved:
                    resolved = cand
                    break
            if resolved is None and fallback is not None:
                resolved = fallback
        # 无上下文：按最近未来补全
        if resolved is None:
            resolved = _nearest_future_date(mo, d, today)

        item['resolved'] = resolved
        if resolved is not None:
            if prev_resolved is None or resolved > prev_resolved:
                prev_resolved = resolved
            prev_year = resolved.year

    # --- 7. 判定需要刷新的日期（过去 或 较远未来>90天） ---
    def _needs_refresh(item):
        r = item['resolved']
        if r is None:
            return True  # 无法解析（如 2月30日）也刷新掉
        return r < today or (r - today).days > _FAR_FUTURE_DAYS

    need_idx = [i for i, it in enumerate(matches) if _needs_refresh(it)]
    if not need_idx:
        return text, 0

    new_dates = {}

    if len(matches) == 1:
        # 单日期：独立刷新
        item = matches[0]
        lo, hi = (_NOYEAR_DAYS_MIN, _NOYEAR_DAYS_MAX) if item['no_year'] else (_PAST_DAYS_MIN, _PAST_DAYS_MAX)
        key = item['key']
        if key in shared_map:
            new_dates[0] = shared_map[key]
        else:
            nd = _future_date(lo, hi)
            shared_map[key] = nd
            new_dates[0] = nd
    else:
        # 多日期：整组保持顺序与间隔整体平移（只要有一个需要刷新就全组刷新）
        prev_new = None
        prev_res = None
        for i, item in enumerate(matches):
            key = item['key']
            if key in shared_map:
                nd = shared_map[key]
            elif prev_new is None:
                # 组内第一个：锚点随机
                nd = _future_date(2, 25)
                shared_map[key] = nd
            else:
                # 后续：保持与前一日期的间隔（clamp 1~30 天）
                gap = 1
                if item['resolved'] is not None and prev_res is not None:
                    gap = (item['resolved'] - prev_res).days
                gap = max(1, min(gap, _MAX_GROUP_GAP))
                nd = prev_new + _td(days=gap)
                shared_map[key] = nd
            new_dates[i] = nd
            prev_new = nd if (prev_new is None or nd > prev_new) else prev_new
            if item['resolved'] is not None:
                prev_res = item['resolved']

        # 顺序修正：确保组内位置靠后的新日期严格晚于靠前（相同 key 共享同一天，跳过）
        for i in range(1, len(matches)):
            if new_dates[i] <= new_dates[i - 1] and matches[i]['key'] != matches[i - 1]['key']:
                new_dates[i] = new_dates[i - 1] + _td(days=1)
                shared_map[matches[i]['key']] = new_dates[i]

    # --- 8. 执行替换（从后往前，避免位置偏移） ---
    result = text
    replaced = 0
    for i in reversed(range(len(matches))):
        if i not in new_dates:
            continue
        item = matches[i]
        new_str = item['fmt'](new_dates[i])
        result = result[:item['start']] + new_str + result[item['end']:]
        replaced += 1

    return result, replaced


def refresh_dates_in_text(text: str, shared_map: dict = None) -> tuple:
    """刷新单条文本中的日期，返回 (new_text, replaced_count)。"""
    if not isinstance(text, str) or not text.strip():
        return text, 0
    return _replace_all_dates(text, shared_map=shared_map)


def refresh_dates_for_records(records: list) -> tuple:
    """批量刷新测试用例记录中的日期。

    同一条记录内对 input / input_cn / retrieval_context / expected_output /
    expected_output_cn 使用同一映射（跨语言 key 统一），
    保证原文与中文翻译刷新后日期仍一致。
    返回 (updated_records, total_replaced)。
    """
    total = 0
    updated = []

    def _refresh_field(rec: dict, field: str, shared_map: dict) -> int:
        """刷新单个字段（str 直接刷，list 逐项刷）。返回替换数。"""
        val = rec.get(field)
        if isinstance(val, list):
            new_list = []
            n = 0
            for item in val:
                item_str = str(item) if item is not None else ""
                new_item, n_item = refresh_dates_in_text(item_str, shared_map=shared_map)
                new_list.append(new_item)
                n += n_item
            if n > 0:
                rec[field] = new_list
            return n
        if val is None:
            return 0
        s = str(val)
        if not s.strip():
            return 0
        new_s, n = refresh_dates_in_text(s, shared_map=shared_map)
        if n > 0:
            rec[field] = new_s
        return n

    for r in records:
        new_r = dict(r)
        shared_map = {}

        # 顺序：先原文（input → retrieval_context → expected_output），
        # 再翻译字段（input_cn → expected_output_cn），共享同一映射
        for field in ('input', 'retrieval_context', 'expected_output',
                      'input_cn', 'expected_output_cn'):
            total += _refresh_field(new_r, field, shared_map)

        updated.append(new_r)

    return updated, total

