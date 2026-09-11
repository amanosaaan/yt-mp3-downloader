"""UR賃貸住宅の空室状況を監視し、空きが出たらメールで通知するスクリプト。

使い方:
    python notifier.py --once          # 1回だけチェックして終了(cron向け)
    python notifier.py --interval 600  # 600秒間隔でループ監視

設定は環境変数で行う(.env や systemd/GitHub Actions の secrets から渡す想定):
    WATCH_URLS   監視対象のURL(カンマ区切りで複数可)。省略時は下のDEFAULT_URLS。
    STATE_FILE   状態保存先のJSONパス(既定: notifier.pyと同じディレクトリのstate.json)
    SMTP_HOST    例: smtp.gmail.com
    SMTP_PORT    例: 587
    SMTP_USER    SMTPログインユーザー(Gmailの場合はアプリパスワードを使うメールアドレス)
    SMTP_PASS    SMTPパスワード(Gmailの場合はアプリパスワード)
    MAIL_FROM    差出人アドレス(省略時はSMTP_USER)
    MAIL_TO      通知先アドレス(カンマ区切りで複数可)

注意:
    UR公式サイトのHTML構造を実機で確認できない環境で作成しているため、
    空室判定は「明記された空き戸数」「よくある『空きなし』文言」
    「号室らしき行の有無」「ページ内容のハッシュ変化」を組み合わせた
    フォールバック方式にしている。初回は --once で実行し、ログの
    [判定] 行が実際のページ状況と一致するか必ず目視確認すること。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import smtplib
import sys
import time
from dataclasses import dataclass, field
from email.mime.text import MIMEText
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("ur_vacancy_notifier")

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_STATE_FILE = BASE_DIR / "state.json"

DEFAULT_URLS = [
    "https://www.ur-net.go.jp/chintai/sp/kansai/hyogo/80_4410.html",
]

NO_VACANCY_PHRASES = [
    "現在、空き住戸はございません",
    "現在空き住戸はございません",
    "ただいま空き住戸はございません",
    "空き住戸はございません",
    "空き住戸はありません",
    "只今空室はございません",
    "ただいま空室はございません",
    "空室はございません",
    "空室はありません",
    "空き情報はございません",
    "現在募集はしておりません",
]

VACANCY_COUNT_RE = re.compile(r"空き\s*(\d+)\s*戸")
ROOM_LABEL_RE = re.compile(r"\d+\s*号室")

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}


@dataclass
class VacancyInfo:
    has_vacancy: bool
    vacancy_count: int | None
    uncertain: bool
    signature: str
    room_lines: list[str] = field(default_factory=list)


def fetch_page(url: str, timeout: int = 20) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding
    return resp.text


def extract_vacancy_info(html: str) -> VacancyInfo:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)

    room_lines = sorted(set(ROOM_LABEL_RE.findall(text)))

    count_match = VACANCY_COUNT_RE.search(text)
    no_vacancy_hit = any(phrase in text for phrase in NO_VACANCY_PHRASES)

    if count_match:
        count = int(count_match.group(1))
        has_vacancy = count > 0
        uncertain = False
    elif no_vacancy_hit:
        count = 0
        has_vacancy = False
        uncertain = False
    elif room_lines:
        count = len(room_lines)
        has_vacancy = True
        uncertain = True
    else:
        count = 0
        has_vacancy = False
        uncertain = True

    signature_source = "|".join(room_lines) if room_lines else text
    signature = hashlib.sha256(signature_source.encode("utf-8")).hexdigest()

    return VacancyInfo(
        has_vacancy=has_vacancy,
        vacancy_count=count,
        uncertain=uncertain,
        signature=signature,
        room_lines=room_lines,
    )


def load_state(state_file: Path) -> dict:
    if not state_file.exists():
        return {}
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        log.warning("状態ファイルの読み込みに失敗したため、初期化します: %s", state_file)
        return {}


def save_state(state_file: Path, state: dict) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def send_mail(subject: str, body: str) -> None:
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    mail_from = os.environ.get("MAIL_FROM", user)
    mail_to_raw = os.environ.get("MAIL_TO", "")
    mail_to = [addr.strip() for addr in mail_to_raw.split(",") if addr.strip()]

    if not (host and user and password and mail_from and mail_to):
        log.error(
            "SMTP設定が不足しているためメールを送信できません "
            "(SMTP_HOST/SMTP_USER/SMTP_PASS/MAIL_FROM/MAIL_TOを確認してください)"
        )
        return

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = ", ".join(mail_to)

    with smtplib.SMTP(host, port, timeout=20) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(mail_from, mail_to, msg.as_string())

    log.info("通知メールを送信しました: %s -> %s", subject, mail_to)


def check_url(url: str, state: dict) -> None:
    log.info("チェック中: %s", url)
    try:
        html = fetch_page(url)
    except requests.RequestException as e:
        log.error("取得に失敗しました: %s (%s)", url, e)
        return

    info = extract_vacancy_info(html)
    prev = state.get(url, {})
    prev_has_vacancy = prev.get("has_vacancy", False)
    prev_signature = prev.get("signature")

    status_label = "空きあり" if info.has_vacancy else "空きなし"
    uncertain_label = "(判定不確実)" if info.uncertain else ""
    log.info(
        "[判定] %s: %s%s 戸数=%s 号室候補=%s",
        url,
        status_label,
        uncertain_label,
        info.vacancy_count,
        info.room_lines or "-",
    )

    newly_vacant = info.has_vacancy and not prev_has_vacancy
    changed_while_vacant = (
        info.has_vacancy and prev_has_vacancy and info.signature != prev_signature
    )

    if newly_vacant or changed_while_vacant:
        reason = "新規に空きが発生しました" if newly_vacant else "空室状況が更新されました"
        body_lines = [
            f"{reason}。",
            "",
            f"URL: {url}",
            f"戸数(検出値): {info.vacancy_count}",
        ]
        if info.room_lines:
            body_lines.append("号室候補: " + ", ".join(info.room_lines))
        if info.uncertain:
            body_lines.append("")
            body_lines.append(
                "※ 自動判定の確度が低いため、必ずURLを開いて実際の空室状況を確認してください。"
            )
        send_mail(f"[UR空室通知] {reason}", "\n".join(body_lines))
    elif info.uncertain:
        log.warning("空室判定が不確実です。ページ構造が想定と異なる可能性があります: %s", url)

    state[url] = {
        "has_vacancy": info.has_vacancy,
        "vacancy_count": info.vacancy_count,
        "signature": info.signature,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def run_once(urls: list[str], state_file: Path) -> None:
    state = load_state(state_file)
    for url in urls:
        check_url(url, state)
    save_state(state_file, state)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once", action="store_true", help="1回だけチェックして終了する(cron向け)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=0,
        help="指定秒数間隔でループ監視する(0以下ならループしない)",
    )
    args = parser.parse_args()

    urls_env = os.environ.get("WATCH_URLS")
    urls = [u.strip() for u in urls_env.split(",")] if urls_env else DEFAULT_URLS
    state_file = Path(os.environ.get("STATE_FILE", str(DEFAULT_STATE_FILE)))

    if args.once or args.interval <= 0:
        run_once(urls, state_file)
        return 0

    log.info("監視ループを開始します(間隔: %s秒)", args.interval)
    while True:
        run_once(urls, state_file)
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
