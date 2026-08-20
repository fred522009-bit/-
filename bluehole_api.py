import json
import os
from typing import Any
from urllib.parse import urlencode
import re

import requests

from bluehole_scan import TEMPLATE_TITLE, company_search_queries, normalize_company, repair_company_name

HOST = "https://bluehole.world"
DEFAULT_PARENT_CASE_ID = "188384"
DEFAULT_STATUS = "2"
DEFAULT_STATUS_LABEL = "해결"
DEFAULT_BRANCH_ID = "1"
DEFAULT_BRANCH_LABEL = "택스팀_영등포"
BRANCH_OPTIONS = {
    "택스팀_영등포": "1",
    "택스팀_수원시청": "2",
    "택스팀_천안아산": "3",
}
STATUS_LABELS = {
    "1": "진행중",
    "2": "해결",
    "3": "완료",
    "4": "보류",
}
VAL_CHECK = "1"
VAL_SLASH = "DISABLE"
TEMPLATE_NAME = "간이지급명세서 V1"


class BlueHoleError(RuntimeError):
    pass


class BlueHoleSession:
    def __init__(self, cookies: dict[str, str]):
        self.http = requests.Session()
        self.http.headers.update(
            {
                "Accept": "application/json",
                "Origin": HOST,
                "Referer": f"{HOST}/",
            }
        )
        for name, value in cookies.items():
            if value:
                self.http.cookies.set(name, value)
        self._child_cache: dict[str, list[dict]] = {}

    def get(self, path: str, params: dict[str, Any]) -> Any:
        url = f"{HOST}/{path.lstrip('/')}?{urlencode(params, doseq=True)}"
        response = self.http.get(url, timeout=60)
        return _unwrap(response)

    def post_form(self, path: str, query: dict[str, Any], data=None, files=None) -> Any:
        url = f"{HOST}/{path.lstrip('/')}?{urlencode(query, doseq=True)}"
        response = self.http.post(url, data=data, files=files, timeout=180)
        return _unwrap(response)


def cookies_from_playwright(context) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in context.cookies():
        name = item.get("name")
        value = item.get("value")
        if name and value:
            out[name] = value
    if "PHPSESSID" not in out:
        raise BlueHoleError("로그인 세션 쿠키를 찾지 못했습니다. 브라우저에서 로그인을 완료해 주세요.")
    return out


def _unwrap(response: requests.Response) -> Any:
    try:
        payload = response.json()
    except Exception as exc:
        raise BlueHoleError(f"블루홀 응답을 읽지 못했습니다: {exc}") from exc
    if isinstance(payload, dict) and "isSuccess" in payload:
        if payload.get("isSuccess"):
            return payload.get("data")
        errors = payload.get("errorMsg") or ["알 수 없는 오류"]
        raise BlueHoleError(str(errors[0]))
    raise BlueHoleError("블루홀 응답 형식이 예상과 다릅니다.")


def find_child_case(
    session: BlueHoleSession,
    parent_id: str,
    company: str,
    company_key: str,
    status_ids: list[str] | None = None,
    branch_ids: list[str] | None = None,
) -> dict:
    company = repair_company_name(company)
    company_key = normalize_company(company) or company_key
    if not company or company == "상호명미상" or len(company_key) < 2:
        raise BlueHoleError(
            f"파일에서 읽은 업체 이름 '{company}' 이(가) 너무 짧거나 불분명해서 거래처를 찾지 못했습니다. "
            "파일명 끝의 상호를 확인해 주세요."
        )

    picked = _pick_child_by_company(
        _list_children(session, parent_id),
        parent_id,
        company,
        company_key,
        status_ids,
        branch_ids,
    )
    if picked:
        return _pack_child_case(picked["case"], picked["client"], company)

    unique = _unique_child_from_queries(session, parent_id, company, status_ids, branch_ids)
    if unique:
        return _pack_child_case(unique["case"], unique.get("client") or {}, company)

    clients = _search_clients(session, company)
    found: dict[str, dict] = {}
    for client in clients:
        cases = session.get(
            "case/list",
            {
                "act": "getList",
                "client_id": client["id"],
                "parent_id": parent_id,
                "with_child_case": "t",
                "limit": 20,
            },
        )
        children = (cases or {}).get("list") or []
        matched = [row for row in children if _child_matches_filters(row, parent_id, status_ids, branch_ids)]
        if len(matched) > 1:
            raise BlueHoleError(
                f"'{company}' 거래처(#{client.get('id')})의 상위 멀티케이스 #{parent_id} 아래 하위 케이스가 "
                f"{len(matched)}개라서 어느 쪽에 넣을지 정하지 못했습니다."
            )
        if len(matched) == 1:
            child = matched[0]
            found[str(child["id"])] = {
                "client": client,
                "case": child,
                "score": _client_score(client.get("name") or "", company, company_key),
            }

    if len(found) == 1:
        item = next(iter(found.values()))
        return _pack_child_case(item["case"], item["client"], company)

    if not found:
        raise BlueHoleError(
            f"'{company}' 거래처의 하위 케이스를 상위 멀티케이스 #{parent_id} 아래에서 찾지 못했습니다. "
            "거래처 이름과 상위 멀티케이스 번호를 확인해 주세요."
        )

    ranked = sorted(found.values(), key=lambda item: item["score"], reverse=True)
    top = ranked[0]["score"]
    tied = [item for item in ranked if item["score"] == top]
    if len(tied) > 1:
        names = ", ".join((item["client"].get("name") or "?") for item in tied)
        raise BlueHoleError(
            f"'{company}' 과(와) 이름이 비슷한 거래처가 여러 개라서 케이스를 정하지 못했습니다: {names}"
        )
    return _pack_child_case(tied[0]["case"], tied[0]["client"], company)


