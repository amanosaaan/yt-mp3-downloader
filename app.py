import os
import re
import tempfile
import threading
import uuid

from flask import Flask, Response, jsonify, request, send_file
import yt_dlp

app = Flask(__name__)

DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "yt_mp3_downloader")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

YOUTUBE_URL_RE = re.compile(
    r"^https?://(www\.)?(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)[\w-]+"
)

# job_id -> {"status": "downloading"|"done"|"error", "progress": float, "filename": str|None, "error": str|None}
jobs = {}
jobs_lock = threading.Lock()


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    return name.strip()[:150] or "audio"


def run_download(job_id: str, url: str):
    def progress_hook(d):
        with jobs_lock:
            job = jobs.get(job_id)
            if not job:
                return
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                downloaded = d.get("downloaded_bytes", 0)
                job["progress"] = (downloaded / total * 100) if total else 0
            elif d["status"] == "finished":
                job["progress"] = 100

    out_template = os.path.join(DOWNLOAD_DIR, f"{job_id}.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "progress_hooks": [progress_hook],
        "noplaylist": True,
        "js_runtimes": {"node": {}},
        "remote_components": ["ejs:github"],
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = sanitize_filename(info.get("title", "audio"))

        mp3_path = os.path.join(DOWNLOAD_DIR, f"{job_id}.mp3")
        if not os.path.exists(mp3_path):
            raise RuntimeError("MP3への変換に失敗しました")

        with jobs_lock:
            jobs[job_id]["status"] = "done"
            jobs[job_id]["progress"] = 100
            jobs[job_id]["filename"] = f"{title}.mp3"
            jobs[job_id]["path"] = mp3_path
    except Exception as e:
        with jobs_lock:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(e)


@app.route("/")
def index():
    return send_file("static/index.html")


@app.route("/api/start", methods=["POST"])
def start():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()

    if not url or not YOUTUBE_URL_RE.match(url):
        return jsonify({"error": "有効なYouTubeのURLを入力してください"}), 400

    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {"status": "downloading", "progress": 0, "filename": None, "error": None}

    thread = threading.Thread(target=run_download, args=(job_id, url), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/status/<job_id>")
def status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify({"error": "ジョブが見つかりません"}), 404
        return jsonify(
            {
                "status": job["status"],
                "progress": job["progress"],
                "filename": job["filename"],
                "error": job["error"],
            }
        )


@app.route("/api/file/<job_id>")
def get_file(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job or job["status"] != "done":
            return jsonify({"error": "ファイルの準備ができていません"}), 404
        path = job["path"]
        filename = job["filename"]

    return send_file(path, as_attachment=True, download_name=filename, mimetype="audio/mpeg")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
