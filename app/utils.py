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
# 日期刷新工具：将测试用例 input 中的过去日期替换为未来 1 个月内的日期
# 支持中文 / 英文 / 葡萄牙语 三种语言，自动识别语言后按对应格式输出
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

def _future_date(min_days=1, max_days=30, ref=None):
    """返回未来 [min_days, max_days] 范围内的一个 date（北京时区日历日）"""
    ref = ref or _dt.utcnow() + _td(hours=8)  # 用北京时间做参考
    delta = _random.randint(min_days, max_days)
    return (ref + _td(days=delta)).date()

def _fmt_date(d: _dt, lang: str, day_pad: bool = False) -> str:
    """按语言格式化日期（不含时间）"""
    if lang == 'zh':
        return f"{d.year}年{d.month}月{d.day}日"
    if lang == 'pt':
        mname = _PT_MONTHS[d.month - 1]
        day = f"{d.day:02d}" if day_pad else str(d.day)
        return f"{day} de {mname} de {d.year}"
    # en
    mname = _EN_MON_ABBR[d.month - 1]
    return f"{d.day:02d} {mname} {d.year}"

def _replace_all_dates(text: str) -> tuple:
    """替换文本中所有过去日期为未来日期。
    返回 (new_text, replaced_count)。
    同一条文本中，日期按先后顺序替换；check-in 先随机，check-out 在 check-in 之后至少 1 天。
    时间部分（HH:MM）原样保留。
    """
    lang = _detect_lang(text)

    # 收集所有日期匹配：(start, end, parser_func, formatter_func, time_suffix)
    # 每个 parser 返回 date 对象或 None；formatter 接收 date 返回字符串
    matches = []

    # --- 1. 中文 yyyy年m月d日[ H:MM / HH:MM] ---
    zh_pat = _re.compile(
        r'(\d{4})年(\d{1,2})月(\d{1,2})日(?:\s*(\d{1,2}:\d{2}))?'
    )
    for m in zh_pat.finditer(text):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            dt_obj = _dt(y, mo, d).date()
        except ValueError:
            continue
        time_part = m.group(4)
        def _fmt_zh(d, tp=time_part):
            base = _fmt_date(d, 'zh')
            return base + (tp if tp else '')
        matches.append((m.start(), m.end(), dt_obj, _fmt_zh))

    # --- 2. 葡语 d de mês de yyyy[ às HH:MM] ---
    pt_pat = _re.compile(
        r'(\d{1,2})\s+de\s+([a-zç]+)\s+de\s+(\d{4})(?:\s+às\s+(\d{1,2}:\d{2}))?',
        _re.IGNORECASE
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
        day_pad = (len(m.group(1)) == 2)  # 原文 2 位日就保持 2 位
        def _fmt_pt(d, tp=time_part, pad=day_pad):
            day = f"{d.day:02d}" if pad else str(d.day)
            base = f"{day} de {_PT_MONTHS[d.month - 1]} de {d.year}"
            return base + (f" às {tp}" if tp else '')
        matches.append((m.start(), m.end(), dt_obj, _fmt_pt))

    # --- 3. 英文 dd Mmm yyyy[ at HH:MM] ---
    en_pat = _re.compile(
        r'(\d{1,2})\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
        r'Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'
        r'\s+(\d{4})(?:\s+at\s+(\d{1,2}:\d{2}))?',
        _re.IGNORECASE
    )
    for m in en_pat.finditer(text):
        d, mname, y = int(m.group(1)), m.group(2)[:3].lower(), int(m.group(3))
        if mname not in _EN_MON_ABBR:
            continue
        mo = _EN_MON_ABBR.index(mname) + 1
        try:
            dt_obj = _dt(y, mo, d).date()
        except ValueError:
            continue
        time_part = m.group(4)
        day_pad = (len(m.group(1)) == 2)
        # 保留原文月份首字母大小写（Sep/SEP/september 等）
        orig_month = m.group(2)
        def _fmt_en(d, tp=time_part, pad=day_pad, om=orig_month):
            day = f"{d.day:02d}" if pad else str(d.day)
            # 若原文是 3 字母缩写（Sep），用缩写；若全拼（September），用全拼；首字母大写
            if len(om) <= 4:
                m_str = _EN_MON_ABBR[d.month - 1].capitalize()
            else:
                m_str = _EN_MONTHS[d.month - 1].capitalize()
            base = f"{day} {m_str} {d.year}"
            return base + (f" at {tp}" if tp else '')
        matches.append((m.start(), m.end(), dt_obj, _fmt_en))

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
        def _fmt_iso(d, mp=mo_pad, dp=d_pad):
            m_str = f"{d.month:02d}" if mp else str(d.month)
            d_str = f"{d.day:02d}" if dp else str(d.day)
            return f"{d.year}-{m_str}-{d_str}"
        # iso 格式常见于英文/葡语
        matches.append((m.start(), m.end(), dt_obj, _fmt_iso))

    # --- 5. M/D/YYYY (美式，中文 query 里也出现过) ---
    # 不用 \b 因为中文字符旁 \b 不生效；用 (?<!\d) 防止和 yyyy-mm-dd 的片段误匹配
    md_pat = _re.compile(r'(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)')
    for m in md_pat.finditer(text):
        mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # 合理性检查：月 1-12，日 1-31，年 >= 2020（避免把其他数字/分数误判）
        if not (1 <= mo <= 12 and 1 <= d <= 31 and y >= 2020):
            continue
        # 避免和 yyyy-mm-dd 重叠（已在 iso_pat 中处理）：前一个字符不能是 '-'
        if m.start() > 0 and text[m.start() - 1] == '-':
            continue
        try:
            dt_obj = _dt(y, mo, d).date()
        except ValueError:
            continue
        mo_pad = (len(m.group(1)) == 2)
        d_pad = (len(m.group(2)) == 2)
        def _fmt_md(d, mp=mo_pad, dp=d_pad):
            m_str = f"{d.month:02d}" if mp else str(d.month)
            d_str = f"{d.day:02d}" if dp else str(d.day)
            return f"{m_str}/{d_str}/{d.year}"
        matches.append((m.start(), m.end(), dt_obj, _fmt_md))

    # 去重 & 排序：可能存在重叠（比如 iso 和 md 都可能匹配类似片段，但 iso 有连字符不会和 / 冲突）
    # 按 start 排序，如果 start 相同取更长的
    matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    dedup = []
    last_end = -1
    for s, e, dt_obj, fmt in matches:
        if s >= last_end:
            dedup.append((s, e, dt_obj, fmt))
            last_end = e
    matches = dedup

    if not matches:
        return text, 0

    today = (_dt.utcnow() + _td(hours=8)).date()

    # 判断文本是否"明显是过去事件"，只要存在过去日期就全部替换为未来
    # 策略：第一个日期分配一个未来基准日；后续日期如果在原文本中在它之后，保持相对间隔
    # 为简单稳定：对每个日期独立生成未来 1-30 天的随机日期；
    # 若文本同时含 check-in / check-out（或"入住"/"退房"、entrada/saída），做特殊处理保证 out > in。

    # 先检测 check-in/out 对
    # 中文: 入住/到店/抵达 + 退房/离店/离开
    # 英文: check-in/check-in on + check-out/check-out on
    # 葡语: check-in/entrada + check-out/saída
    date_spans = [(s, e) for s, e, _, _ in matches]

    def _find_pair(keywords_in, keywords_out):
        """找 (check-in idx, check-out idx) in matches"""
        in_idx = out_idx = None
        for i, (s, e, _, _) in enumerate(matches):
            before = text[max(0, s-40):s].lower()
            if in_idx is None and any(k in before for k in keywords_in):
                in_idx = i
            elif in_idx is not None and out_idx is None and any(k in before for k in keywords_out):
                out_idx = i
                break
        return in_idx, out_idx

    ci_idx, co_idx = None, None
    if lang == 'zh':
        ci_idx, co_idx = _find_pair(['入住','到店','抵达','接机','接'], ['退房','离店','离开','送机'])
    elif lang == 'en':
        ci_idx, co_idx = _find_pair(['check in','check-in','checkin','arriving','arrival','pickup'],
                                    ['check out','check-out','checkout','departure','dropoff','drop-off'])
    else:
        ci_idx, co_idx = _find_pair(['check in','check-in','checkin','entrada','chegada','em '],
                                    ['check out','check-out','checkout','saída','saida'])

    # 生成未来日期
    new_dates = {}
    if ci_idx is not None and co_idx is not None and co_idx != ci_idx:
        # 先分配 check-in，再保证 check-out 在其之后
        ci_new = _future_date(2, 25)
        stay = _random.randint(1, 7)
        co_new = ci_new + _td(days=stay)
        new_dates[ci_idx] = ci_new
        new_dates[co_idx] = co_new

    for i, (s, e, dt_obj, fmt) in enumerate(matches):
        if i in new_dates:
            continue
        # 如果是未来且距今 > 90 天的日期（比如 2099、2100），也替换
        is_past = dt_obj < today
        is_far_future = (dt_obj - today).days > 90
        if is_past or is_far_future:
            # 检查是否应该基于前一个日期顺延
            new_dates[i] = _future_date(1, 30)
        # else: 未来 90 天内的日期不动

    # 按 start 从后往前替换，避免位置偏移
    result = text
    replaced = 0
    for i in reversed(range(len(matches))):
        s, e, dt_obj, fmt = matches[i]
        if i in new_dates:
            new_str = fmt(new_dates[i])
            result = result[:s] + new_str + result[e:]
            replaced += 1

    return result, replaced


def refresh_dates_in_text(text: str) -> tuple:
    """刷新单条文本中的过去日期，返回 (new_text, replaced_count)。
    多轮用例的每个 turn 应分别调用。
    """
    if not isinstance(text, str) or not text.strip():
        return text, 0
    return _replace_all_dates(text)


def refresh_dates_for_records(records: list) -> tuple:
    """批量刷新一组测试用例记录（df.to_dict('records') 形式）中的日期。
    同时更新 input 字段；返回 (updated_records, total_replaced)。
    """
    total = 0
    updated = []
    for r in records:
        new_r = dict(r)
        inp = new_r.get('input', '')
        new_inp, n = refresh_dates_in_text(inp)
        if n > 0:
            new_r['input'] = new_inp
            total += n
        updated.append(new_r)
    return updated, total