def _child_matches_filters(
    child: dict,
    parent_id: str,
    status_ids: list[str] | None,
    branch_ids: list[str] | None,
) -> bool:
    if str(child.get("id") or "") == str(parent_id):
        return False
    child_parent = str(child.get("parent_id") or "")
    if child_parent and child_parent != str(parent_id):
        return False
    if status_ids:
        allowed = {str(item) for item in status_ids if item}
        if allowed and str(child.get("status") or "") not in allowed:
            return False
    if branch_ids:
        assigned = child.get("assigned_user_obj") or {}
        case_branch_id = str(
            assigned.get("branch_id")
            or child.get("branch_id")
            or (child.get("user_obj") or {}).get("branch_id")
            or ""
        )
        allowed = {str(item) for item in branch_ids if item}
        # 소속 값이 비어 있으면 제외하지 않음. 비어 있다고 영등포가 아닌 것은 아님.
        if allowed and case_branch_id and case_branch_id not in allowed:
            return False
    return True


def _unique_child_from_queries(
    session: BlueHoleSession,
    parent_id: str,
    company: str,
    status_ids: list[str] | None,
    branch_ids: list[str] | None,
) -> dict | None:
    for query in company_search_queries(company):
        data = session.get(
            "case/list",
            {
                "act": "getList",
                "parent_id": parent_id,
                "q": query,
                "with_child_case": "t",
                "limit": 50,
            },
        )
        matched = [
            row
            for row in (data or {}).get("list") or []
            if _child_matches_filters(row, parent_id, status_ids, branch_ids)
        ]
        unique: dict[str, dict] = {}
        for row in matched:
            unique[str(row["id"])] = row
        if len(unique) == 1:
            child = next(iter(unique.values()))
            return {"case": child, "client": _row_client(child)}
    return None


def _list_children(session: BlueHoleSession, parent_id: str) -> list[dict]:
    cache_key = str(parent_id)
    if cache_key in session._child_cache:
        return session._child_cache[cache_key]
    rows: list[dict] = []
    seen: set[str] = set()
    for pg in range(1, 51):
        data = session.get(
            "case/list",
            {
                "act": "getList",
                "parent_id": parent_id,
                "with_child_case": "t",
                "limit": 100,
                "pg": str(pg),
                "start": (pg - 1) * 100,
            },
        )
        chunk = (data or {}).get("list") or []
        new_count = 0
        for row in chunk:
            rid = str(row.get("id") or "")
            if not rid or rid == str(parent_id) or rid in seen:
                continue
            seen.add(rid)
            rows.append(row)
            new_count += 1
        if not chunk or new_count == 0 or len(chunk) < 100:
            break
    session._child_cache[cache_key] = rows
    return rows


def _row_client(row: dict) -> dict:
    client = row.get("client_obj") if isinstance(row.get("client_obj"), dict) else {}
    name = client.get("name") or row.get("client_name") or ""
    cid = client.get("id") or row.get("client_id") or ""
    if not name:
        extra = row.get("clients") or []
        if extra and isinstance(extra[0], dict):
            name = extra[0].get("name") or name
            cid = extra[0].get("id") or cid
    return {"id": cid, "name": name}


