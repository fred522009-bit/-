import hashlib
import os
import re
from collections import defaultdict

INCOME_TAGS = ("근로", "일용", "사업", "기타")
TEMPLATE_ITEMS = {
    "근로": "근로소득",
    "일용": "일용소득",
    "사업": "사업소득",
    "기타": "기타소득",
}
TEMPLATE_TITLE = "원천세 - 간이지급명세서 V1"
BLUEHOLE_HOME = "https://bluehole.world/"


def income_from_filename(filename: str) -> str | None:
    match = re.search(r"\((근로|일용|사업|기타)\)", filename)
    return match.group(1) if match else None


def company_from_filename(filename: str) -> str:
    stem = os.path.splitext(os.path.basename(filename))[0]
    if "_" in stem:
        company = stem.rsplit("_", 1)[-1].strip()
        company = re.split(r"귀속연도|귀속\s*연도", company)[0].strip()
        if company:
            return repair_company_name(company)
    return "상호명미상"


def period_from_filename(filename: str) -> str:
    match = re.search(r"(\d{2}년(?:\d{2}월|상반기|하반기))", filename)
    return match.group(1) if match else "-"


def repair_company_name(name: str) -> str:
    """PDF 줄바꿈으로 잘린 상호는 띄어쓰기 없이 이어 붙입니다."""
    if not name:
        return name
    name = name.replace("\r", "\n")
    name = re.sub(r"([0-9A-Za-z가-힣])\n+([0-9A-Za-z가-힣])", r"\1\2", name)
    name = re.sub(r"([0-9A-Za-z가-힣])\n+(\()", r"\1\2", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"(?<=[가-힣]) (?=[가-힣(])", "", name)
    for prefix in ("주식회사", "유한회사"):
        if name.startswith(prefix) and len(name) > len(prefix):
            rest = name[len(prefix) :].lstrip()
            name = f"{prefix} {rest}"
            break
    return name.strip(" ,;.|")


def normalize_company(name: str) -> str:
    name = repair_company_name(name)
    name = re.sub(r"주식회사|\(주\)|㈜|\(유\)|유한회사", "", name)
    name = re.sub(r"\([^)]*$", "", name)
    name = re.sub(r"\([^)]*\)", "", name)
    return re.sub(r"\s+", "", name).lower()


def company_search_queries(company: str) -> list[str]:
    repaired = repair_company_name(company)
    queries: list[str] = []

    def add(query: str) -> None:
        query = repair_company_name(query).strip()
        compact = re.sub(r"\s+", "", query)
        if query and compact not in {re.sub(r"\s+", "", item) for item in queries} and len(compact) >= 2:
            queries.append(query)

    add(repaired)
    stripped = re.sub(r"주식회사|\(주\)|㈜|\(유\)|유한회사", "", repaired).strip()
    add(stripped)
    for part in re.findall(r"[^()]+", stripped):
        add(part.strip())
    add(re.sub(r"[()]", "", stripped))
    hangul = "".join(re.findall(r"[가-힣]+", stripped))
    if hangul:
        add(hangul)
        if len(hangul) >= 6:
            add(hangul[:6])
        if len(hangul) >= 4:
            add(hangul[:4])
        if len(hangul) >= 3:
            add(hangul[:3])
    english = re.search(r"\(([A-Za-z][A-Za-z0-9 ]*)", repaired)
    if english:
        add(english.group(1).strip())
        first = english.group(1).split()[0]
        add(first)
    return queries


def pdf_fingerprint(path: str) -> dict:
    with open(path, "rb") as handle:
        data = handle.read()
    return fingerprint_bytes(data)


def fingerprint_bytes(data: bytes) -> dict:
    file_hash = hashlib.sha256(data).hexdigest()
    text = ""
    try:
        import io
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                text += (page.extract_text() or "") + "\n"
    except Exception:
        text = ""
    return {
        "size": len(data),
        "sha256": file_hash,
        "text_sha256": hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest(),
        "text": text.strip(),
    }


def _build_job(company: str, files: list[dict]) -> dict:
    present = {item["income"] for item in files if item.get("income")}
    check_items = [TEMPLATE_ITEMS[tag] for tag in INCOME_TAGS if tag in present and tag != "기타"]
    if "기타" in present:
        check_items.append(TEMPLATE_ITEMS["기타"])
    slash_items = [
        TEMPLATE_ITEMS[tag] for tag in INCOME_TAGS if TEMPLATE_ITEMS[tag] not in check_items
    ]
    return {
        "company": company,
        "company_key": normalize_company(company),
        "files": files,
        "check_items": check_items,
        "slash_items": slash_items,
    }


def jobs_from_uploaded(items: list[tuple[str, bytes]], save_root: str) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for fname, data in items:
        company = company_from_filename(fname)
        company_dir = os.path.join(save_root, company)
        os.makedirs(company_dir, exist_ok=True)
        path = os.path.join(company_dir, fname)
        with open(path, "wb") as handle:
            handle.write(data)
        grouped[company].append(
            {
                "name": fname,
                "path": path,
                "income": income_from_filename(fname),
                "period": period_from_filename(fname),
                "fingerprint": fingerprint_bytes(data),
            }
        )
    return [_build_job(company, files) for company, files in grouped.items()]


def scan_period_folder(folder: str) -> list[dict]:
    jobs = []
    if not folder or not os.path.isdir(folder):
        return jobs

    entries = sorted(os.listdir(folder))
    company_dirs = [
        name for name in entries if os.path.isdir(os.path.join(folder, name))
    ]
    if company_dirs:
        for company in company_dirs:
            company_path = os.path.join(folder, company)
            files = []
            for fname in sorted(os.listdir(company_path)):
                if not fname.lower().endswith(".pdf"):
                    continue
                full_path = os.path.join(company_path, fname)
                files.append(
                    {
                        "name": fname,
                        "path": full_path,
                        "income": income_from_filename(fname),
                        "period": period_from_filename(fname),
                        "fingerprint": pdf_fingerprint(full_path),
                    }
                )
            if files:
                jobs.append(_build_job(company, files))
        return jobs

    file_items = []
    for fname in entries:
        if fname.lower().endswith(".pdf"):
            full_path = os.path.join(folder, fname)
            with open(full_path, "rb") as handle:
                file_items.append((fname, handle.read()))
    if file_items:
        return jobs_from_uploaded(file_items, folder)
    return jobs
