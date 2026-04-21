# DSC Slack Calendar Bot

> **⚠️ このリポジトリは [dsc_schedule](https://github.com/Shun523/dsc_schedule) に統合されました。**
> 最新のコードは `dsc_schedule` リポジトリの `bot/` ディレクトリを参照してください。
> セットアップ・運用もそちらのREADMEに従ってください。

---

Slackの🗓️スタンプを検知してメッセージから日程を自動抽出し、カレンダーに登録するBot。

## 機能

- 🗓️（spiral_calendar_pad）スタンプが押されたメッセージを検知
- Gemini AIでイベントタイトル・日時・場所を自動抽出
- dsc_scheduleのAPIルート（`/api/bot/events`）経由でイベントを保存
- `.ics`ファイルをスレッドに投稿（Google カレンダー・iPhone カレンダー対応）

## システム構成

```
[Slack] ──→ [このBot] ──→ [dsc_schedule API] ──→ [Supabase DB]
                                  ↑
                    dsc_scheduleリポジトリと組み合わせて使用
```

このBotは単体では動作しません。[dsc_schedule](https://github.com/Shun523/dsc_schedule) のNext.jsアプリが起動している必要があります。

## セットアップ

[dsc_schedule](https://github.com/Shun523/dsc_schedule) リポジトリのセットアップ手順を参照してください。

### 環境変数

```env
# Slack
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...

# Gemini
GEMINI_API_KEY=...

# dsc_scheduleアプリのURL（本番: https://your-app.vercel.app）
NEXT_APP_URL=http://localhost:3000

# Bot認証用シークレット（openssl rand -hex 32 で生成）
BOT_API_SECRET=...
```

### Slack App の設定

[api.slack.com/apps](https://api.slack.com/apps) でアプリを作成・設定：

- **Socket Mode**：有効化
- **Event Subscriptions**：`reaction_added` を Subscribe
- **Bot Token Scopes**：`channels:history`, `reactions:read`, `files:write`, `chat:write`

### 起動

```bash
cd bot
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

## 動作フロー

1. メンバーがSlackメッセージに 🗓️ スタンプを押す
2. Botがメッセージ本文を取得
3. Gemini AIで日程情報（タイトル・開始・終了・場所）を抽出
4. dsc_scheduleの `/api/bot/events` APIにPOSTしてイベントを保存
5. スレッドに返信：
   - Google カレンダー追加リンク
   - `.ics` ファイル（iPhone カレンダー用）

## 注意事項

- 年が明記されていない日程は現在年を自動補完（10月以降に投稿された1〜3月の予定は翌年扱い）
- 同じメッセージへの重複スタンプは無視（`slack_thread_ts` でdedup）
- Botは常時起動が必要（ローカル実行 or Railway/Fly.io などへデプロイ推奨）
