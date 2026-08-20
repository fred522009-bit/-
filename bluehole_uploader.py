import argparse
import json
import os
import sys

from bluehole_api import (
    DEFAULT_BRANCH_ID,
    DEFAULT_PARENT_CASE_ID,
    DEFAULT_STATUS,
    STATUS_LABELS,
    BlueHoleError,
    BlueHoleSession,
    cookies_from_playwright,
    find_child_case,
    update_btemplate,
    upload_missing_files,
)
from bluehole_auth import ensure_logged_in
from bluehole_scan import BLUEHOLE_HOME, scan_period_folder

PROFILE_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
    "PDF_Renamer",
    "bluehole_profile",
)


def log(message: str) -> None:
    print(message, flush=True)


def process_company(
    session: BlueHoleSession,
    parent_id: str,
    job: dict,
    status_ids: list[str] | None = None,
    branch_ids: list[str] | None = None,
    apply_btemplate: bool = False,
) -> dict:
    result = {
        "company": job["company"],
        "status": "실패",
        "reason": "",
        "files": [],
        "template": [],
        "notes": [],
        "case_id": "",
    }
    if not job.get("files"):
        result["reason"] = "폴더 안에 파일이 없어서 케이스에 추가하지 못했습니다."
        result["files"] = [
            {
                "name": "-",
                "status": "오류",
                "reason": "폴더 안에 파일이 없어서 케이스에 추가하지 못했습니다.",
            }
        ]
        return result

    try:
        child = find_child_case(
            session,
            parent_id,
            job["company"],
            job["company_key"],
            status_ids=status_ids,
            branch_ids=branch_ids,
        )
    except BlueHoleError as exc:
        result["reason"] = str(exc)
        result["files"] = [
            {"name": item["name"], "status": "오류", "reason": str(exc)}
            for item in job["files"]
        ]
        return result

    result["case_id"] = child["case_id"]
    case_status = str(child.get("status") or "")
    if case_status == "3":
        leave_msg = f'상태 "{STATUS_LABELS.get(case_status, "완료")}"이므로 그대로 두었습니다.'
        result["status"] = "완료"
        result["reason"] = leave_msg
        result["files"] = [
            {"name": item["name"], "status": "완료", "reason": leave_msg}
            for item in job["files"]
        ]
        result["template"] = []
        return result

    result["files"] = upload_missing_files(session, child["case_id"], job["files"])
    if apply_btemplate:
        result["template"] = update_btemplate(
            session,
            child["case_id"],
            job.get("check_items") or [],
            job.get("slash_items") or [],
        )
    else:
        result["template"] = []

    file_rows = result["files"]
    template_rows = result["template"]
    file_errors = [item for item in file_rows if item.get("status") == "오류"]
    template_errors = [item for item in template_rows if item.get("status") == "오류"]
    notes = []
    for item in file_rows:
        if item.get("status") == "특이사항":
            notes.append(f"{item.get('name')}: {item.get('reason')}")
    for item in template_rows:
        if item.get("status") == "특이사항":
            notes.append(f"{item.get('item')}: {item.get('reason')}")
    result["notes"] = notes

    if file_errors or template_errors:
        reasons = [item.get("reason") for item in file_errors + template_errors if item.get("reason")]
        result["status"] = "실패"
        result["reason"] = " ".join(reasons) if reasons else "파일 또는 B템플릿 처리 중 오류가 났습니다."
        return result

    result["status"] = "완료"
    if notes and not any(item.get("status") == "됐다" for item in file_rows + template_rows):
        result["reason"] = f"하위 케이스 #{child['case_id']} 는 이미 반영되어 있어 추가로 바꾸지 않았습니다."
    elif apply_btemplate:
        result["reason"] = f"하위 케이스 #{child['case_id']} 작업이 끝났습니다. 파일과 지정 B템플릿 외는 건드리지 않았습니다."
    else:
        result["reason"] = f"하위 케이스 #{child['case_id']} 에 파일만 올렸습니다. B템플릿은 건드리지 않았습니다."
    return result


def write_result(path: str, payload: dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    log(json.dumps(payload, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--parent-id", default=DEFAULT_PARENT_CASE_ID)
    parser.add_argument("--status", default=DEFAULT_STATUS)
    parser.add_argument("--branch-id", default=DEFAULT_BRANCH_ID)
    parser.add_argument("--jobs", default="")
    parser.add_argument("--apply-btemplate", action="store_true")
    args = parser.parse_args()

    payload = {"overall": "실패", "overall_reason": "", "companies": [], "notes": []}
    try:
        if args.jobs and os.path.isfile(args.jobs):
            with open(args.jobs, encoding="utf-8") as handle:
                jobs = json.load(handle)
        else:
            jobs = scan_period_folder(args.folder)
        if not jobs:
            payload["overall_reason"] = "처리할 PDF가 없습니다. 폴더 안에 파일이 있는지 확인해 주세요."
            write_result(args.result, payload)
            return 1

        from playwright.sync_api import sync_playwright

        os.makedirs(PROFILE_DIR, exist_ok=True)
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                PROFILE_DIR,
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(BLUEHOLE_HOME, wait_until="domcontentloaded")
            ensure_logged_in(page)
            session = BlueHoleSession(cookies_from_playwright(context))

            for job in jobs:
                try:
                    payload["companies"].append(
                        process_company(
                            session,
                            args.parent_id,
                            job,
                            status_ids=[item for item in str(args.status or "").split(",") if item],
                            branch_ids=[item for item in str(args.branch_id or "").split(",") if item],
                            apply_btemplate=bool(args.apply_btemplate),
                        )
                    )
                except Exception as exc:
                    payload["companies"].append(
                        {
                            "company": job["company"],
                            "status": "실패",
                            "reason": f"작업 중 오류가 났습니다: {exc}",
                            "files": [
                                {"name": item["name"], "status": "오류", "reason": str(exc)}
                                for item in job["files"]
                            ],
                            "template": [],
                            "notes": [],
                        }
                    )
            context.close()

        errors = [item for item in payload["companies"] if item.get("status") in {"오류", "실패"}]
        notes = []
        for item in payload["companies"]:
            for note in item.get("notes") or []:
                notes.append(f"{item.get('company')}: {note}")
        payload["notes"] = notes
        if errors:
            payload["overall"] = "실패"
            payload["overall_reason"] = " / ".join(
                f"{item.get('company')}: {item.get('reason')}" for item in errors
            )
        elif payload["companies"]:
            payload["overall"] = "완료"
            payload["overall_reason"] = "모든 업체 작업이 끝났습니다."
        else:
            payload["overall"] = "실패"
            payload["overall_reason"] = "처리할 업체가 없습니다."
        write_result(args.result, payload)
        return 0 if payload["overall"] == "완료" else 1
    except Exception as exc:
        payload["overall"] = "실패"
        payload["overall_reason"] = f"업로드를 시작하지 못했습니다: {exc}"
        write_result(args.result, payload)
        return 1


if __name__ == "__main__":
    sys.exit(main())
