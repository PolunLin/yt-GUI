FROM python:3.12-slim

WORKDIR /app

# 系統依賴：yt-dlp 合併 mp4 需要 ffmpeg；psycopg 連線常需要 libpq
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libpq5 nodejs\
    && rm -rf /var/lib/apt/lists/*

# 1) 固定 uv 版本（正常專案會 pin；不要每次 build 裝到不同 uv）
#    你也可以改成官方建議的做法：COPY --from=ghcr.io/astral-sh/uv:... /uv /uvx /bin/
RUN pip install --no-cache-dir "uv==0.9.18"

# 2) 固定 venv 路徑（避免 .venv 不小心不在你以為的位置）
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
ENV UV_NO_DEV=1

# 3) 依賴層：先 copy lock 檔再 sync（利於 Docker cache）
COPY pyproject.toml uv.lock /app/
RUN uv sync --locked --no-install-project

# 4) 專案層：再 copy 程式碼，安裝專案本身
COPY . /app
RUN uv sync --locked

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "apps.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]