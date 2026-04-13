# DSC Slack Calendar Bot

Slackの🗓️スタンプを検知してメッセージから日程を自動抽出し、カレンダーに登録するBot。

## 機能

- 🗓️（spiral_calendar_pad）スタンプが押されたメッセージを検知
- Gemini AIでイベントタイトル・日時・場所を自動抽出
- Supabaseにイベントを保存
- `.ics`ファイルをスレッドに投稿（Google カレンダー・iPhone カレンダー対応）

## システム構成

```
[Slack] ──→ [このBot] ──→ [Supabase DB] ←── [フロントエンド（別リポジトリ）]
```

- **このBot**：🗓️スタンプ検知 → 日程抽出 → Supabase保存 → .ics投稿
- **フロントエンド**：Supabaseのデータをカレンダー表示（Next.js）
- **Supabase**：2つのサービスが共有するデータベース

## セットアップ

### 1. 依存パッケージのインストール

```bash
cd bot
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 環境変数の設定

リポジトリルートに `.env` を作成：

```env
# Slack
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...

# Gemini
GEMINI_API_KEY=...

# Supabase
NEXT_PUBLIC_SUPABASE_URL=https://xxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
```

### 3. Slack App の設定

[api.slack.com/apps](https://api.slack.com/apps) でアプリを作成・設定：

- **Socket Mode**：有効化
- **Event Subscriptions**：`reaction_added` を Subscribe
- **Bot Token Scopes**：`channels:history`, `reactions:read`, `files:write`, `chat:write`

### 4. 起動

```bash
python bot/main.py
```

## 動作フロー

1. メンバーがSlackメッセージに 🗓️ スタンプを押す
2. Botがメッセージ本文を取得
3. Gemini AIで日程情報（タイトル・開始・終了・場所）を抽出
4. Supabaseの `events` テーブルに保存
5. スレッドに返信：
   - Google カレンダー追加リンク
   - `.ics` ファイル（iPhone カレンダー用）

## 注意事項

- 年が明記されていない日程は現在年を自動補完（10月以降に投稿された1〜3月の予定は翌年扱い）
- 同じメッセージへの重複スタンプは無視（`slack_thread_ts` でdedup）
- Botは常時起動が必要（ローカル実行 or Railway/Fly.io などへデプロイ推奨）
