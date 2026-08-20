import json
import os
import time

CONFIG_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
    "PDF_Renamer",
)
CONFIG_FILE = os.path.join(CONFIG_DIR, "bluehole_login.json")
LOGIN_PROMPT = "시작하려면 로그인하세요"


def load_login_config() -> dict:
    data = {
        "group_id": "",
        "user_id": "",
        "password": "",
        "auto_login": True,
    }
    if not os.path.exists(CONFIG_FILE):
        return data
    try:
        with open(CONFIG_FILE, encoding="utf-8") as handle:
            saved = json.load(handle)
        if isinstance(saved, dict):
            data["group_id"] = str(saved.get("group_id") or "")
            data["user_id"] = str(saved.get("user_id") or saved.get("erp_id") or "")
            data["password"] = str(saved.get("password") or saved.get("erp_pw") or "")
            data["auto_login"] = bool(saved.get("auto_login", True))
    except Exception:
        pass
    return data


def save_login_config(group_id: str, user_id: str, password: str, auto_login: bool = True) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "group_id": group_id,
                "user_id": user_id,
                "password": password,
                "auto_login": auto_login,
            },
            handle,
            ensure_ascii=False,
        )


def clear_login_config() -> None:
    if os.path.exists(CONFIG_FILE):
        os.remove(CONFIG_FILE)


def is_login_screen(page) -> bool:
    try:
        body = page.inner_text("body")
    except Exception:
        return False
    return LOGIN_PROMPT in body


def _try_fill(page, hints: list[str], value: str, password: bool = False) -> bool:
    if not value:
        return False
    for hint in hints:
        for locator in (
            page.get_by_label(hint, exact=True),
            page.get_by_placeholder(hint),
            page.get_by_role("textbox", name=hint),
        ):
            try:
                if locator.count() > 0:
                    locator.first.fill(value, timeout=2500)
                    return True
            except Exception:
                continue
    if password:
        loc = page.locator("input[type='password']").first
        try:
            loc.fill(value, timeout=2500)
            return True
        except Exception:
            return False
    return False


def _click_login(page) -> bool:
    for locator in (
        page.get_by_role("button", name="로그인"),
        page.locator("button:has-text('로그인')"),
        page.locator("input[type='submit']"),
    ):
        try:
            if locator.count() > 0:
                locator.first.click(timeout=2500)
                return True
        except Exception:
            continue
    return False


def try_auto_login(page, config: dict) -> bool:
    group_id = str(config.get("group_id") or "").strip()
    user_id = str(config.get("user_id") or "").strip()
    password = str(config.get("password") or "")
    if not user_id or not password:
        return False

    if group_id:
        _try_fill(page, ["그룹ID"], group_id)
    filled_id = _try_fill(page, ["개인ID", "아이디"], user_id)
    if not filled_id:
        texts = page.locator("input[type='text']:visible")
        try:
            count = texts.count()
            if count >= 2:
                if group_id:
                    texts.nth(0).fill(group_id, timeout=2500)
                texts.nth(1).fill(user_id, timeout=2500)
                filled_id = True
            elif count == 1:
                texts.nth(0).fill(user_id, timeout=2500)
                filled_id = True
        except Exception:
            filled_id = False
    filled_pw = _try_fill(page, ["패스워드", "비밀번호", "Password"], password, password=True)
    if not filled_id or not filled_pw:
        return False
    if not _click_login(page):
        return False

    deadline = time.time() + 20
    while time.time() < deadline:
        if not is_login_screen(page):
            return True
        time.sleep(0.4)
    return not is_login_screen(page)


def wait_for_login(page, timeout_sec: int = 300) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if not is_login_screen(page):
            return
        time.sleep(1)
    raise TimeoutError("로그인 대기 시간(5분)이 지났습니다. 브라우저에서 로그인을 먼저 완료해 주세요.")


def ensure_logged_in(page, timeout_sec: int = 300) -> None:
    if not is_login_screen(page):
        return
    config = load_login_config()
    if config.get("auto_login") and try_auto_login(page, config):
        return
    wait_for_login(page, timeout_sec=timeout_sec)
