import { useEffect, useMemo, useState } from "react";

type Video = {
  video_id: string;
  webpage_url: string;
  title?: string | null;
  uploader?: string | null;
  upload_date?: string | null;
  duration?: number | null;
  view_count?: number | null;
  is_short?: number | null;
};

type DownloadJob = {
  job_id: string;
  video_id: string;
  status: "queued" | "running" | "success" | "failed";
  progress: number;
  output_path?: string | null;
  error_message?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: {
  "Content-Type": "application/json",
  "X-API-Key": import.meta.env.VITE_API_KEY,
  ...(init?.headers || {}),
},
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${txt}`);
  }
  return res.json() as Promise<T>;
}

export default function App() {
  // filters (對應你後端 /videos 的 query 參數)
  const [q, setQ] = useState("");
  const [isShort, setIsShort] = useState<"" | "1" | "0">("1");
  const [minViews, setMinViews] = useState("");
  const [maxDuration, setMaxDuration] = useState("");

  // scan channel
  const [channel, setChannel] = useState("");
  const [scanShorts, setScanShorts] = useState(true);
  const [scanVideos, setScanVideos] = useState(true);
  const [scanStreams, setScanStreams] = useState(false);
  const [scanMaxItems, setScanMaxItems] = useState(30);
  // add-by-url
  const [url, setUrl] = useState("");

  const [videos, setVideos] = useState<Video[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // 下載 jobs：用 video_id 當 key
  const [jobs, setJobs] = useState<Record<string, DownloadJob>>({});

  const queryString = useMemo(() => {
    const p = new URLSearchParams();
    if (q.trim()) p.set("q", q.trim());
    if (isShort !== "") p.set("is_short", isShort);
    if (minViews.trim()) p.set("min_views", minViews.trim());
    if (maxDuration.trim()) p.set("max_duration", maxDuration.trim());
    const s = p.toString();
    return s ? `?${s}` : "";
  }, [q, isShort, minViews, maxDuration]);

  async function loadVideos() {
    setErr(null);
    setLoading(true);
    try {
      const data = await api<Video[]>(`/videos${queryString}`);
      setVideos(data);
await syncJobsForVideos(data);
    } catch (e: any) {
      setErr(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadVideos();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryString]);

  async function addByUrl() {
    setErr(null);
    const u = url.trim();
    if (!u) return;
    try {
      await api(`/videos/by_url`, { method: "POST", body: JSON.stringify({ url: u }) });
      setUrl("");
      await loadVideos();
    } catch (e: any) {
      setErr(e.message || String(e));
    }
  }
  async function scanChannel() {
    setErr(null);
    const ch = channel.trim();
    if (!ch) return;

    try {
      const max = Math.max(1, Math.min(500, scanMaxItems));

    await api(`/sources/scan`, {
      method: "POST",
      body: JSON.stringify({
        channel: ch,
        include_shorts: scanShorts,
        include_videos: scanVideos,
        include_streams: scanStreams,
        max_items: max,
      }),
    });

      // ✅ 掃完自動切到 shorts（不直接呼叫 loadVideos，讓 useEffect 接手）
      setIsShort("1");
    } catch (e: any) {
      setErr(e.message || String(e));
    }
  }
  async function startDownload(video: Video) {
    setErr(null);
    try {
      // 你的 /downloads 已做去重：同一 video_id 不會重複 enqueue
      const created = await api<{ job_id: string; status: string; output_path?: string }>(`/downloads`, {
        method: "POST",
        body: JSON.stringify({ video_id: video.video_id }),
      });

      // 先拉一次 job detail（如果後端還沒建好，也至少有 job_id）
      const job = await api<DownloadJob>(`/downloads/${created.job_id}`);
      setJobs((prev) => ({ ...prev, [video.video_id]: job }));

      // 只有 queued/running 才輪詢
      if (job.status === "queued" || job.status === "running") {
        pollJob(video.video_id, job.job_id);
      }
    } catch (e: any) {
      setErr(e.message || String(e));
    }
  }

  async function pollJob(videoId: string, jobId: string) {
    // 簡單輪詢：每 1 秒抓一次，直到 success/failed
    const tick = async () => {
      try {
        const job = await api<DownloadJob>(`/downloads/${jobId}`);
        setJobs((prev) => ({ ...prev, [videoId]: job }));
        if (job.status === "queued" || job.status === "running") {
          setTimeout(tick, 1000);
        }
      } catch (e) {
        // 忽略輪詢中的暫時錯誤
        setTimeout(tick, 1500);
      }
    };
    tick();
  }

async function syncJobsForVideos(vs: Video[]) {
  const ids = vs.map(v => v.video_id);
  const data = await api<DownloadJob[]>(`/downloads/by_videos`, {
    method: "POST",
    body: JSON.stringify({ video_ids: ids }),
  });

  const next: Record<string, DownloadJob> = {};
  for (const j of data) next[j.video_id] = j;
  setJobs(next);

  Object.values(next).forEach((job) => {
    if (job.status === "queued" || job.status === "running") pollJob(job.video_id, job.job_id);
  });
}
async function downloadFile(jobId: string, videoId: string) {
  const key = import.meta.env.VITE_API_KEY;
  if (!key) throw new Error("Missing VITE_API_KEY");

  const res = await fetch(`/api/downloads/${jobId}/file`, {
    headers: { "X-API-Key": key },
  });

  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${txt}`);
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
  a.download = `${videoId}.mp4`;
  document.body.appendChild(a);
  a.click();
  a.remove();

  URL.revokeObjectURL(url);
}
  return (
    <div style={{ fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif", padding: 16, maxWidth: 1100, margin: "0 auto" }}>
      <h2 style={{ margin: "8px 0 16px" }}>YT GUI</h2>

      {/* Add by URL */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <input
          style={{ flex: 1, padding: 10 }}
          placeholder="貼上 YouTube Shorts URL → 入庫"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => (e.key === "Enter" ? addByUrl() : null)}
        />
        <button style={{ padding: "10px 14px" }} onClick={addByUrl}>Add</button>
        <button style={{ padding: "10px 14px" }} onClick={loadVideos}>Refresh</button>
      </div>
      {/* Scan Channel */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, alignItems: "center", flexWrap: "wrap" }}>
        <input
          style={{ flex: 1, minWidth: 240, padding: 10 }}
          placeholder="輸入 channel：InnahBee / @InnahBee / https://youtube.com/@InnahBee"
          value={channel}
          onChange={(e) => setChannel(e.target.value)}
          onKeyDown={(e) => (e.key === "Enter" ? scanChannel() : null)}
        />

        <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <input type="checkbox" checked={scanShorts} onChange={(e) => setScanShorts(e.target.checked)} />
          Shorts
        </label>

        <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <input type="checkbox" checked={scanVideos} onChange={(e) => setScanVideos(e.target.checked)} />
          Videos
        </label>

        <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <input type="checkbox" checked={scanStreams} onChange={(e) => setScanStreams(e.target.checked)} />
          Streams
        </label>

              <input
        type="number"
        min={1}
        step={1}
        style={{ width: 110, padding: 10 }}
        value={scanMaxItems}
        onChange={(e) => {
          const n = parseInt(e.target.value || "30", 10);
          setScanMaxItems(Number.isFinite(n) && n > 0 ? n : 30);
        }}
      />

        <button style={{ padding: "10px 14px" }} onClick={scanChannel}>
          Scan
        </button>
      </div>
      {/* Filters */}
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr", gap: 8, marginBottom: 12 }}>
        <input style={{ padding: 10 }} placeholder="搜尋 title/uploader（q）" value={q} onChange={(e) => setQ(e.target.value)} />
        <select style={{ padding: 10 }} value={isShort} onChange={(e) => setIsShort(e.target.value as any)}>
          <option value="">全部</option>
          <option value="1">Shorts</option>
          <option value="0">非 Shorts</option>
        </select>
        <input style={{ padding: 10 }} placeholder="min_views" value={minViews} onChange={(e) => setMinViews(e.target.value)} />
        <input style={{ padding: 10 }} placeholder="max_duration" value={maxDuration} onChange={(e) => setMaxDuration(e.target.value)} />
      </div>

      {err && (
        <div style={{ background: "#ffecec", border: "1px solid #ffb3b3", padding: 10, marginBottom: 12, whiteSpace: "pre-wrap" }}>
          {err}
        </div>
      )}

      {loading ? <div>Loading...</div> : null}

      {/* Table */}
      <table width="100%" cellPadding={10} style={{ borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>
            <th>Title</th>
            <th>Uploader</th>
            <th>Views</th>
            <th>Duration</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {videos.map((v) => {
            return (
              <tr key={v.video_id} style={{ borderBottom: "1px solid #f0f0f0", verticalAlign: "top" }}>
                <td>
                  <div style={{ fontWeight: 600 }}>{v.title || "(no title)"}</div>
                  <div style={{ fontSize: 12, opacity: 0.75 }}>
                    <a href={v.webpage_url} target="_blank" rel="noreferrer">{v.video_id}</a>
                  </div>
                </td>
                <td>{v.uploader || "-"}</td>
                <td>{v.view_count ?? "-"}</td>
                <td>{v.duration ?? "-"}</td>
                <td>
  <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
    <button onClick={() => startDownload(v)}>
      {jobs[v.video_id]?.status === "success" ? "Re-check" : "Download"}
    </button>

    {jobs[v.video_id] ? (
      <>
        <span style={{ fontSize: 12, opacity: 0.8 }}>
          {jobs[v.video_id].status} ({jobs[v.video_id].progress}%)
        </span>

        {jobs[v.video_id].status === "success" ? (
          <button onClick={() => downloadFile(jobs[v.video_id].job_id, v.video_id)}>Get File</button>
        ) : null}

        {jobs[v.video_id].status === "failed" && jobs[v.video_id].error_message ? (
          <span style={{ color: "#b00020", fontSize: 12 }}>{jobs[v.video_id].error_message}</span>
        ) : null}
      </>
    ) : null}
  </div>
</td>
              </tr>
            );
          })}
          {videos.length === 0 ? (
            <tr><td colSpan={5} style={{ padding: 16, opacity: 0.7 }}>No videos</td></tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}
