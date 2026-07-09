"""
AGVmon 更新服务器 — 单文件独立部署

启动:
    uv run python update_server.py
    # 或
    python update_server.py --port 9000 --api-key my-secret-key

客户端检查更新:
    GET /api/update/latest.json          # stable 通道
    GET /api/update/latest-beta.json     # beta 通道

客户端下载:
    GET /api/update/download/<filename>

构建脚本上传:
    POST /api/update/upload              # multipart: zip + manifest 字段
"""

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

_dotenv_path = Path(__file__).parent / ".env"
if _dotenv_path.exists():
    load_dotenv(_dotenv_path)
# ── Config ────────────────────────────────────────────────────

API_KEY = os.environ.get("UPDATE_API_KEY", "agvmon-update-key")
PORT = int(os.environ.get("UPDATE_PORT", "9000"))
HOST = os.environ.get("UPDATE_HOST", "0.0.0.0")
UPLOAD_DIR = Path(os.environ.get("UPDATE_DIR", Path(__file__).parent / "updates"))
MANIFEST_FILE = "latest.json"
BETA_MANIFEST_FILE = "latest-beta.json"

# ── App ───────────────────────────────────────────────────────

app = FastAPI(title="AGVmon Update Server", docs_url=None, redoc_url=None)

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ── Root page ──────────────────────────────────────────────────


