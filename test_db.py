"""
Supabase 接続テスト & events テーブル存在確認
実行: python bot/test_db.py  (プロジェクトルートから)
      または: cd bot && python test_db.py
"""
import os
import sys
from pathlib import Path

# .env はプロジェクトルート（bot/ の親）にある
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")

# ── 1. 環境変数チェック ──────────────────────────────────────
print("=== [1] 環境変数チェック ===")
if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ NEXT_PUBLIC_SUPABASE_URL または NEXT_PUBLIC_SUPABASE_ANON_KEY が未設定です。")
    sys.exit(1)
print(f"✅ URL : {SUPABASE_URL}")
print(f"✅ KEY : {SUPABASE_KEY[:30]}...")

# ── 2. Supabase クライアント初期化 ───────────────────────────
print("\n=== [2] Supabase クライアント初期化 ===")
try:
    from supabase import create_client, Client
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ クライアントの初期化に成功しました。")
except Exception as e:
    print(f"❌ クライアントの初期化に失敗しました: {e}")
    sys.exit(1)

# ── 3. events テーブルへのクエリ ─────────────────────────────
print("\n=== [3] events テーブル存在確認 ===")
try:
    response = supabase.table("events").select("id").limit(1).execute()
    # エラーなく応答が返れば、テーブルは存在する
    print("✅ events テーブルが存在します。")
    print(f"   取得件数: {len(response.data)} 件（最大1件取得）")
    if response.data:
        print(f"   サンプル行: {response.data[0]}")
except Exception as e:
    err_str = str(e)
    # "relation ... does not exist" はテーブル未作成を示す
    if "does not exist" in err_str:
        print(f"❌ events テーブルが存在しません（未作成）。")
        print(f"   → schema.sql を Supabase の SQL Editor で実行してください。")
    else:
        print(f"⚠️  クエリ中にエラーが発生しました: {e}")
    sys.exit(1)

print("\n✅ すべてのチェックが完了しました。Supabase との接続は正常です。")
