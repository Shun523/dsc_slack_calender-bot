"""
Slack × カレンダー連携Bot
🗓️スタンプを検知 → メッセージ取得 → LLM日程抽出 → Supabase保存 → .ics生成 → スレッドに投稿
"""
import io
import os
import sys
import json
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from google import genai
from google.genai import types as genai_types
from supabase import create_client, Client

# ── 環境変数の読み込み ────────────────────────────────────────
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

SLACK_BOT_TOKEN  = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN  = os.getenv("SLACK_APP_TOKEN")
GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY")
SUPABASE_URL     = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY     = os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
SUPABASE_SVC_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# ── 起動時チェック ────────────────────────────────────────────
if not SLACK_BOT_TOKEN or SLACK_BOT_TOKEN.startswith("xoxb-your"):
    print("❌ SLACK_BOT_TOKEN が未設定です。.env を確認してください。")
    sys.exit(1)
if not SLACK_APP_TOKEN or SLACK_APP_TOKEN.startswith("xapp-your"):
    print("❌ SLACK_APP_TOKEN が未設定です。.env を確認してください。")
    sys.exit(1)
if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Supabase の環境変数が未設定です。.env を確認してください。")
    sys.exit(1)
if not SUPABASE_SVC_KEY:
    print("❌ SUPABASE_SERVICE_ROLE_KEY が未設定です。.env を確認してください。")
    sys.exit(1)
if not GEMINI_API_KEY or GEMINI_API_KEY == "your-gemini-api-key":
    print("⚠️  GEMINI_API_KEY が未設定です。🗓️スタンプを検知しても日程抽出は行われません。")

# ── ロガー設定 ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── クライアント初期化 ────────────────────────────────────────
app              = App(token=SLACK_BOT_TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SVC_KEY)
gemini           = genai.Client(api_key=GEMINI_API_KEY)

TARGET_EMOJI = "spiral_calendar_pad"  # 🗓️
JST          = timezone(timedelta(hours=9))

LLM_PROMPT = """\
以下のSlackメッセージから、イベント・MTGの情報をJSON形式で抽出してください。

現在日時（JST）: {now}

メッセージ:
{message_text}

以下のJSON形式のみを出力してください。
- 日時はISO 8601形式かつJST（+09:00）で記載してください。
- 年が明示されていない場合は現在年を使用してください。
- ただし現在が10月以降で、抽出した月が1〜3月の場合は翌年として扱ってください。
- end_at が不明な場合は start_at の1時間後を設定してください。
- 抽出できない項目は null にしてください。

{{
  "title": "イベントタイトル",
  "start_at": "2024-06-01T13:00:00+09:00",
  "end_at": "2024-06-01T14:00:00+09:00",
  "location": "場所またはnull"
}}
"""


def fix_year(event_data: dict) -> dict:
    """抽出日時が過去になっている場合に翌年へ補正する安全網。"""
    now = datetime.now(JST)
    for key in ("start_at", "end_at"):
        val = event_data.get(key)
        if not val:
            continue
        try:
            dt = datetime.fromisoformat(val)
            if dt < now - timedelta(days=1):
                dt = dt.replace(year=dt.year + 1)
                event_data[key] = dt.isoformat()
        except ValueError:
            pass
    return event_data


def extract_event_with_llm(message_text: str) -> dict | None:
    """LLMを使ってメッセージからイベント情報を抽出する。503時は最大3回リトライ。"""
    now_str = datetime.now(JST).strftime("%Y年%m月%d日 %H:%M")
    prompt  = LLM_PROMPT.format(now=now_str, message_text=message_text)

    for attempt in range(3):
        try:
            response = gemini.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            return fix_year(json.loads(response.text))
        except json.JSONDecodeError as e:
            logger.error(f"[LLM] JSONパース失敗: {e}")
            return None
        except Exception as e:
            if "503" in str(e) and attempt < 2:
                wait = 2 ** attempt  # 1秒 → 2秒
                logger.warning(f"[LLM] 503エラー、{wait}秒後にリトライ ({attempt + 1}/3): {e}")
                time.sleep(wait)
            else:
                logger.error(f"[LLM] API呼び出しエラー: {e}")
                return None

    return None


def save_event_to_db(event_data: dict, slack_thread_ts: str) -> bool:
    """Supabaseに保存。同じslack_thread_tsが既存ならFalseを返す。"""
    try:
        existing = supabase.table("events").select("id").eq("slack_thread_ts", slack_thread_ts).execute()
        if existing.data:
            logger.info(f"[DB] 登録済みのためスキップ: {slack_thread_ts}")
            return False
        supabase.table("events").insert({
            "title":           event_data["title"],
            "start_at":        event_data["start_at"],
            "end_at":          event_data["end_at"],
            "location":        event_data.get("location"),
            "slack_thread_ts": slack_thread_ts,
            "is_public":       True,
        }).execute()
        logger.info(f"[DB] 登録完了: {event_data['title']}")
        return True
    except Exception as e:
        logger.error(f"[DB] 保存エラー: {e}")
        return False


