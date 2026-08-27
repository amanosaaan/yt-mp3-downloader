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


MIME_TYPES = {
    "mp3": "audio/mpeg",
    "mp4": "video/mp4",
}


def run_download(job_id: str, url: str, fmt: str):
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
        "outtmpl": out_template,
        "progress_hooks": [progress_hook],
        "noplaylist": True,
        "js_runtimes": {"node": {}},
        "remote_components": ["ejs:github"],
        "quiet": True,
        "no_warnings": True,
    }

    if fmt == "mp4":
        ydl_opts["format"] = "bestvideo*+bestaudio/best"
        ydl_opts["merge_output_format"] = "mp4"
    else:
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = sanitize_filename(info.get("title", "video"))

        out_path = os.path.join(DOWNLOAD_DIR, f"{job_id}.{fmt}")
        if not os.path.exists(out_path):
            raise RuntimeError(f"{fmt.upper()}への変換に失敗しました")

        with jobs_lock:
            jobs[job_id]["status"] = "done"
            jobs[job_id]["progress"] = 100
            jobs[job_id]["filename"] = f"{title}.{fmt}"
            jobs[job_id]["path"] = out_path
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
    fmt = (data.get("format") or "mp3").strip().lower()

    if not url or not YOUTUBE_URL_RE.match(url):
        return jsonify({"error": "有効なYouTubeのURLを入力してください"}), 400

    if fmt not in ("mp3", "mp4"):
        return jsonify({"error": "形式はmp3かmp4を指定してください"}), 400

    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {"status": "downloading", "progress": 0, "filename": None, "error": None}

    thread = threading.Thread(target=run_download, args=(job_id, url, fmt), daemon=True)
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

    ext = filename.rsplit(".", 1)[-1].lower()
    mimetype = MIME_TYPES.get(ext, "application/octet-stream")
    return send_file(path, as_attachment=True, download_name=filename, mimetype=mimetype)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
