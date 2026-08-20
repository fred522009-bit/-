import os
import re
import sys
import pdfplumber
import streamlit as st
from bluehole_scan import repair_company_name

# 1. 무조건 최상단에 위치해야 합니다.
st.set_page_config(page_title="파일명 변경 및 블루홀 업로드기", layout="wide")

# 2. 우측 하단 뱃지 및 메뉴 전체 숨기기 CSS
hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    [data-testid="stDecoration"] {display: none;}
    [data-testid="stStatusWidget"] {display: none;}
    [data-testid="stToolbar"] {display: none;}
    div[class*="viewerBadge"] {display: none !important;}
    div[class*="stActionButton"] {display: none !important;}
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

st.markdown(
    """
    <style>
    .stApp { background: #F3F7FC; }
    header[data-testid="stHeader"] { background: #1B4F9C; }
    .block-container { padding-top: 5.4rem; }
    .bh-topbar {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        z-index: 999999;
        background: linear-gradient(90deg, #163A78 0%, #1B4F9C 55%, #2B6CB0 100%);
        color: #ffffff;
        font-size: 1.45rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        padding: 14px 28px 14px 4.5rem;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 12px;
        box-shadow: 0 4px 16px rgba(22, 58, 120, 0.28);
    }
    .bh-topbar .logo {
        font-size: 1.7rem;
        line-height: 1;
    }
    .bh-topbar .title-wrap {
        display: flex;
        flex-direction: column;
        gap: 2px;
    }
    .bh-topbar .sub {
        font-size: 0.78rem;
        font-weight: 500;
        opacity: 0.88;
        letter-spacing: 0;
    }
    .stTabs [data-baseweb="tab-list"] {
        background: #ffffff;
        border-radius: 12px;
        padding: 8px 16px;
        gap: 24px;
        justify-content: flex-start;
        border: 1px solid #d5e4f4;
        box-shadow: 0 2px 8px rgba(27, 79, 156, 0.06);
    }
    .stTabs [data-baseweb="tab"] {
        color: #2B6CB0;
        font-weight: 600;
        padding: 10px 28px;
        min-width: 160px;
    }
    .stTabs [aria-selected="true"] { background: #E8F1FB; border-radius: 8px; }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: #ffffff;
        border: 1px solid #d5e4f4;
        border-radius: 12px;
    }
    .stButton > button {
        background: #2B6CB0;
        color: #ffffff;
        border: 0;
        border-radius: 8px;
        font-weight: 600;
    }
    .stButton > button:hover { background: #1B4F9C; color: #ffffff; }
    [data-testid="stDataFrame"] { width: 100%; }
    iframe[title="st.iframe"] { border: 0 !important; }
    .period-add [data-testid="stSelectbox"] { max-width: 130px; }
    .period-chips [data-testid="stHorizontalBlock"] {
        justify-content: flex-start !important;
        gap: 8px !important;
        flex-wrap: wrap !important;
    }
    .period-chips [data-testid="column"] {
        width: auto !important;
        flex: 0 0 auto !important;
        min-width: fit-content !important;
        max-width: 160px !important;
        padding: 0 !important;
    }
    .period-chips button {
        padding: 4px 12px !important;
        min-height: 32px !important;
        font-size: 0.85rem !important;
        border-radius: 16px !important;
        font-weight: 600 !important;
        width: auto !important;
        white-space: nowrap !important;
    }
    [data-testid="stFileUploaderDropzoneInstructions"] > div > span:nth-child(1) {
        font-size: 0 !important;
        white-space: normal !important;
    }
    [data-testid="stFileUploaderDropzoneInstructions"] > div > span:nth-child(1)::before {
        content: "PDF 파일이나 폴더를 이곳에 끌어다 놓으세요.";
        font-size: 1rem;
        font-weight: 600;
        color: #1A365D;
        white-space: normal;
    }
    [data-testid="stFileUploaderDropzoneInstructions"] > div > span:nth-child(2) {
        font-size: 0 !important;
    }
    [data-testid="stFileUploaderDropzoneInstructions"] > div > span:nth-child(2)::before {
        content: "(200MB 제한이 있습니다)";
        font-size: 0.85rem;
        color: #4A5568;
    }
    [data-testid="stFileUploaderDropzone"] button {
        font-size: 0 !important;
    }
    [data-testid="stFileUploaderDropzone"] button::after {
        content: "찾아보기";
        font-size: 0.875rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="bh-topbar"><span class="logo">📂</span><span class="title-wrap">'
    '<span>파일명 변경 및 블루홀 업로드기</span>'
    '<span class="sub">지급명세서 · 원천세 · 블루홀</span></span></div>',
    unsafe_allow_html=True,
)

desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
default_output = os.path.join(desktop_path, "지급명세서_변경완료")
default_wht_output = os.path.join(desktop_path, "원천세_변경완료")
RENAME_MODE_RECEIPT = "(간이)지급명세서"
RENAME_MODE_WHT = "원천세"
RENAME_MODES = [RENAME_MODE_RECEIPT, RENAME_MODE_WHT]

INCOME_KEYWORDS = [
    ("일용", "일용"),
    ("사업소득", "사업"),
    ("근로소득", "근로"),
    ("퇴직", "퇴직"),
    ("연금", "연금"),
    ("이자", "이자"),
    ("배당", "배당"),
    ("기타소득", "기타"),
    ("사업", "사업"),
    ("근로", "근로"),
    ("기타", "기타"),
]


def init_state():
    defaults = {
        "uploader_key": 0,
        "pdf_items": [],
        "preview_list": None,
        "output_folder": default_output,
        "last_result": None,
        "rename_mode": RENAME_MODE_RECEIPT,
        "uploader_key_wht": 0,
        "pdf_items_wht": [],
        "preview_list_wht": None,
        "output_folder_wht": default_wht_output,
        "rename_period_labels": ["26년01월"],
        "rename_period_rows": [{"id": 0, "year": 2026, "month": 1}],
        "rename_period_next_id": 1,
        "rename_mode_all": RENAME_MODE_RECEIPT,
        "uploader_key_all": 0,
        "pdf_items_all": [],
        "preview_list_all": None,
        "output_folder_all": default_output,
        "uploader_key_wht_all": 0,
        "pdf_items_wht_all": [],
        "preview_list_wht_all": None,
        "output_folder_wht_all": default_wht_output,
        "last_result_all": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def unique_path(folder: str, filename: str) -> str:
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(folder, filename)
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{base}_{counter}{ext}")
        counter += 1
    return candidate


def extract_pdf_text_and_tables(pdf_bytes: bytes) -> tuple[str | None, list, str]:
    text = ""
    tables = []
    try:
        import io

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text += page_text + "\n"
                for table in page.extract_tables() or []:
                    tables.append(table)
    except Exception as e:
        return None, [], f"PDF 읽기 오류: {str(e)}"

    if not text.strip() and not tables:
        return None, [], "텍스트를 읽을 수 없음 (스캔본)"

    return text, tables, "성공"


COMPANY_STOP_RE = (
    r"지급연도|귀속연도|귀속\s*연도|귀속월|지급월|지급시기|지급자|제출구분|"
    r"건수|총\s*지급액|사업자|대표자|상호|접수|명세서|납부기한|과세대상|등록번호|납세자번호|전자납부"
)


def flatten_tables(tables: list) -> list[str]:
    cells = []
    for table in tables:
        for row in table or []:
            for cell in row or []:
                raw = cell or ""
                if "\n" in raw:
                    parts = []
                    for line in raw.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        if re.match(rf"^({COMPANY_STOP_RE})", line):
                            break
                        parts.append(line)
                    value = repair_company_name("\n".join(parts)) if parts else ""
                else:
                    value = re.sub(r"\s+", " ", raw).strip()
                if value:
                    cells.append(value)
    return cells


def _is_name_continuation(cell: str) -> bool:
    text = (cell or "").strip()
    if not text or len(text) > 40:
        return False
    if re.match(rf"^({COMPANY_STOP_RE})", text):
        return False
    if re.match(r"^\d{2,4}(\s*년)?$", text):
        return False
    return bool(re.match(r"^[가-힣A-Za-z(]", text))


def value_after_label(cells: list[str], labels: list[str], take_continuations: bool = False) -> str | None:
    for i, cell in enumerate(cells):
        compact = re.sub(r"\s+", "", cell)
        for label in labels:
            label_compact = re.sub(r"\s+", "", label)
            value = None
            if compact == label_compact and i + 1 < len(cells):
                value = cells[i + 1]
                next_index = i + 2
            elif compact.startswith(label_compact) and compact != label_compact:
                value = cell[len(label) :].strip(" :")
                next_index = i + 1
            if value is None:
                continue
            if take_continuations:
                parts = [value]
                while next_index < len(cells) and _is_name_continuation(cells[next_index]):
                    parts.append(cells[next_index])
                    next_index += 1
                return repair_company_name("\n".join(parts))
            return value
    return None


def value_from_text(text: str, labels: list[str], stop: str) -> str | None:
    for label in labels:
        pattern = rf"{label}\s*[:\s]*([^\n]+?)(?=\s*(?:{stop})|$)"
        match = re.search(pattern, text)
        if match:
            value = match.group(1).strip()
            if value:
                return value
    return None


def extract_income_type(text: str, original_filename: str, cells: list[str]) -> str:
    kind = value_after_label(cells, ["(지급)명세서 종류", "명세서 종류"]) or ""
    kind_match = re.search(
        r"\(지급\)명세서\s*종류\s*[:\s]*([^\n]+)|명세서\s*종류\s*[:\s]*([^\n]+)",
        text,
    )
    if kind_match:
        kind = kind or (kind_match.group(1) or kind_match.group(2) or "").strip()

    for source in (kind, original_filename, text):
        for keyword, short_name in INCOME_KEYWORDS:
            if keyword in source:
                return short_name
    return "기타"


def extract_doc_prefix(text: str) -> str:
    if "간이지급명세서" in text:
        return "(간이)지급명세서접수증"
    if "지급명세서" in text:
        return "지급명세서접수증"
    return "(간이)지급명세서접수증"


def extract_payment_period(text: str, cells: list[str]) -> str:
    year_raw = value_after_label(cells, ["지급연도", "귀속연도"]) or value_from_text(
        text,
        [r"지급연도", r"귀속연도", r"귀속\s*연도"],
        r"지급월|지급시기|제출구분|건수|총\s*지급액|상호",
    )
    month_raw = value_after_label(cells, ["지급월", "지급시기"]) or value_from_text(
        text,
        [r"지급월", r"지급시기"],
        r"지급연도|건수|총\s*지급액|상호|제출구분",
    )

    year = None
    if year_raw:
        year_match = re.search(r"(\d{4}|\d{2})", year_raw)
        if year_match:
            year = year_match.group(1)[-2:]

    period = None
    if month_raw:
        half_match = re.search(r"(상반기|하반기)", month_raw)
        month_match = re.search(r"(\d{1,2})\s*월", month_raw)
        if half_match:
            period = half_match.group(1)
        elif month_match:
            period = f"{int(month_match.group(1)):02d}월"

    if year and period:
        return f"{year}년{period}"
    if year:
        return f"{year}년"
    if period:
        return period
    return "날짜미상"


def extract_is_amended(text: str, original_filename: str, cells: list[str]) -> bool:
    submit_type = value_after_label(cells, ["제출구분"]) or ""
    if not submit_type:
        submit_type = value_from_text(
            text,
            [r"제출구분"],
            r"지급자|상호|지급연도|지급월|건수|총\s*지급액|명세서\s*종류",
        ) or ""
    return "수정신고" in submit_type or "수정신고" in original_filename


def extract_company_name(text: str, cells: list[str]) -> str:
    company = value_after_label(cells, ["상호(법인명)", "상호 (법인명)", "상호"], take_continuations=True)
    if not company:
        company = company_from_raw_text(text)

    if not company:
        return "상호명미상"

    company = re.split(
        r"지급연도|귀속연도|귀속\s*연도|귀속월|지급월|지급시기|지급자|제출구분",
        company,
    )[0]
    company = repair_company_name(sanitize_filename(company))
    company = re.sub(r"귀속연도.*$", "", company).strip()
    if len(company) > 40:
        company = company[:40]
    return company or "상호명미상"


def company_from_raw_text(text: str) -> str | None:
    match = re.search(r"상호\s*(?:\(\s*법인명\s*\))?\s*[:\s]*", text)
    if not match:
        return None
    lines = []
    for raw in text[match.end() :].splitlines():
        line = raw.strip()
        if not line:
            if lines:
                break
            continue
        if re.match(rf"^({COMPANY_STOP_RE})", line):
            break
        lines.append(line)
        joined = repair_company_name("\n".join(lines))
        if "(" in joined and ")" in joined:
            break
        if len(lines) >= 3:
            break
    if not lines:
        return None
    return repair_company_name("\n".join(lines))


def normalize_period(period_str: str) -> str:
    text = (period_str or "").strip()
    match = re.match(r"(\d{2})년(\d{1,2})월$", text)
    if match:
        return f"{match.group(1)}년{int(match.group(2)):02d}월"
    return text


def period_from_year_month(year: int, month: int) -> str:
    return f"{int(year) % 100:02d}년{int(month):02d}월"


def selected_period_labels() -> list[str]:
    labels = list(st.session_state.get("rename_period_labels") or [])
    return labels or ["26년01월"]


def is_keep_period(period_str: str, selected: list[str] | None = None) -> bool:
    allowed = [normalize_period(item) for item in (selected or []) if item]
    if not allowed:
        return False
    period = normalize_period(period_str)
    if period in allowed:
        return True
    half = re.match(r"(\d{2})년하반기$", period)
    if half:
        return any(
            (match := re.match(r"(\d{2})년(\d{2})월$", item))
            and match.group(1) == half.group(1)
            and int(match.group(2)) >= 7
            for item in allowed
        )
    upper = re.match(r"(\d{2})년상반기$", period)
    if upper:
        return any(
            (match := re.match(r"(\d{2})년(\d{2})월$", item))
            and match.group(1) == upper.group(1)
            and int(match.group(2)) <= 6
            for item in allowed
        )
    return False


def period_group(period_str: str, selected: list[str] | None = None, keep_all: bool = False) -> str | None:
    if keep_all:
        return normalize_period(period_str) or "날짜미상"
    if not is_keep_period(period_str, selected):
        return None
    return normalize_period(period_str) or None


def skip_reason(
    period_str: str,
    amended: bool,
    selected: list[str] | None = None,
    keep_all: bool = False,
) -> str | None:
    if amended:
        return "수정신고 제외"
    if keep_all:
        return None
    if not is_keep_period(period_str, selected):
        labels = ", ".join(selected or selected_period_labels()) or "선택한 기간"
        return f"대상 기간 아님 ({labels}만 저장)"
    return None


def parse_receipt_pdf(
    pdf_bytes: bytes,
    original_filename: str,
    selected: list[str] | None = None,
    keep_all: bool = False,
) -> dict:
    text, tables, status = extract_pdf_text_and_tables(pdf_bytes)
    if text is None:
        return {
            "filename": None,
            "company": "상호명미상",
            "status": status,
            "keep": False,
            "reason": status,
            "period_group": "",
        }

    cells = flatten_tables(tables)
    if classify_withholding(text, original_filename):
        return parse_withholding_pdf(pdf_bytes, original_filename, selected, keep_all)

    doc_prefix = extract_doc_prefix(text)
    income_type = extract_income_type(text, original_filename, cells)
    period_str = extract_payment_period(text, cells)
    company_name = extract_company_name(text, cells)
    amended = extract_is_amended(text, original_filename, cells)

    new_filename = f"{doc_prefix}({income_type}) {period_str}_{company_name}.pdf"
    reason = skip_reason(period_str, amended, selected, keep_all=keep_all)
    keep = reason is None

    return {
        "filename": sanitize_filename(new_filename),
        "company": company_name,
        "status": "성공" if keep else reason,
        "keep": keep,
        "reason": reason or "저장",
        "period_group": period_group(period_str, selected, keep_all=keep_all) if keep else "",
    }


def _yy_mm(year: str, month: str) -> str:
    return f"{year[-2:]}년{int(month):02d}월"


def extract_local_tax_period(text: str) -> str | None:
    match = re.search(r"(20\d{2})\s*년\s*(\d{1,2})\s*월\s*신고\s*납부", text)
    if match:
        return _yy_mm(match.group(1), match.group(2))
    belong = re.search(r"(20\d{2})\s*년\s*(\d{1,2})\s*월\s*귀속", text)
    if belong:
        return _yy_mm(belong.group(1), belong.group(2))
    return None


def extract_withholding_period(
    text: str,
    cells: list[str],
    original_filename: str = "",
    prefix: str | None = None,
) -> str:
    is_local = (prefix or "").startswith("지방세") or "지방소득세" in text or (
        "지방세" in original_filename and "원천세" not in original_filename
    )
    if is_local:
        local = extract_local_tax_period(text)
        if local:
            return local
    else:
        raw = value_after_label(cells, ["지급연월", "③ 지급연월"]) or value_from_text(
            text,
            [r"③\s*지급연월", r"지급연월"],
            r"상호|신고구분|접수|사업자|납부세액|제출연월|귀속연월",
        )
        if not raw and prefix and "납부서" in prefix:
            raw = value_after_label(cells, ["연도/기분", "연도/기 분"]) or value_from_text(
                text,
                [r"연도/기분"],
                r"상호|세목|납부금액|납부기한",
            )
        if raw:
            month_match = re.search(r"(20\d{2}|\d{2})\s*[-./년]?\s*(\d{1,2})", raw)
            if month_match:
                return _yy_mm(month_match.group(1), month_match.group(2))
    name_match = re.search(r"(\d{2})년(\d{1,2})월", original_filename)
    if name_match:
        return f"{name_match.group(1)}년{int(name_match.group(2)):02d}월"
    return "날짜미상"


def classify_withholding(text: str, original_filename: str) -> str | None:
    named = re.match(
        r"^(원천세납부서\([^)]+\)|원천세신고서|원천세접수증|지방세납부서|지방세접수증)",
        os.path.splitext(original_filename)[0],
    )
    if named:
        return named.group(1)
    blob = f"{original_filename}\n{text}"
    if "지방소득세접수증" in blob or "지방소득세 특별징수 신고결과" in blob or "지방소득세특별징수 신고결과" in blob:
        return "지방세접수증"
    if "지방소득세납부서" in blob or ("지방소득세" in blob and "납부서" in blob):
        return "지방세납부서"
    if "원천세 신고서 접수증" in blob or ("원천세" in blob and "접수증" in blob and "지방" not in original_filename):
        return "원천세접수증"
    if "원천징수이행상황신고서" in blob or ("신고서" in original_filename and "정기신고" in original_filename):
        return "원천세신고서"
    if "납부서" in blob:
        if "사업소득세" in blob or "납부서(2)_사업" in original_filename:
            return "원천세납부서(사업)"
        if "근로소득세" in blob or "납부서_근로" in original_filename or "근로소득세(갑)" in blob:
            return "원천세납부서(근로)"
        return "원천세납부서(근로)"
    return None


def extract_withholding_company(text: str, cells: list[str], original_filename: str) -> str:
    company = value_after_label(
        cells,
        ["법인명(상호)", "상호(성명)", "상호(법인명)", "상호", "사업장명", "납세자"],
        take_continuations=True,
    )
    if not company:
        company = extract_company_name(text, cells)
    if not company or company == "상호명미상":
        stem = os.path.splitext(os.path.basename(original_filename))[0]
        if "_" in stem:
            company = stem.rsplit("_", 1)[-1]
    company = re.sub(r"\([A-Za-z][^)]*\)", "", company)
    company = re.sub(r"\([^)]*$", "", company or "")
    company = (company or "").split("(")[0] if re.search(r"\([A-Za-z]", company or "") else (company or "").split("(")[0]
    company = re.split(
        r"사업자|대표자|신고구분|귀속연월|성명/법인|납부기한|과세대상|등록번호|납세자번호|전자납부|세목|주소|일반회계",
        company,
    )[0]
    company = re.sub(r"[A-Za-z].*$", "", company)
    company = re.sub(r"\s+", "", sanitize_filename(company))
    if len(company) > 40:
        company = company[:40]
    return company or "상호명미상"


def parse_withholding_pdf(
    pdf_bytes: bytes,
    original_filename: str,
    selected: list[str] | None = None,
    keep_all: bool = False,
) -> dict:
    text, tables, status = extract_pdf_text_and_tables(pdf_bytes)
    if text is None:
        return {
            "filename": None,
            "company": "상호명미상",
            "status": status,
            "keep": False,
            "reason": status,
            "period_group": "",
        }

    cells = flatten_tables(tables)
    prefix = classify_withholding(text, original_filename)
    company_name = extract_withholding_company(text, cells, original_filename)
    period_str = extract_withholding_period(text, cells, original_filename, prefix)
    if not prefix:
        return {
            "filename": None,
            "company": company_name,
            "status": "원천세·지방세 종류를 알아보지 못했습니다.",
            "keep": False,
            "reason": "종류 미상",
            "period_group": "",
        }

    new_filename = f"{prefix} {normalize_period(period_str)}_{company_name}.pdf"
    reason = skip_reason(period_str, False, selected, keep_all=keep_all)
    keep = reason is None
    return {
        "filename": sanitize_filename(new_filename),
        "company": company_name,
        "status": "성공" if keep else reason,
        "keep": keep,
        "reason": reason or "저장",
        "period_group": period_group(period_str, selected, keep_all=keep_all) if keep else "",
    }


def render_period_picker() -> list[str]:
    if "rename_period_labels" not in st.session_state:
        rows = st.session_state.get("rename_period_rows") or []
        labels = []
        for row in rows:
            labels.append(period_from_year_month(row.get("year") or 2026, row.get("month") or 1))
        st.session_state.rename_period_labels = labels or ["26년01월"]

    st.markdown("**추출할 년도·월**")
    st.caption("년도·월을 고른 뒤 **추가**를 누르면 바로 옆에 붙습니다. 일괄 변경은 고른 기간만, 모두 변경 실행은 날짜 상관없이 저장합니다.")
    years = list(range(2020, 2032))
    with st.container(horizontal=True, gap="small", width="content"):
        year = st.selectbox(
            "년도",
            years,
            index=years.index(2026),
            key="rp_add_year",
            label_visibility="collapsed",
            format_func=lambda value: f"{value}년",
            width=140,
        )
        month = st.selectbox(
            "월",
            list(range(1, 13)),
            index=0,
            key="rp_add_month",
            label_visibility="collapsed",
            format_func=lambda value: f"{value:02d}월",
            width=110,
        )
        if st.button("추가", key="rp_add"):
            label = period_from_year_month(year, month)
            labels = list(st.session_state.rename_period_labels)
            if label not in labels:
                labels.append(label)
                st.session_state.rename_period_labels = labels
            st.rerun()

    labels = list(st.session_state.rename_period_labels)
    if labels:
        with st.container(horizontal=True, gap="small", width="content"):
            for label in labels:
                if st.button(f"{label} ×", key=f"rp_chip_{label}"):
                    st.session_state.rename_period_labels = [item for item in labels if item != label]
                    st.rerun()
    return selected_period_labels()


def rename_keys(mode: str) -> dict:
    if mode == RENAME_MODE_WHT:
        return {
            "items": "pdf_items_wht",
            "preview": "preview_list_wht",
            "uploader": "uploader_key_wht",
            "output": "output_folder_wht",
            "query": "preview_company_query_wht",
            "query_last": "preview_company_query_last_wht",
            "page": "preview_table_wht_page",
            "result": "last_result",
        }
    return {
        "items": "pdf_items",
        "preview": "preview_list",
        "uploader": "uploader_key",
        "output": "output_folder",
        "query": "preview_company_query",
        "query_last": "preview_company_query_last",
        "page": "preview_table_page",
        "result": "last_result",
    }


def company_from_upload_name(filename: str) -> str:
    from bluehole_scan import company_from_filename

    stem = os.path.splitext(os.path.basename(filename))[0]
    parts = stem.split("_")
    if len(parts) >= 2 and parts[0].isdigit():
        return parts[1].strip() or company_from_filename(filename)
    return company_from_filename(filename)


def unique_upload_name(name: str, seen: set[str]) -> str:
    if name not in seen:
        return name
    base, ext = os.path.splitext(name)
    index = 1
    while f"{base}_{index}{ext}" in seen:
        index += 1
    return f"{base}_{index}{ext}"


def collect_uploaded_pdfs(uploaded_files) -> list[tuple[str, bytes]]:
    if not uploaded_files:
        return []
    if not isinstance(uploaded_files, list):
        uploaded_files = [uploaded_files]
    collected = []
    seen: set[str] = set()
    for item in uploaded_files:
        raw = str(getattr(item, "name", "") or "").replace("\\", "/")
        name = os.path.basename(raw)
        if not name.lower().endswith(".pdf"):
            continue
        name = unique_upload_name(name, seen)
        seen.add(name)
        collected.append((name, item.getvalue()))
    return collected


def merge_uploaded_files(current: list, uploaded_files) -> list:
    merged = list(current or [])
    seen = {name for name, _ in merged}
    for item in uploaded_files:
        if isinstance(item, tuple) and len(item) == 2:
            name, data = item
        else:
            name = os.path.basename(str(item.name).replace("\\", "/"))
            data = item.getvalue()
        if not str(name).lower().endswith(".pdf"):
            continue
        name = unique_upload_name(os.path.basename(str(name).replace("\\", "/")), seen)
        merged.append((name, data))
        seen.add(name)
    return merged


def ensure_pdf_name(name: str) -> str:
    cleaned = sanitize_filename(str(name or "").strip())
    if not cleaned:
        return ""
    if not cleaned.lower().endswith(".pdf"):
        cleaned += ".pdf"
    return cleaned


def action_label(keep: bool) -> str:
    return "✅ 저장" if keep else "❌ 제외"


def is_save_action(value: str) -> bool:
    text = str(value or "")
    return "저장" in text and "제외" not in text


def status_label(keep: bool, status: str) -> str:
    text = str(status or "")
    if keep:
        return "✅ 성공" if text in {"성공", "저장", "완료", ""} else f"✅ {text}"
    if text.startswith("❌"):
        return text
    return f"❌ {text or '제외'}"


def rows_from_editor(edited) -> list[dict]:
    if edited is None:
        return []
    if isinstance(edited, list):
        return edited
    return edited.to_dict("records")


def render_pdf_dropzone(kind_key: str, uploader_key: str):
    kind = st.radio(
        "올리는 방법",
        ["파일", "폴더"],
        horizontal=True,
        key=kind_key,
        help="폴더를 고르면 그 안의 PDF를 가져옵니다.",
    )
    uploaded = st.file_uploader(
        "PDF 파일 끌어다 놓기",
        type=["pdf"],
        accept_multiple_files="directory" if kind == "폴더" else True,
        key=f"{uploader_key}_{kind}",
        label_visibility="collapsed",
    )
    if kind == "폴더":
        st.caption("폴더를 선택하면 하위 폴더까지 PDF만 가져옵니다.")
    return collect_uploaded_pdfs(uploaded)


def clear_stage_files(stage: str) -> None:
    import shutil

    if not os.path.isdir(stage):
        return
    for name in os.listdir(stage):
        if name in {"last_result.json", "jobs.json"}:
            continue
        path = os.path.join(stage, name)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            try:
                os.remove(path)
            except OSError:
                pass


def apply_bh_files(items: list) -> None:
    from bluehole_scan import jobs_from_uploaded

    stage = st.session_state.bh_stage
    os.makedirs(stage, exist_ok=True)
    clear_stage_files(stage)
    st.session_state.bh_files = items
    st.session_state.bh_jobs = jobs_from_uploaded(items, stage) if items else None
    st.session_state.bh_result = None


PAGE_SIZE = 5


def page_slice(page_key: str, total: int, page_size: int = PAGE_SIZE) -> tuple[int, int, int, int]:
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
    page = int(st.session_state.get(page_key) or 1)
    page = min(max(1, page), total_pages)
    st.session_state[page_key] = page
    start = (page - 1) * page_size
    end = min(start + page_size, total)
    return page, total_pages, start, end


def render_page_nav(key: str, page: int, total_pages: int, total: int) -> None:
    prev_col, info_col, next_col = st.columns([1, 2.4, 1])
    with prev_col:
        if st.button("이전", key=f"{key}_prev", disabled=page <= 1):
            st.session_state[f"{key}_page"] = page - 1
            st.rerun()
    with info_col:
        st.caption(f"{page} / {total_pages} 페이지 · 한 페이지 5개 · 모두 {total}개")
    with next_col:
        if st.button("다음", key=f"{key}_next", disabled=page >= total_pages or total == 0):
            st.session_state[f"{key}_page"] = page + 1
            st.rerun()


def render_upload_file_manager(items_key: str, uploader_key_name: str, on_change=None) -> None:
    items = list(st.session_state.get(items_key) or [])
    if not items:
        return

    companies = sorted({company_from_upload_name(name) for name, _ in items})
    st.caption(f"올린 파일 {len(items)}개 · 전체 지우기, 업체별 지우기, 파일 하나씩 지우기를 쓸 수 있습니다.")
    top = st.columns([1.3, 2.4, 1.8])
    with top[0]:
        clear_all = st.button("전체 지우기", key=f"{items_key}_clear_all")
    with top[1]:
        pick = st.selectbox("지울 업체", companies, key=f"{items_key}_company_pick")
    with top[2]:
        st.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
        clear_company = st.button("이 업체 파일 지우기", key=f"{items_key}_clear_company")

    def _set_items(remaining: list, reset_page: bool = False) -> None:
        st.session_state[items_key] = remaining
        st.session_state[uploader_key_name] += 1
        if reset_page:
            st.session_state[f"{items_key}_list_page"] = 1
        if on_change:
            on_change(remaining)
        st.rerun()

    if clear_all:
        _set_items([], reset_page=True)
    if clear_company and pick:
        _set_items(
            [(name, data) for name, data in items if company_from_upload_name(name) != pick],
            reset_page=True,
        )

    with st.expander(f"올린 파일 목록 ({len(items)}개)", expanded=False):
        page, total_pages, start, end = page_slice(f"{items_key}_list_page", len(items))
        for offset, (name, _) in enumerate(items[start:end]):
            real_index = start + offset
            left, right = st.columns([6, 1])
            with left:
                st.caption(name)
            with right:
                if st.button("지우기", key=f"{items_key}_del_{real_index}"):
                    _set_items([item for i, item in enumerate(items) if i != real_index])
        render_page_nav(f"{items_key}_list", page, total_pages, len(items))


def period_folder_from_item(item: dict) -> str:
    group = str(item.get("_group") or "").strip()
    if group and group != "-":
        return group
    name = str(item.get("변경될 파일명") or "")
    match = re.search(r"(\d{2}년(?:\d{2}월|상반기|하반기))", name)
    return match.group(1) if match else "날짜미상"


def execute_rename_save(preview: list, dest_folder: str, save_all: bool) -> str:
    os.makedirs(dest_folder, exist_ok=True)
    changed_count = 0
    skipped_count = 0
    error_count = 0
    saved_paths = []
    for item in preview:
        new_name = ensure_pdf_name(item.get("변경될 파일명") or "")
        if not new_name or new_name == "분석 실패.pdf" or new_name == "분석 실패":
            skipped_count += 1
            continue
        if not save_all and not item.get("_keep"):
            skipped_count += 1
            continue
        if save_all and "수정신고" in str(item.get("상태") or ""):
            skipped_count += 1
            continue
        company_folder = os.path.join(
            dest_folder,
            period_folder_from_item(item),
            item.get("_company") or "상호명미상",
        )
        os.makedirs(company_folder, exist_ok=True)
        dst = unique_path(company_folder, new_name)
        try:
            with open(dst, "wb") as out:
                out.write(item["_bytes"])
            changed_count += 1
            saved_paths.append(dst)
        except Exception:
            error_count += 1
    prefix = "✅ 모두 변경 완료!" if save_all else "✅ 완료!"
    result = f"{prefix} {changed_count}개 파일을 `{dest_folder}` 폴더에 저장했습니다."
    if skipped_count:
        result += f"\n❌ 제외(저장 안 함) {skipped_count}개"
    if saved_paths:
        result += "\n" + "\n".join(f"- {path}" for path in saved_paths)
    if error_count:
        result += f"\n❌ {error_count}개 파일 저장 중 오류가 발생했습니다."
    return result


def render_renamer_tab():
    mode = st.radio(
        "바꿀 파일 종류",
        RENAME_MODES,
        key="rename_mode",
        horizontal=True,
        help="종류마다 보는 PDF 칸과 파일명 규칙이 다릅니다.",
    )
    keys = rename_keys(mode)
    is_wht = mode == RENAME_MODE_WHT
    items = st.session_state[keys["items"]]
    selected_periods = render_period_picker()

    st.subheader("1. PDF 올리기")
    if is_wht:
        st.caption(
            "원천세는 신고서 오른쪽 위 **지급연월**, 지방세는 **2026년06월 신고 납부(납입)세액** 줄을 보고 날짜를 넣습니다. "
            "이름은 `원천세납부서(근로)`, `원천세신고서`, `원천세접수증`, `지방세납부서`, `지방세접수증` 입니다."
        )

    uploaded_files = render_pdf_dropzone(
        f"rename_kind_{mode}",
        f"uploader_{mode}_{st.session_state[keys['uploader']]}",
    )
    if uploaded_files:
        st.session_state[keys["items"]] = merge_uploaded_files(items, uploaded_files)
        st.session_state[keys["preview"]] = None
        st.session_state[keys["uploader"]] += 1
        st.rerun()

    result_key = keys["result"]
    if st.session_state.get(result_key):
        st.success(st.session_state[result_key])
        st.session_state[result_key] = None

    render_upload_file_manager(
        keys["items"],
        keys["uploader"],
        on_change=lambda _items, preview_key=keys["preview"]: st.session_state.__setitem__(preview_key, None),
    )
    if not st.session_state[keys["items"]]:
        st.warning("아직 올린 PDF가 없습니다.")

    st.subheader("2. 변경된 파일을 넣을 폴더")
    if is_wht:
        st.markdown("미리 만들어 둔 저장 폴더 경로를 입력하세요. 없으면 실행 시 자동으로 만들고, 기간 폴더 안에 업체별 폴더를 나눠 저장합니다.")
        help_text = f"예: {default_wht_output}"
        folder_caption = "일괄 변경은 고른 년도·월만 저장하고, 모두 변경 실행은 날짜와 상관없이 저장합니다."
    else:
        st.markdown("미리 만들어 둔 저장 폴더 경로를 입력하세요. 없으면 실행 시 자동으로 만들고, 기간 폴더 안에 업체별 폴더를 나눠 저장합니다.")
        help_text = f"예: {default_output}"
        folder_caption = "일괄 변경은 고른 년도·월·정기신고만 저장합니다. 모두 변경 실행은 날짜와 상관없이 저장합니다. 수정신고는 넣지 않습니다."
    st.text_input(
        "저장 폴더 경로",
        key=keys["output"],
        help=help_text,
    )
    st.caption(folder_caption)

    st.subheader("3. 변환")
    if st.button(
        "변환하기",
        type="secondary",
        disabled=not st.session_state[keys["items"]],
        key=f"rename_convert_{mode}",
    ):
        preview_list = []
        parse_fn = parse_withholding_pdf if is_wht else parse_receipt_pdf
        for fname, data in st.session_state[keys["items"]]:
            parsed = parse_fn(data, fname, selected_periods)
            preview_list.append(
                {
                    "현재 파일명": fname,
                    "변경될 파일명": parsed["filename"] if parsed["filename"] else "분석 실패.pdf",
                    "기간 폴더": parsed["period_group"] or "-",
                    "업체 폴더": parsed["company"],
                    "처리": action_label(parsed["keep"]),
                    "상태": status_label(parsed["keep"], parsed["status"]),
                    "_bytes": data,
                    "_company": parsed["company"],
                    "_keep": parsed["keep"],
                    "_group": parsed["period_group"],
                }
            )
        st.session_state[keys["preview"]] = preview_list
        st.session_state[keys["page"]] = 1

    preview = st.session_state[keys["preview"]]
    if preview:
        keep_count = sum(1 for item in preview if item["_keep"])
        skip_count = len(preview) - keep_count
        st.subheader("미리보기 · 파일명 수정")
        if is_wht:
            st.caption(
                f"✅ 저장 {keep_count}개 / ❌ 제외 {skip_count}개 · "
                f"일괄 변경은 선택한 기간({', '.join(selected_periods) or '없음'})만 저장합니다. "
                "변환된 파일명·업체 폴더·저장 여부는 표에서 고칠 수 있습니다."
            )
        else:
            st.caption(
                f"✅ 저장 {keep_count}개 / ❌ 제외 {skip_count}개 "
                "(수정신고·선택한 기간 외는 일괄 변경에서 넣지 않습니다). "
                "변환된 파일명·업체 폴더·저장 여부는 표에서 고칠 수 있습니다."
            )
        query = st.text_input(
            "업체 검색",
            key=keys["query"],
            placeholder="업체 폴더 이름으로 찾기",
        )
        filtered = list(preview)
        if query.strip():
            needle = query.strip().casefold()
            filtered = [
                item
                for item in filtered
                if needle in str(item.get("업체 폴더") or "").casefold()
            ]
        if st.session_state.get(keys["query_last"]) != query:
            st.session_state[keys["page"]] = 1
            st.session_state[keys["query_last"]] = query
        page, total_pages, start, end = page_slice(keys["page"], len(filtered))
        page_items = filtered[start:end]
        if page_items:
            edited = st.data_editor(
                [
                    {
                        "현재 파일명": item["현재 파일명"],
                        "변경될 파일명": item["변경될 파일명"],
                        "기간 폴더": item["기간 폴더"],
                        "업체 폴더": item["업체 폴더"],
                        "처리": item["처리"],
                        "상태": item["상태"],
                    }
                    for item in page_items
                ],
                column_config={
                    "현재 파일명": st.column_config.TextColumn(width="medium", disabled=True),
                    "변경될 파일명": st.column_config.TextColumn(width="large"),
                    "기간 폴더": st.column_config.TextColumn(width="small"),
                    "업체 폴더": st.column_config.TextColumn(width="medium"),
                    "처리": st.column_config.SelectboxColumn(options=["✅ 저장", "❌ 제외"], width="small"),
                    "상태": st.column_config.TextColumn(width="medium", disabled=True),
                },
                hide_index=True,
                num_rows="fixed",
                key=f"rename_editor_{mode}_{page}_{query}",
                width="stretch",
            )
            for src, row in zip(page_items, rows_from_editor(edited)):
                new_name = ensure_pdf_name(row.get("변경될 파일명") or src.get("변경될 파일명") or "")
                if new_name:
                    src["변경될 파일명"] = new_name
                src["_keep"] = is_save_action(row.get("처리"))
                src["처리"] = action_label(src["_keep"])
                company = str(row.get("업체 폴더") or "").strip()
                if company:
                    src["_company"] = company
                    src["업체 폴더"] = company
                group = str(row.get("기간 폴더") or "").strip()
                if group:
                    src["_group"] = group
                    src["기간 폴더"] = group
                src["상태"] = "✅ 성공" if src["_keep"] else (
                    src["상태"] if str(src.get("상태") or "").startswith("❌") else "❌ 제외"
                )
        if query.strip() and not filtered:
            st.caption("검색한 업체 파일이 없습니다.")
        nav_key = keys["page"][:-5] if keys["page"].endswith("_page") else keys["page"]
        render_page_nav(nav_key, page, total_pages, len(filtered))

        with st.container(horizontal=True, gap="small", width="content"):
            run_filtered = st.button("파일명 일괄 변경 실행", type="primary", key=f"rename_run_{mode}")
            run_all = st.button("모두 변경 실행", key=f"rename_run_all_{mode}")
        if run_filtered or run_all:
            dest_folder = str(st.session_state.get(keys["output"]) or "").strip('"').strip("'")
            result = execute_rename_save(preview, dest_folder, save_all=bool(run_all))
            st.session_state[keys["result"]] = result
            st.session_state[keys["items"]] = []
            st.session_state[keys["preview"]] = None
            st.session_state[keys["uploader"]] += 1
            st.rerun()


def render_bluehole_tab():
    col_main, col_login = st.columns([3.5, 1.5])
    with col_main:
        render_bluehole_upload_panel()
    with col_login:
        render_bluehole_login_panel()


def render_bluehole_login_panel():
    from bluehole_auth import clear_login_config, load_login_config, save_login_config

    saved = load_login_config()
    with st.container(border=True):
        st.markdown("### 🔐 블루홀 자동 로그인 설정")
        st.caption("이 컴퓨터에만 저장됩니다. 업로드를 시작하면 블루홀 로그인 화면에 자동으로 넣습니다.")

        if "bh_login_group" not in st.session_state:
            st.session_state.bh_login_group = saved.get("group_id") or ""
        if "bh_login_id" not in st.session_state:
            st.session_state.bh_login_id = saved.get("user_id") or ""
        if "bh_login_auto" not in st.session_state:
            st.session_state.bh_login_auto = bool(saved.get("auto_login", True))

        group_id = st.text_input(
            "그룹ID",
            placeholder="그룹ID 입력",
            key="bh_login_group",
        )
        user_id = st.text_input(
            "개인ID",
            placeholder="ID 입력",
            key="bh_login_id",
        )
        show_password = st.checkbox("비밀번호 표시", value=False, key="bh_login_show_pw")
        pw_type = "default" if show_password else "password"
        other_type = "password" if show_password else "default"
        pw_key = f"bh_login_pw_{pw_type}"
        if pw_key not in st.session_state:
            st.session_state[pw_key] = (
                st.session_state.get(f"bh_login_pw_{other_type}") or saved.get("password") or ""
            )
        password = st.text_input(
            "패스워드",
            type=pw_type,
            placeholder="PW 입력",
            key=pw_key,
        )
        auto_login_enabled = st.checkbox(
            "계정 정보 저장 및 자동 로그인 사용",
            key="bh_login_auto",
        )
        if st.button("로그인 정보 저장", type="primary", key="bh_login_save"):
            if auto_login_enabled:
                save_login_config(group_id.strip(), user_id.strip(), password, True)
                st.success("로그인 정보가 저장되었습니다.")
            else:
                clear_login_config()
                st.info("저장된 로그인 정보가 삭제되었습니다.")


def render_bluehole_upload_panel():
    import json
    import subprocess
    import tempfile

    from bluehole_scan import TEMPLATE_TITLE
    from bluehole_api import (
        BRANCH_OPTIONS,
        DEFAULT_BRANCH_LABEL,
        DEFAULT_STATUS_LABEL,
        STATUS_LABELS,
    )

    if "bh_uploader_key" not in st.session_state:
        st.session_state.bh_uploader_key = 0
    if "bh_files" not in st.session_state:
        st.session_state.bh_files = []
    if "bh_jobs" not in st.session_state:
        st.session_state.bh_jobs = None
    if "bh_result" not in st.session_state:
        st.session_state.bh_result = None
    if "bh_stage" not in st.session_state:
        st.session_state.bh_stage = os.path.join(tempfile.gettempdir(), "pdf_renamer_bluehole")
    if "bh_parent_case" not in st.session_state:
        st.session_state.bh_parent_case = ""
    if "bh_status_labels" not in st.session_state:
        st.session_state.bh_status_labels = [DEFAULT_STATUS_LABEL]
    if "bh_branch_labels" not in st.session_state:
        st.session_state.bh_branch_labels = [DEFAULT_BRANCH_LABEL]
    if "bh_apply_btemplate" not in st.session_state:
        st.session_state.bh_apply_btemplate = False

    st.markdown(
        "여러 업체 PDF를 한 번에 끌어다 놓으면, **업체별로 나눠서** 같은 하위 케이스에 들어갑니다. "
        "파일은 합치지 않고 **하나씩** 올립니다. "
        "(간이)지급명세서이면 아래 칸을 체크하고, 원천세 파일만 올리면 체크하지 않습니다."
    )
    st.text_input(
        "상위 멀티케이스",
        key="bh_parent_case",
        placeholder="상위 멀티케이스 번호",
        help="파일을 올릴 상위 멀티케이스 번호입니다.",
    )
    parent_id = str(st.session_state.get("bh_parent_case") or "").strip()
    filter_cols = st.columns(2)
    with filter_cols[0]:
        st.multiselect(
            "상태 필터",
            options=list(STATUS_LABELS.values()),
            key="bh_status_labels",
            help="하위 케이스를 찾을 때 이 상태를 씁니다. 완료 케이스는 파일을 올리지 않고 그대로 둡니다.",
        )
    with filter_cols[1]:
        st.multiselect(
            "소속",
            options=list(BRANCH_OPTIONS.keys()),
            key="bh_branch_labels",
            help="블루홀 소속 필터와 같습니다. 여러 지점을 같이 고를 수 있습니다.",
        )
    selected_status_ids = [
        status_id
        for status_id, label in STATUS_LABELS.items()
        if label in st.session_state.bh_status_labels
    ]
    selected_branch_ids = [
        BRANCH_OPTIONS[label]
        for label in st.session_state.bh_branch_labels
        if label in BRANCH_OPTIONS
    ]

    with st.container(border=True):
        apply_btemplate = st.checkbox(
            "(간이)지급명세서 파일 업로드",
            key="bh_apply_btemplate",
            help="(간이)지급명세서의 경우 파일명을 확인해서 B템플릿 체크를 진행합니다.",
        )
        st.caption("(간이)지급명세서의 경우 파일명을 확인해서 B템플릿 체크를 진행합니다.")
        if apply_btemplate:
            st.caption(
                f"`B템플릿 / {TEMPLATE_TITLE}` 만 조작합니다. "
                "있는 소득 종류는 **체크**, 없는 종류는 **빗금** 처리하고 "
                "상태·댓글·다른 템플릿은 건드리지 않습니다."
            )

    uploaded = render_pdf_dropzone(
        "bh_upload_kind",
        f"bh_uploader_{st.session_state.bh_uploader_key}",
    )
    if uploaded:
        apply_bh_files(merge_uploaded_files(st.session_state.bh_files, uploaded))
        st.session_state.bh_uploader_key += 1
        st.rerun()
    render_upload_file_manager("bh_files", "bh_uploader_key", on_change=apply_bh_files)

    if st.session_state.bh_files:
        st.caption("블루홀에 올라갈 파일명을 표에서 고칠 수 있습니다. 상호가 파일명 뒤에 있어야 업체를 찾습니다.")
        bh_rows = [
            {"현재 파일명": name, "올릴 파일명": name}
            for name, _ in st.session_state.bh_files
        ]
        bh_edited = st.data_editor(
            bh_rows,
            column_config={
                "현재 파일명": st.column_config.TextColumn(width="medium", disabled=True),
                "올릴 파일명": st.column_config.TextColumn(width="large"),
            },
            hide_index=True,
            num_rows="fixed",
            key=f"bh_name_editor_{st.session_state.bh_uploader_key}",
            width="stretch",
        )
        renamed = []
        changed = False
        for (old_name, data), row in zip(st.session_state.bh_files, rows_from_editor(bh_edited)):
            new_name = ensure_pdf_name(row.get("올릴 파일명") or old_name) or old_name
            if new_name != old_name:
                changed = True
            renamed.append((new_name, data))
        if changed:
            apply_bh_files(renamed)
            st.rerun()

    jobs = st.session_state.bh_jobs
    result = st.session_state.bh_result
    if jobs:
        if apply_btemplate:
            st.caption(f"올릴 업체 {len(jobs)}곳 · 템플릿 대상: {TEMPLATE_TITLE} 만")
        else:
            st.caption(f"올릴 업체 {len(jobs)}곳 · B템플릿은 건드리지 않습니다.")
        with st.expander("업체별 업로드 계획", expanded=len(jobs) <= 3):
            st.caption("같은 업체 파일은 같은 케이스에 들어가지만, 파일 자체는 따로따로 올라갑니다.")
            for job in jobs:
                st.markdown(f"**{job['company']}** ({len(job['files'])}개)")
                st.table(
                    [
                        {
                            "파일명": item["name"],
                            "기간": item.get("period") or "-",
                            "종류": item.get("income") or "-",
                        }
                        for item in job["files"]
                    ]
                )
                if apply_btemplate:
                    st.caption(
                        f"체크: {', '.join(job['check_items']) or '없음'} · "
                        f"빗금: {', '.join(job['slash_items']) or '없음'}"
                    )
        if st.button("블루홀에 업로드 시작", type="primary", key="bluehole_run_btn"):
            if not parent_id:
                st.error("상위 멀티 케이스 번호를 입력해 주세요.")
            else:
                script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bluehole_uploader.py")
                result_path = os.path.join(st.session_state.bh_stage, "last_result.json")
                jobs_path = os.path.join(st.session_state.bh_stage, "jobs.json")
                with open(jobs_path, "w", encoding="utf-8") as handle:
                    json.dump(st.session_state.bh_jobs, handle, ensure_ascii=False)
                status_id = ",".join(selected_status_ids)
                branch_id = ",".join(selected_branch_ids)
                command = [
                    sys.executable,
                    script,
                    "--folder",
                    st.session_state.bh_stage,
                    "--result",
                    result_path,
                    "--parent-id",
                    parent_id,
                    "--status",
                    status_id,
                    "--branch-id",
                    branch_id,
                    "--jobs",
                    jobs_path,
                ]
                if apply_btemplate:
                    command.append("--apply-btemplate")
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                if os.path.exists(result_path):
                    with open(result_path, encoding="utf-8") as handle:
                        st.session_state.bh_result = json.load(handle)
                else:
                    err = (completed.stderr or completed.stdout or "").strip()
                    st.session_state.bh_result = {
                        "overall": "실패",
                        "overall_reason": err or "결과 파일이 만들어지지 않아 업로드 결과를 확인하지 못했습니다.",
                        "companies": [],
                        "notes": [],
                    }

                st.session_state.bh_files = []
                st.session_state.bh_jobs = None
                st.session_state.bh_uploader_key += 1
                st.rerun()
    elif not result:
        st.caption("PDF를 여러 개 끌어다 놓으세요. 예: 왓에버타코 근로 파일, 왓에버타코 일용 파일.")

    if result:
        render_bluehole_results(result)
    else:
        st.caption("아직 블루홀 업로드는 진행되지 않았습니다.")


def display_result_status(status: str) -> str:
    if status in {"오류", "실패"}:
        return "❌ 실패"
    if status in {"됐다", "완료", "성공"}:
        return "✅ 성공"
    if status in {"제외"}:
        return "❌ 제외"
    if str(status).startswith(("✅", "❌")):
        return status
    return status or ""


def _company_detail_html(company: dict) -> str:
    import html

    parts = []
    case_id = company.get("case_id") or ""
    if case_id:
        url = f"https://bluehole.world/case/info/{html.escape(case_id)}/summary?"
        parts.append(f'<p><a href="{url}" target="_blank">케이스 #{html.escape(case_id)}</a></p>')
    notes = company.get("notes") or []
    if notes:
        parts.append("<p><b>특이사항</b></p><ul>")
        for note in notes:
            parts.append(f"<li>{html.escape(str(note))}</li>")
        parts.append("</ul>")
    files = company.get("files") or []
    if files:
        parts.append("<table class='inner'><tr><th>파일명</th><th>결과</th><th>내용</th></tr>")
        for item in files:
            parts.append(
                "<tr>"
                f"<td>{html.escape(str(item.get('name') or ''))}</td>"
                f"<td>{html.escape(display_result_status(str(item.get('status') or '')))}</td>"
                f"<td>{html.escape(str(item.get('reason') or ''))}</td>"
                "</tr>"
            )
        parts.append("</table>")
    templates = company.get("template") or []
    if templates:
        parts.append("<table class='inner'><tr><th>항목</th><th>작업</th><th>결과</th><th>내용</th></tr>")
        for item in templates:
            action = "체크" if item.get("action") == "check" else "빗금 표시"
            parts.append(
                "<tr>"
                f"<td>{html.escape(str(item.get('item') or ''))}</td>"
                f"<td>{html.escape(action)}</td>"
                f"<td>{html.escape(display_result_status(str(item.get('status') or '')))}</td>"
                f"<td>{html.escape(str(item.get('reason') or ''))}</td>"
                "</tr>"
            )
        parts.append("</table>")
    if not parts:
        return "<p>자세한 내용이 없습니다.</p>"
    return "".join(parts)


def render_bluehole_results(result: dict) -> None:
    import html
    import streamlit.components.v1 as components

    companies = list(result.get("companies") or [])
    if not companies:
        if result.get("overall_reason"):
            st.error(result["overall_reason"])
        return

    fail_n = sum(
        1 for company in companies if display_result_status(company.get("status") or "") == "❌ 실패"
    )
    ok_n = sum(
        1 for company in companies if display_result_status(company.get("status") or "") == "✅ 성공"
    )
    st.caption(f"전체 {len(companies)}건 · ✅ 성공 {ok_n}건 · ❌ 실패 {fail_n}건")

    if "bh_result_query" not in st.session_state:
        st.session_state.bh_result_query = ""
    query = st.text_input(
        "업체명 검색",
        key="bh_result_query",
        placeholder="예: 와이, 빠르크",
    ).strip()

    needle = re.sub(r"\s+", "", query).lower()
    visible = []
    for company in companies:
        name = company.get("company") or ""
        hay = re.sub(r"\s+", "", name).lower()
        if not needle or needle in hay:
            visible.append(company)

    body_rows = []
    for item in visible:
        name = html.escape(item.get("company") or "")
        status = display_result_status(item.get("status") or "")
        status_cls = "fail" if "실패" in status else "ok"
        reason = html.escape(item.get("reason") or "")
        body_rows.append(
            "<details class='row'>"
            f"<summary data-name=\"{name}\" data-status=\"{status}\" data-reason=\"{reason}\">"
            f"<span>{name}</span><span class='{status_cls}'>{status}</span><span class='reason'>{reason}</span>"
            "</summary>"
            f"<div class='detail'>{_company_detail_html(item)}</div>"
            "</details>"
        )

    height = min(560, max(220, 36 * (len(visible) + 1) + 24))
    components.html(
        f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body {{ margin: 0; background: #fff; font-family: "Segoe UI", sans-serif; font-size: 14px; color: #31333F; }}
  .wrap {{ border: 1px solid #d6dce5; border-radius: 8px; overflow: hidden; }}
  .head, .row summary {{
    display: grid;
    grid-template-columns: 22% 10% 68%;
    align-items: center;
    gap: 8px;
    box-sizing: border-box;
  }}
  .head {{
    background: #eaf1f8;
    font-weight: 700;
    padding: 9px 12px;
    border-bottom: 1px solid #d6dce5;
  }}
  .head span {{ cursor: pointer; user-select: none; display: inline-flex; align-items: center; gap: 4px; }}
  .head span:hover {{ color: #1B4F9C; }}
  .head .arrow {{ color: #1B4F9C; font-size: 12px; min-width: 12px; font-style: normal; font-weight: 700; }}
  .row {{ border-bottom: 1px solid #e6e9ef; }}
  .row:nth-child(even):not([open]) summary {{ background: #f7fbff; }}
  .row:nth-child(odd):not([open]) summary {{ background: #ffffff; }}
  .row summary {{
    list-style: none;
    padding: 8px 12px;
    cursor: pointer;
  }}
  .row summary::-webkit-details-marker {{ display: none; }}
  .row[open] {{
    margin: 8px 6px;
    border: 2px solid #2B6CB0;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(27, 79, 156, 0.14);
    overflow: hidden;
  }}
  .row[open] summary {{
    background: #d9e8f8;
    font-weight: 700;
  }}
  .fail {{ color: #c53030; font-weight: 600; }}
  .ok {{ color: #2f855a; font-weight: 600; }}
  .reason {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .detail {{
    padding: 12px 14px 16px 14px;
    background: #eef5fc;
    border-top: 1px dashed #8fb0d4;
    font-size: 13px;
  }}
  .inner {{ width: 100%; border-collapse: collapse; margin: 6px 0; background: #ffffff; }}
  .inner th, .inner td {{ border: 1px solid #d6dce5; padding: 5px 8px; text-align: left; }}
  .inner th {{ background: #eaf1f8; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="head">
    <span onclick="sortBy('name')">이름 <i class="arrow" id="arr-name">↑</i></span>
    <span onclick="sortBy('status')">결과 <i class="arrow" id="arr-status"></i></span>
    <span onclick="sortBy('reason')">내용 <i class="arrow" id="arr-reason"></i></span>
  </div>
  <div id="list">{''.join(body_rows)}</div>
</div>
<script>
let active = 'name';
let dir = 1;
function updateArrows() {{
  for (const key of ['name', 'status', 'reason']) {{
    const el = document.getElementById('arr-' + key);
    el.textContent = key === active ? (dir === 1 ? '↑' : '↓') : '';
  }}
}}
function sortBy(key) {{
  const list = document.getElementById('list');
  const items = Array.from(list.children);
  if (active === key) dir *= -1;
  else {{ active = key; dir = 1; }}
  items.sort((a, b) => {{
    const sa = a.querySelector('summary');
    const sb = b.querySelector('summary');
    const va = (sa.dataset[key] || '');
    const vb = (sb.dataset[key] || '');
    return va.localeCompare(vb, 'ko') * dir;
  }});
  items.forEach(item => list.appendChild(item));
  updateArrows();
}}
updateArrows();
</script>
</body>
</html>
        """,
        height=height,
        scrolling=True,
    )


init_state()
tab_rename, tab_bluehole = st.tabs(["📄 파일명 변경", "📤 블루홀 업로드"])
with tab_rename:
    render_renamer_tab()
with tab_bluehole:
    render_bluehole_tab()