def _pick_child_by_company(
    children: list[dict],
    parent_id: str,
    company: str,
    company_key: str,
    status_ids: list[str] | None,
    branch_ids: list[str] | None,
) -> dict | None:
    scored: list[tuple[int, dict, dict]] = []
    for row in children:
        if not _child_matches_filters(row, parent_id, status_ids, branch_ids):
            continue
        client = _row_client(row)
        score = _client_score(client.get("name") or "", company, company_key)
        if score <= 0:
            continue
        scored.append((score, row, client))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    top = scored[0][0]
    tied = [item for item in scored if item[0] == top]
    if len(tied) != 1:
        return None
    return {"case": tied[0][1], "client": tied[0][2]}


def _pack_child_case(child: dict, client: dict, company: str) -> dict:
    assigned = child.get("assigned_user_obj") or {}
    return {
        "case_id": str(child["id"]),
        "client_id": str(child.get("client_id") or client.get("id") or ""),
        "client_name": client.get("name") or (child.get("client_obj") or {}).get("name") or company,
        "subject": child.get("subject") or "",
        "status": str(child.get("status") or ""),
        "branch_id": str(assigned.get("branch_id") or child.get("branch_id") or ""),
        "branch_name": assigned.get("branch_name") or "",
    }


def list_case_files(session: BlueHoleSession, case_id: str) -> list[dict]:
    data = session.get(
        "bfile/list",
        {
            "act": "getList",
            "case_id": case_id,
            "container_type": "case",
            "container_id": case_id,
        },
    )
    files = []
    for row in (data or {}).get("list") or []:
        file_obj = row.get("file_obj") or {}
        name = file_obj.get("name") or ""
        if name:
            files.append(
                {
                    "id": str(file_obj.get("id") or ""),
                    "name": name,
                    "size": int(file_obj.get("size") or 0),
                }
            )
    return files


def upload_missing_files(session: BlueHoleSession, case_id: str, files: list[dict]) -> list[dict]:
    if not files:
        return [
            {
                "name": "-",
                "status": "오류",
                "reason": "폴더 안에 파일이 없어서 케이스에 추가하지 못했습니다.",
            }
        ]

    existing = list_case_files(session, case_id)
    existing_names = {item["name"].strip().lower() for item in existing}
    results = []
    to_upload = []
    for item in files:
        name = item["name"]
        path = item.get("path") or ""
        if not path or not os.path.isfile(path):
            results.append(
                {
                    "name": name,
                    "status": "오류",
                    "reason": f"'{name}' 파일을 폴더에서 찾지 못해 케이스에 추가하지 못했습니다.",
                }
            )
            continue
        if name.strip().lower() in existing_names:
            results.append(
                {
                    "name": name,
                    "status": "특이사항",
                    "reason": "이미 같은 파일명이 케이스에 있어 올리지 않았습니다.",
                }
            )
        else:
            to_upload.append(item)

    if not to_upload:
        return results

    metas = {}
    multipart = []
    opened = []
    try:
        for index, item in enumerate(to_upload):
            handle = open(item["path"], "rb")
            opened.append(handle)
            multipart.append(
                (
                    "files[]",
                    (str(index), handle, "application/pdf"),
                )
            )
            metas[str(index)] = {
                "file_name": item["name"],
                "tag_ids": "",
                "description": "",
            }
        data = session.post_form(
            f"case/info/{case_id}",
            {"act": "updateCase"},
            data={"file_metas": json.dumps(metas, ensure_ascii=False)},
            files=multipart,
        )
    finally:
        for handle in opened:
            handle.close()

    props = (data or {}).get("success_props") or []
    if "file" not in props:
        for item in to_upload:
            results.append(
                {
                    "name": item["name"],
                    "status": "오류",
                    "reason": "파일을 올렸지만 블루홀이 저장 성공을 확인해주지 않았습니다.",
                }
            )
        return results

    for item in to_upload:
        results.append({"name": item["name"], "status": "됐다", "reason": "케이스에 파일을 올렸습니다."})
    return results