@app.get("/")
def root():
    """首页 — 显示当前版本信息和可用文件。"""
    stable_path = UPLOAD_DIR / MANIFEST_FILE
    beta_path = UPLOAD_DIR / BETA_MANIFEST_FILE

    def load_manifest(p):
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return None

    stable = load_manifest(stable_path)
    beta = load_manifest(beta_path)

    # 列出所有 zip 文件
    files = sorted(
        UPLOAD_DIR.glob("*.zip"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    def file_row(f, tag=""):
        size_mb = f.stat().st_size / (1024 * 1024)
        return (
            f'<tr><td><a href="/api/update/download/{f.name}">{f.name}</a> {tag}</td>'
            f"<td>{size_mb:.1f} MB</td></tr>"
        )

    rows = []
    for f in files:
        tag = ""
        if stable and f.name == stable.get("url"):
            tag = '<span style="color:#18a058">[stable]</span>'
        elif beta and f.name == beta.get("url"):
            tag = '<span style="color:#f0a020">[beta]</span>'
        rows.append(file_row(f, tag))

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>AGVmon Update Server</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 720px; margin: 40px auto; padding: 0 16px; color: #333; }}
  h1 {{ font-size: 24px; }}
  .card {{ background: #f5f5f5; border-radius: 8px; padding: 16px; margin: 12px 0; }}
  .card h3 {{ margin: 0 0 8px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #e0e0e0; }}
  code {{ background: #e8e8e8; padding: 2px 6px; border-radius: 3px; font-size: 13px; }}
  .empty {{ color: #999; }}
</style>
</head>
<body>
<h1>AGVmon Update Server</h1>

<div class="card">
  <h3>stable</h3>
  {f"<p>v{stable['version']} · {stable['build_time']} · git: {stable['git_hash']}<br><code>{stable['url']}</code> ({stable['size'] / 1024 / 1024:.1f} MB)</p>" if stable else '<p class="empty">暂无版本</p>'}
</div>

<div class="card">
  <h3>beta</h3>
  {f"<p>v{beta['version']} · {beta['build_time']} · git: {beta['git_hash']}<br><code>{beta['url']}</code> ({beta['size'] / 1024 / 1024:.1f} MB)</p>" if beta else '<p class="empty">暂无 beta 版本</p>'}
</div>

<div class="card">
  <h3>所有文件</h3>
  <table>{"".join(rows) if rows else '<tr><td class="empty">暂无文件</td></tr>'}</table>
</div>

<p style="color:#999;font-size:12px;">
  API: <code>GET /api/update/latest.json</code> ·
  <code>GET /api/update/download/&lt;file&gt;</code> ·
  <code>POST /api/update/upload</code>
</p>
</body>
</html>"""
    return HTMLResponse(html)

# ── Auth ──────────────────────────────────────────────────────


def verify_api_key(x_api_key: str = Header(None)) -> str:
    """Verify API key for upload endpoints."""
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="无效的 API Key")
    return x_api_key


# ── Check endpoints (public, no auth) ─────────────────────────


@app.get("/api/update/latest.json")
def get_latest():
    """返回 stable 通道最新版本清单。"""
    path = UPLOAD_DIR / MANIFEST_FILE
    if not path.exists():
        return JSONResponse({"error": "暂无可用版本"}, status_code=404)
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))


@app.get("/api/update/latest-beta.json")
def get_latest_beta():
    """返回 beta 通道最新版本清单。"""
    path = UPLOAD_DIR / BETA_MANIFEST_FILE
    if not path.exists():
        return JSONResponse({"error": "暂无 beta 版本"}, status_code=404)
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))


# ── Download endpoint (public, no auth) ───────────────────────


@app.get("/api/update/download/{filename}")
def download_file(filename: str):
    """下载更新包。"""
    # 安全检查：防止路径穿越
    safe_name = Path(filename).name
    file_path = UPLOAD_DIR / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(
        file_path,
        media_type="application/zip",
        filename=safe_name,
    )


# ── Upload endpoint (requires auth) ───────────────────────────


@app.post("/api/update/upload")
async def upload_update(
    file: UploadFile = File(...),
    version: str = "0.0.0",
    build_time: str = "",
    git_hash: str = "",
    channel: str = "stable",
    x_api_key: str = Header(None),
):
    """
    上传更新包 + 自动更新版本清单。

    multipart/form-data:
        file:       ZIP 文件
        version:    版本号 (e.g. "0.1.0.89")
        build_time: 构建时间
        git_hash:   Git 短哈希
        channel:    stable | beta
    """
    import re

    verify_api_key(x_api_key)

    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="仅支持 .zip 文件")

    # 从文件名自动解析版本信息: agvmon_v0.1.0.89_2265893_20260710_120000.zip
    parsed = re.match(r"agvmon_v([\d.]+)_(\w+)_(\d{8}_\d{6})\.zip", file.filename)
    if parsed:
        if version == "0.0.0":
            version = parsed.group(1)
        if not git_hash:
            git_hash = parsed.group(2)

    safe_name = Path(file.filename).name
    dest = UPLOAD_DIR / safe_name

    # 保存 ZIP
    sha256_hasher = hashlib.sha256()
    file_size = 0

    with open(dest, "wb") as f:
        while chunk := await file.read(8 * 1024 * 1024):  # 8MB chunks
            f.write(chunk)
            sha256_hasher.update(chunk)
            file_size += len(chunk)

    sha256_hex = sha256_hasher.hexdigest()

    # 生成/更新版本清单
    manifest_name = MANIFEST_FILE if channel == "stable" else BETA_MANIFEST_FILE
    manifest = {
        "version": version,
        "build_time": build_time
        or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "git_hash": git_hash,
        "url": safe_name,
        "size": file_size,
        "sha256": sha256_hex,
    }

    manifest_path = UPLOAD_DIR / manifest_name
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # 记录上传历史
    log_entry = {
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "version": version,
        "file": safe_name,
        "size": file_size,
        "channel": channel,
    }
    _append_upload_log(log_entry)

    return {
        "status": "ok",
        "manifest": manifest,
        "manifest_file": manifest_name,
    }


# ── Upload history ────────────────────────────────────────────


def _append_upload_log(entry: dict):
    log_path = UPLOAD_DIR / "upload_history.json"
    history = []
    if log_path.exists():
        try:
            history = json.loads(log_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            history = []
    history.insert(0, entry)
    # Keep last 100 entries
    history = history[:100]
    log_path.write_text(
        json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8"
    )


@app.get("/api/update/history")
def get_history(x_api_key: str = Header(None)):
    """查看上传历史（需要认证）。"""
    verify_api_key(x_api_key)
    log_path = UPLOAD_DIR / "upload_history.json"
    if not log_path.exists():
        return []
    return json.loads(log_path.read_text(encoding="utf-8"))


# ── Health check ──────────────────────────────────────────────


@app.get("/api/update/health")
def health():
    """健康检查。"""
    stable = (UPLOAD_DIR / MANIFEST_FILE).exists()
    beta = (UPLOAD_DIR / BETA_MANIFEST_FILE).exists()
    return {
        "status": "ok",
        "stable": stable,
        "beta": beta,
        "time": datetime.now(timezone.utc).isoformat(),
    }


# ── Main ──────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AGVmon Update Server")
    parser.add_argument("--host", default=HOST, help=f"监听地址 (默认: {HOST})")
    parser.add_argument(
        "--port", type=int, default=PORT, help=f"监听端口 (默认: {PORT})"
    )
    parser.add_argument("--api-key", default=API_KEY, help="上传 API Key")
    parser.add_argument(
        "--dir", default=str(UPLOAD_DIR), help=f"文件存储目录 (默认: {UPLOAD_DIR})"
    )
    args = parser.parse_args()

    API_KEY = args.api_key
    UPLOAD_DIR = Path(args.dir)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    print("AGVmon Update Server")
    print(f"  地址: http://{args.host}:{args.port}")
    print(f"  存储: {UPLOAD_DIR.absolute()}")
    print(f"  API Key: {API_KEY}")
    print("  检查更新: GET /api/update/latest.json")
    print("  下载文件: GET /api/update/download/<filename>")
    print("  上传更新: POST /api/update/upload")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
