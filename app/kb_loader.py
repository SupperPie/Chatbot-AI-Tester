"""Knowledge Base 多格式加载器。

把用户上传的多种文本 / 表格 / 图片文件统一解析为 Markdown 文本，
注入 Tester 页面的 Knowledge Base，供大模型生成测试用例使用。

支持格式（按扩展名分发）：
- .md / .txt / .text / .markdown   纯文本与 Markdown
- .csv / .xlsx / .xlsm / .xls       表格 -> Markdown 表格
- .docx                            Word 文档 -> 文本（含表格）
- .pdf                             文本型 PDF 抽取文本；扫描件渲染成图片走视觉模型
- .png / .jpg / .jpeg / .webp / .gif / .bmp   图片走多模态视觉模型

视觉抽取优先使用多模态大模型（默认 qwen3-vl-plus）直接“看懂”图片/扫描件，
还原表格结构与语义，不依赖传统 OCR 引擎。
"""

import io
import os
import base64

import pandas as pd

# 表格转 Markdown 时的最大行数，避免超长知识污染 prompt
MAX_TABLE_ROWS = 300
# PDF 判定为“扫描件”的文本字符阈值（低于则认为没有可抽取文本层）
PDF_TEXT_MIN_CHARS = 50
# 扫描版 PDF 最多渲染的页数（避免逐页调用视觉模型开销过大）
PDF_MAX_RENDER_PAGES = 10
PDF_RENDER_DPI = 150

# 视觉模型默认值：qwen3-vl-plus（阿里云百炼 OpenAI 兼容接口示例所用视觉模型）
DEFAULT_VISION_MODEL = "qwen3-vl-plus"

# 发给视觉模型的抽取指令
VISION_PROMPT = """请把这张图片中的内容完整、准确地转录为 Markdown 文本。

要求：
1. 若图片中包含表格，用 Markdown 表格语法还原，保留表头、行列关系与每个单元格内容。
2. 若是流程图/界面截图/示意图，忠实转录其中的文字，并简要说明结构关系。
3. 纯文字内容直接转录，保留层级（标题、列表）。
4. 只输出转录结果本身，不要任何解释、前言或客套话。"""


def _decode_text(raw: bytes) -> str:
    """按常见编码顺序解码文本字节。"""
    for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="ignore")


def _df_to_markdown(df: "pd.DataFrame") -> str:
    """把 DataFrame 转成 Markdown 表格文本（不依赖 tabulate）。"""
    if df is None or df.empty:
        return ""
    df = df.copy()
    df.columns = [str(c) for c in df.columns]
    cols = df.columns.tolist()
    if len(cols) > 30:
        cols = cols[:30]

    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"

    rows = []
    total = len(df)
    for _, r in df.head(MAX_TABLE_ROWS).iterrows():
        cells = []
        for c in cols:
            v = r.get(c, "")
            v = "" if (v is None or (isinstance(v, float) and pd.isna(v))) else str(v)
            cells.append(v.replace("|", "\\|").replace("\n", " ").strip())
        rows.append("| " + " | ".join(cells) + " |")

    out = "\n".join([header, sep] + rows)
    if total > MAX_TABLE_ROWS:
        out += f"\n\n[... 共 {total} 行，仅展示前 {MAX_TABLE_ROWS} 行 ...]"
    return out


def _read_csv(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            df = pd.read_csv(io.BytesIO(raw), encoding=enc, dtype=str)
            return _df_to_markdown(df)
        except Exception:
            continue
    return ""


def _read_excel(raw: bytes) -> str:
    sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None, dtype=str)
    parts = []
    for sheet_name, df in sheets.items():
        if df is None or df.empty:
            continue
        df = df.dropna(how="all").dropna(axis=1, how="all")
        if df.empty:
            continue
        parts.append(f"### 工作表：{sheet_name}\n{_df_to_markdown(df)}")
    return "\n\n".join(parts)


def _read_docx(raw: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(raw))
    parts = []
    for p in doc.paragraphs:
        t = p.text.strip()
        if t:
            parts.append(t)
    for table in doc.tables:
        rows = []
        for row in table.rows:
            cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            rows.append(cells)
        if rows:
            if len(rows) > 1:
                df = pd.DataFrame(rows[1:], columns=rows[0])
            else:
                df = pd.DataFrame(rows)
            parts.append(_df_to_markdown(df))
    return "\n\n".join(parts)


def _vision_extract(image_bytes: bytes, mime: str = "image/png") -> str:
    """用多模态视觉模型抽取图片内容为 Markdown 文本。"""
    api_key = os.getenv("COMPATIBLE_API_KEY")
    base_url = os.getenv("COMPATIBLE_BASE_URL")
    if not api_key:
        return ""
    model = os.getenv("COMPATIBLE_VISION_MODEL", DEFAULT_VISION_MODEL)

    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url)
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": VISION_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
    )
    return (resp.choices[0].message.content or "").strip()


def _read_scanned_pdf(doc) -> str:
    """扫描版 PDF：逐页渲染成图片后走视觉模型。"""
    parts = []
    total = len(doc)
    for i, page in enumerate(doc):
        if i >= PDF_MAX_RENDER_PAGES:
            parts.append(f"\n\n[... 共 {total} 页，仅解析前 {PDF_MAX_RENDER_PAGES} 页 ...]")
            break
        pix = page.get_pixmap(dpi=PDF_RENDER_DPI)
        txt = _vision_extract(pix.tobytes("png"), "image/png")
        parts.append(txt.strip())
    return "\n\n".join(parts)


def _read_pdf(raw: bytes) -> str:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=raw, filetype="pdf")
    texts = [page.get_text() or "" for page in doc]
    full = "\n\n".join(texts).strip()
    if len(full) >= PDF_TEXT_MIN_CHARS:
        return full
    # 无足够文本层，判定为扫描件，走视觉模型
    return _read_scanned_pdf(doc)


_MIME_BY_EXT = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
    "bmp": "image/bmp",
}

_TEXT_EXTS = {"md", "txt", "text", "markdown"}
_TABLE_EXTS = {"xlsx", "xlsm", "xls"}
_IMAGE_EXTS = set(_MIME_BY_EXT.keys())


def load_uploaded_file(uploaded_file) -> str:
    """解析一个上传文件，返回其文本表示（Markdown）。"""
    name = getattr(uploaded_file, "name", "") or ""
    ext = os.path.splitext(name)[1].lower().lstrip(".")
    raw = uploaded_file.getvalue()

    if ext in _TEXT_EXTS:
        return _decode_text(raw).strip()
    if ext == "csv":
        return _read_csv(raw).strip()
    if ext in _TABLE_EXTS:
        return _read_excel(raw).strip()
    if ext == "docx":
        return _read_docx(raw).strip()
    if ext == "pdf":
        return _read_pdf(raw).strip()
    if ext in _IMAGE_EXTS:
        mime = getattr(uploaded_file, "type", "") or _MIME_BY_EXT[ext]
        return _vision_extract(raw, mime).strip()

    # 兜底：按文本解码
    return _decode_text(raw).strip()