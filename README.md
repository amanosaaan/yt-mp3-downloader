# yt-mp3-downloader

YouTubeのURLを貼り付けてMP3(音声のみ)としてダウンロードするローカルWebアプリ。

※ 著作権で保護されたコンテンツのダウンロードは、著作権者の許諾がある場合や、私的利用など法律で認められた範囲でのみ行ってください。YouTubeの利用規約も確認してください。

## セットアップ

```bash
pip install -r requirements.txt
```

ffmpeg が別途必要です（PATHに通っていること）。

## 起動

```bash
python app.py
```

ブラウザで `http://127.0.0.1:5000` を開き、YouTubeのURLを入力して「MP3に変換」を押してください。

---

# 体組成ログ（ジム体重記録アプリ）

ジムの体組成計の値（体重・体脂肪率・骨格筋量・内臓脂肪・身長）を記録するスマホ向けWebアプリ。
データは Google スプレッドシートに保存し、GAS（Google Apps Script）を API として使います。画面は GitHub Pages で公開します。

- 画面: `docs/`（`docs/index.html`, `docs/config.js`）
- GAS: `gas/Code.gs`

## 機能

- 記録の入力（日付・体重・体脂肪率・骨格筋量・内臓脂肪・身長・メモ）。身長は前回の値が自動で入ります
- 最新値の表示と前回比（BMI・体脂肪量は自動計算）
- 項目・期間別の推移グラフと表表示
- 履歴の編集・削除、CSV書き出し
- GAS 未接続でも端末内（localStorage）に保存できます。あとからスプレッドシートへまとめて送れます

## セットアップ

1. **GAS**: https://script.google.com で新しいプロジェクトを作り、`gas/Code.gs` を貼り付けて保存
2. 関数 `setup` を実行して権限を承認（「ジム体組成記録」スプレッドシートが自動で作られます）
3. 「デプロイ」→「新しいデプロイ」→「ウェブアプリ」／実行するユーザー: 自分／アクセスできるユーザー: 全員
4. **GitHub Pages**: リポジトリの Settings → Pages → Source「Deploy from a branch」→ Branch `main` / `/docs` → Save
5. `https://amanosaaan.github.io/yt-mp3-downloader/` を開き、「設定」タブに GAS の URL（…/exec）を貼り付け

URL を知っている人は読み書きできるので、気になる場合は `Code.gs` の `TOKEN` に合言葉を設定し、アプリの設定にも同じ合言葉を入れてください。
`docs/config.js` の `apiUrl` に URL を書いておくと、どの端末でも最初から接続された状態になります（合言葉はここに書かないでください）。

GAS のコードを変更したときは「デプロイを管理」→ 編集 → バージョン「新バージョン」で更新すると URL が変わりません。
