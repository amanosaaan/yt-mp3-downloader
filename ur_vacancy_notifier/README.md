# UR空室通知スクリプト

指定したUR賃貸住宅のページを定期的にチェックし、空きが出たらメールで通知します。
`yt-mp3-downloader` 本体(Flaskアプリ)とは独立した、単体で動くスクリプトです。

## 注意事項

- UR公式サイトの実際のHTMLを開発環境から取得できなかったため、空室判定は
  「明記された空き戸数」「よくある『空きなし』文言」「号室らしき行の有無」
  「ページ内容のハッシュ変化」を組み合わせたフォールバック方式で作っています。
  **初回は必ず `--once` で手動実行し、ログの `[判定]` 行が実際のページの
  空室状況と一致しているか確認してください。** サイトの構造が想定と違う場合は
  `notifier.py` の `NO_VACANCY_PHRASES` や `extract_vacancy_info()` を
  実際のページに合わせて調整してください。
- 個人利用目的の巡回を想定しています。アクセス頻度は常識的な間隔(数十分〜1時間に1回程度)
  にし、UR公式サイトの利用規約に従ってください。

## セットアップ

```bash
cd ur_vacancy_notifier
pip install -r requirements.txt
```

## 環境変数

| 変数名 | 説明 | 例 |
|---|---|---|
| `WATCH_URLS` | 監視するURL(カンマ区切りで複数可)。省略時は既定のUR物件ページ | `https://www.ur-net.go.jp/chintai/sp/kansai/hyogo/80_4410.html` |
| `STATE_FILE` | 前回チェック結果を保存するJSONのパス | `state.json` |
| `SMTP_HOST` | SMTPサーバー | `smtp.gmail.com` |
| `SMTP_PORT` | SMTPポート | `587` |
| `SMTP_USER` | SMTPログインユーザー | `you@gmail.com` |
| `SMTP_PASS` | SMTPパスワード(Gmailは**アプリパスワード**を使用) | `xxxxxxxxxxxxxxxx` |
| `MAIL_FROM` | 差出人アドレス(省略時は`SMTP_USER`) | `you@gmail.com` |
| `MAIL_TO` | 通知先アドレス(カンマ区切りで複数可) | `you@gmail.com` |

Gmailを使う場合は、Googleアカウントで2段階認証を有効にした上で
「アプリパスワード」を発行し、`SMTP_PASS` にはそのアプリパスワードを設定してください
(通常のログインパスワードはSMTP認証に使えません)。

## 実行方法

1回だけチェック(cron向け):

```bash
export SMTP_HOST=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USER=you@gmail.com
export SMTP_PASS=xxxxxxxxxxxxxxxx
export MAIL_TO=you@gmail.com
python notifier.py --once
```

ループで監視(例: 10分間隔):

```bash
python notifier.py --interval 600
```

## cronでの定期実行例

`crontab -e` で以下のように15分おきに実行するよう登録できます。

```
*/15 * * * * cd /path/to/yt-mp3-downloader/ur_vacancy_notifier && \
  SMTP_HOST=smtp.gmail.com SMTP_PORT=587 \
  SMTP_USER=you@gmail.com SMTP_PASS=xxxxxxxxxxxxxxxx \
  MAIL_TO=you@gmail.com \
  /usr/bin/python3 notifier.py --once >> notifier.log 2>&1
```

## GitHub Actionsでの定期実行例

自前のサーバーがなくても、このリポジトリのGitHub Actionsで定期実行できます。
`.github/workflows/ur-vacancy-check.yml` を追加済みです。使うには、リポジトリの
Settings → Secrets and variables → Actions で以下のSecretsを登録してください。

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASS`
- `MAIL_TO`

ワークフローは15分おきに `notifier.py --once` を実行し、状態ファイル
(`state.json`)に変化があればリポジトリへコミットして次回実行時の
「前回との差分」判定に使います。
