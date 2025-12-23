import os
import re
import glob
import yt_dlp


def extract_info(url: str) -> dict:
    opts = {
        "quiet": True,
        "skip_download": True,
        "ignoreerrors": True,
        "retries": 3,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise RuntimeError("yt-dlp returned empty info")
    return info


def _safe_dir(name: str | None) -> str:
    s = (name or "unknown").strip()
    s = re.sub(r"[^\w\-\.\s]", "_", s)  # 移除不安全字元
    s = re.sub(r"\s+", " ", s).strip()
    return s[:80] if s else "unknown"


def download_video(url: str, base_outdir: str, video_id: str, uploader: str | None, max_height: int = 1080) -> str:
    uploader_dir = _safe_dir(uploader)
    outdir = os.path.join(base_outdir, uploader_dir)
    os.makedirs(outdir, exist_ok=True)

    outtmpl = os.path.join(outdir, f"{video_id}.%(ext)s")

    ydl_opts = {
        "outtmpl": outtmpl,
        "format": f"bestvideo[height<={max_height}]+bestaudio/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "retries": 3,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    # 保守找實際輸出（避免極端狀況不是 mp4）
    candidates = glob.glob(os.path.join(outdir, f"{video_id}.*"))
    if not candidates:
        raise RuntimeError("download finished but output file not found")

    # 優先 mp4
    mp4 = [p for p in candidates if p.lower().endswith(".mp4")]
    return mp4[0] if mp4 else candidates[0]