def build_gcal_url(event_data: dict) -> str:
    """Googleカレンダー追加用URLを生成する。"""
    from urllib.parse import urlencode

    def to_gcal_dt(iso_str: str) -> str:
        return datetime.fromisoformat(iso_str).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    params = {
        "action":   "TEMPLATE",
        "text":     event_data["title"],
        "dates":    f"{to_gcal_dt(event_data['start_at'])}/{to_gcal_dt(event_data['end_at'])}",
    }
    if event_data.get("location"):
        params["location"] = event_data["location"]

    return "https://calendar.google.com/calendar/render?" + urlencode(params)


def generate_ics(event_data: dict) -> bytes:
    """イベント情報から .ics ファイルのバイト列を生成する。"""
    def to_ical_dt(iso_str: str) -> str:
        return datetime.fromisoformat(iso_str).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//DSC Schedule Bot//JA",
        "BEGIN:VEVENT",
        f"UID:{uuid.uuid4()}",
        f"DTSTART:{to_ical_dt(event_data['start_at'])}",
        f"DTEND:{to_ical_dt(event_data['end_at'])}",
        f"SUMMARY:{event_data['title']}",
    ]
    if event_data.get("location"):
        lines.append(f"LOCATION:{event_data['location']}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines).encode("utf-8")


# ── イベントハンドラ: reaction_added ─────────────────────────
@app.event("reaction_added")
def handle_reaction_added(event: dict, client, logger):
    emoji      = event.get("reaction", "")
    user_id    = event.get("user", "")
    item       = event.get("item", {})
    channel_id = item.get("channel", "")
    message_ts = item.get("ts", "")

    if emoji != TARGET_EMOJI:
        return

    logger.info(f"[検知] 🗓️ | channel={channel_id} user={user_id} ts={message_ts}")

    # 1. メッセージ本文を取得
    try:
        result   = client.conversations_replies(channel=channel_id, ts=message_ts, limit=1)
        messages = result.get("messages", [])
        if not messages:
            logger.error("[取得] メッセージが見つかりません")
            return
        message_text = messages[0].get("text", "")
    except Exception as e:
        logger.error(f"[取得] メッセージ取得エラー: {e}")
        return

    if not message_text:
        logger.warning("[取得] メッセージ本文が空です")
        return

    logger.info(f"[取得] メッセージ本文: {message_text[:120]}")

    # 2. LLMで日程抽出
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your-gemini-api-key":
        logger.error("[LLM] GEMINI_API_KEY が未設定のためスキップします")
        return

    event_data = extract_event_with_llm(message_text)
    if not event_data or not event_data.get("title") or not event_data.get("start_at"):
        logger.error(f"[LLM] 日程の抽出に失敗しました: {event_data}")
        return

    logger.info(f"[LLM] 抽出結果: {event_data}")

    # 3. Supabaseに保存
    if not save_event_to_db(event_data, message_ts):
        return

    # 4. .ics を生成してスレッドに投稿
    try:
        ics_bytes  = generate_ics(event_data)
        safe_title = event_data["title"].replace("/", "-").replace(" ", "_")
        gcal_url   = build_gcal_url(event_data)
        client.files_upload_v2(
            channel=channel_id,
            thread_ts=message_ts,
            file=io.BytesIO(ics_bytes),
            filename=f"{safe_title}.ics",
            initial_comment=(
                f"✅ *{event_data['title']}* を登録しました！\n"
                f"\n"
                f"*カレンダーへの追加方法*\n"
                f"• *Googleカレンダー*：<{gcal_url}|こちらをタップ>（iPhone/Android 共通）\n"
                f"• *iPhoneカレンダー*：添付の .ics ファイルを開く → 右上メニューから「ブラウザで開く」を選択"
            ),
        )
        logger.info(f"[投稿] .ics をスレッドに投稿しました: {event_data['title']}")
    except Exception as e:
        logger.error(f"[投稿] ファイル送信エラー: {e}")


# ── 未処理イベントの警告を抑制 ───────────────────────────────
@app.event("reaction_removed")
def handle_reaction_removed(event: dict, logger):
    pass


# ── 起動 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("Bot を起動します（Socket Mode）...")
    handler = SocketModeHandler(app, SLACK_APP_TOKEN, ping_interval=10)
    handler.start()
