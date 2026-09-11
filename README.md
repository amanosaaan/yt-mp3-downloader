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

## UR賃貸空室通知(おまけ)

`ur_vacancy_notifier/` に、UR賃貸住宅の空室状況を定期チェックしてメール通知する
独立したスクリプトを同梱しています。詳細は `ur_vacancy_notifier/README.md` を参照してください。