def update_btemplate(
    session: BlueHoleSession,
    case_id: str,
    check_items: list[str],
    slash_items: list[str],
) -> list[dict]:
    info = session.get(
        f"case/info/{case_id}",
        {
            "act": "getInfo",
            "with_templates": "t",
        },
    )
    template_list = ((info or {}).get("templates") or {}).get("template_id_list") or []
    if not template_list:
        return _template_errors(
            check_items,
            slash_items,
            f"이 케이스에서 '{TEMPLATE_TITLE}' B템플릿을 찾지 못해 체크/빗금 처리를 하지 못했습니다.",
        )

    template_id = str(template_list[0].get("template_id") or "")
    version_id = str(template_list[0].get("template_version_id") or "")
    vals = session.get(
        "template/info",
        {
            "act": "getTemplateVals",
            "template_id": template_id,
            "template_version_id": version_id,
            "case_ids": case_id,
        },
    )
    template_info = (((vals or {}).get("template_info") or {}).get("list") or [{}])[0]
    info_obj = template_info.get("templateInfo") or {}
    kind = info_obj.get("kind_name") or ""
    name = info_obj.get("name") or ""
    title = f"{kind} - {name}".strip(" -")
    if TEMPLATE_NAME not in name and TEMPLATE_TITLE not in title:
        return _template_errors(
            check_items,
            slash_items,
            f"이 케이스의 B템플릿이 '{title or name or '알 수 없음'}' 이라서 "
            f"'{TEMPLATE_TITLE}' 체크/빗금 처리를 하지 못했습니다.",
        )

    item_defs = ((template_info.get("templateItems") or {}).get("list") or [])
    name_by_item_id = {
        str(item.get("id")): item.get("item_name") or ""
        for item in item_defs
    }
    wanted = {label: VAL_CHECK for label in check_items}
    wanted.update({label: VAL_SLASH for label in slash_items})

    results = []
    changes = []
    seen = set()
    for row in (vals or {}).get("list") or []:
        item_id = str(row.get("template_item_id") or "")
        label = name_by_item_id.get(item_id) or ""
        if label not in wanted:
            continue
        seen.add(label)
        target = wanted[label]
        current = row.get("val")
        action = "check" if target == VAL_CHECK else "slash"
        if current == target:
            already = "이미 체크되어 있어 그대로 두었습니다." if action == "check" else "이미 빗금 표시가 되어 있어 그대로 두었습니다."
            results.append(
                {
                    "item": label,
                    "action": action,
                    "status": "특이사항",
                    "reason": already,
                }
            )
            continue
        changes.append({"id": str(row["id"]), "val": target})
        results.append(
            {
                "item": label,
                "action": action,
                "status": "대기",
                "reason": "",
            }
        )

    for label in list(wanted):
        if label not in seen:
            action = "check" if wanted[label] == VAL_CHECK else "slash"
            results.append(
                {
                    "item": label,
                    "action": action,
                    "status": "오류",
                    "reason": f"B템플릿에서 '{label}' 항목을 찾지 못해 처리하지 못했습니다.",
                }
            )

    if not changes:
        return results

    data = session.post_form(
        f"case/info/{case_id}",
        {"act": "updateCase"},
        data={"kv[template_item_vals_json]": json.dumps(changes, ensure_ascii=False)},
    )
    props = (data or {}).get("success_props") or []
    ok = "template" in props
    for item in results:
        if item["status"] == "대기":
            if ok:
                item["status"] = "됐다"
                item["reason"] = "체크했습니다." if item["action"] == "check" else "빗금 표시했습니다."
            else:
                item["status"] = "오류"
                item["reason"] = "B템플릿 변경을 저장했지만 블루홀이 성공을 확인해주지 않았습니다."
    return results


def _search_clients(session: BlueHoleSession, company: str) -> list[dict]:
    seen = set()
    clients = []
    for query in company_search_queries(company):
        data = session.get("client/list", {"act": "getList", "q": query})
        for client in (data or {}).get("list") or []:
            cid = str(client.get("id") or "")
            if cid and cid not in seen:
                seen.add(cid)
                clients.append(client)
    return clients


def _client_score(client_name: str, company: str, company_key: str) -> int:
    repaired = repair_company_name(company)
    client_repaired = repair_company_name(client_name or "")
    if not client_repaired:
        return 0
    if client_name == company or client_repaired == repaired:
        return 4
    hangul_company = "".join(re.findall(r"[가-힣]+", repaired))
    hangul_client = "".join(re.findall(r"[가-힣]+", client_repaired))
    if hangul_company and hangul_company == hangul_client:
        return 3
    eng_company = re.search(r"\(([A-Za-z][A-Za-z0-9 ]*)", repaired)
    eng_client = re.search(r"\(([A-Za-z][A-Za-z0-9 ]*)", client_repaired)
    if (
        eng_company
        and eng_client
        and eng_company.group(1).strip().lower() == eng_client.group(1).strip().lower()
    ):
        return 3
    compact = normalize_company(client_name)
    if compact and company_key and compact == company_key:
        return 2
    if company_key and compact and (compact.startswith(company_key) or company_key.startswith(compact)):
        if min(len(compact), len(company_key)) >= 3:
            return 1
    return 0


def _template_errors(check_items: list[str], slash_items: list[str], reason: str) -> list[dict]:
    results = []
    for label in check_items:
        results.append({"item": label, "action": "check", "status": "오류", "reason": reason})
    for label in slash_items:
        results.append({"item": label, "action": "slash", "status": "오류", "reason": reason})
    return results
