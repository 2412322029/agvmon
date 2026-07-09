import asyncio
import json
import os

import httpx
from datetime import datetime
from ipaddress import ip_address

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import StreamingResponse

from util.agv_protocol_parser import AGVProtocolParser
from util.agvlog import (
    agv_log_dir,
    delete_agv_logs,
    find_str,
    get_pio_result,
    list_agv_logs,
    parse_agv_log,
)
from util.clean import _format_size
from util.logger import logger
from util.parse_wcs_log import MAX_FILES, WCSLOG_DIR, _collect_default_files, download_wcs_log, download_wcs_logbak, list_wcs_logbak, list_wcs_logs, parse

log_parser_router = APIRouter(
    prefix="/log_parser",
    tags=["log_parser"],
)

# ── 和 main.py tools clean 保持一致的固定目录 ──────────────────────────
_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "util", "data")
CLEAN_DIRS = {
    "wcslog": os.path.join(_BASE, "wcslog"),
    "logbak": os.path.join(_BASE, "wcslog", "logbak"),
    "agvlog": os.path.join(_BASE, "agvlog"),
}


# ── AGV Protocol ──────────────────────────────────────────────────────

@log_parser_router.get("/agv_protocol")
def parse_agv_protocol(data: str, type: str) -> dict:
    parser = AGVProtocolParser()
    if type.lower() == "agv":
        return parser.parse_agv_command(data)
    elif type.lower() == "eq":
        return parser.parse_eq_status(data)
    else:
        raise HTTPException(status_code=400, detail="Invalid type. Please specify 'agv' or 'eq'.")


# ── AGV Logs (本地文件管理) ────────────────────────────────────────────

@log_parser_router.get("/agv_logs")
async def api_list_agv_logs():
    return list_agv_logs()


@log_parser_router.delete("/agv_logs")
async def api_delete_agv_logs(filenames: list[str] | None = Body(None)):
    try:
        deleted = delete_agv_logs(filenames)
        return {"deleted": deleted, "count": len(deleted)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@log_parser_router.post("/agv_logs/parse")
async def api_parse_agv_log(filename: str = Body(..., description="AGV log filename, e.g. AGV_2026_04_24_13_01_15_CASTOR_1032")):
    try:
        txt_path, carid = await asyncio.to_thread(parse_agv_log, filename)
        return {"txt_path": txt_path, "carid": carid}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@log_parser_router.post("/agv_logs/batch_parse")
async def api_parse_agv_logs(filenames: list[str] = Body(..., description="AGV log filenames, max 5")):
    from util.agvlog import parse_agv_logs

    try:
        txt_files, carid = await asyncio.to_thread(parse_agv_logs, filenames)
        return {"txt_files": txt_files, "carid": carid}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@log_parser_router.post("/agv_logs/search")
async def api_search_agv_logs(
    filenames: list[str] = Body(..., description="Parsed txt file paths"),
    pattern: str = Body(..., description="Search pattern"),
):
    try:
        matches = await asyncio.to_thread(find_str, filenames, pattern)
        return {
            "count": len(matches),
            "matches": [{"line": ln, "content": content} for ln, content in matches],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── AGV 下载 + PIO 分析 (对应 CLI: tools agvlog IP_OR_CARID --pio ...) ──

def _format_size(size):
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


@log_parser_router.post("/agv_logs/download")
async def api_download_agv_logs(
    ip_or_carid: str = Body(..., description="AGV IP address or car ID (same as CLI positional arg)"),
    filenames: list[str] = Body([], description="Specific filenames to download, empty = download latest"),
    prefix: str = Body("/mnt/agv_log/", description="Remote log directory path"),
    count: int = Body(1, description="Number of latest files when filenames is empty"),
):
    """从 AGV 下载日志文件，通过 SSE 流式返回下载进度。
    和 CLI `tools agvlog <ip> --download <prefix> --count N` 行为一致。
    """
    return StreamingResponse(
        _sse_download(ip_or_carid, filenames, prefix, count, is_agvlog=True, need_agv_prefix=True),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@log_parser_router.post("/agv_logs/download_file")
async def api_download_file(
    ip_or_carid: str = Body(..., description="AGV IP address or car ID"),
    filenames: list[str] = Body(..., description="Filenames to download (required)"),
    prefix: str = Body("/mnt/agv_log/", description="Remote directory path"),
):
    """从 AGV 下载任意文件（不验证 AGV_ 前缀），通过 SSE 返回进度。
    和 CLI `tools agvlog <ip> --download <prefix> --files ...` 行为一致。
    """
    return StreamingResponse(
        _sse_download(ip_or_carid, filenames, prefix, 0, is_agvlog=False, need_agv_prefix=False),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@log_parser_router.post("/agv_logs/pio")
async def api_agvlog_pio(
    ip_or_carid: str = Body(..., description="AGV IP address or car ID (same as CLI positional arg)"),
    filenames: list[str] = Body([], description="Specific filenames to download, empty = download latest"),
    count: int = Body(1, description="Number of latest files when filenames is empty"),
):
    """下载 AGV 日志并解析 PIO 结果，通过 SSE 返回进度 + 最终 PIO 分析。
    和 CLI `tools agvlog <ip> --pio print` 行为一致。
    """
    return StreamingResponse(
        _sse_download_and_pio(ip_or_carid, filenames, count),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _sse_download(ip_or_carid, filenames, prefix, count, is_agvlog, need_agv_prefix):
    """SSE 生成器：下载 AGV 日志，逐事件报告进度。"""
    from util.agvlog import getip_from_carid, parse_time_from_filename
    from util.ssh import SSHManager

    # 解析 IP / carid
    carid = None
    if "." not in ip_or_carid and 0 < len(ip_or_carid) < 6:
        carid = ip_or_carid
        yield _sse("status", f"正在通过 carid={carid} 查找 IP ...")
        try:
            ip = await getip_from_carid(ip_or_carid)
            if not ip:
                yield _sse("error", f"未找到 carid={carid} 对应的 AGV IP")
                return
        except Exception as e:
            yield _sse("error", f"查询 IP 失败: {e}")
            return
    else:
        ip = ip_or_carid

    try:
        ip_address(ip)
    except ValueError:
        yield _sse("error", f"无效的 IP 地址: {ip}")
        return

    if not prefix.endswith("/"):
        prefix += "/"

    ssh = SSHManager(ip, username="root", password="")
    progress_queue: asyncio.Queue = asyncio.Queue()
    _current_file = {"name": ""}

    def progress_cb(downloaded, total):
        pct = round((downloaded / total) * 100, 1) if total > 0 else 0
        progress_queue.put_nowait({
            "type": "progress",
            "filename": _current_file["name"],
            "downloaded": downloaded,
            "total": total,
            "percentage": pct,
            "downloaded_str": _format_size(downloaded),
            "total_str": _format_size(total),
        })

    try:
        yield _sse("status", f"连接 {ip} ...")
        await ssh.agv_auto_connect()

        if not filenames:
            yield _sse("status", "列出远程文件 ...")
            res = await ssh.list_directory(path=f"/{prefix.strip('/')}")
            if need_agv_prefix:
                agv_files = [f for f in res if f.get("is_file") and f.get("name", "").startswith("AGV_")]
            else:
                agv_files = [f for f in res if f.get("is_file")]
            agv_files.sort(key=lambda x: parse_time_from_filename(x["name"]), reverse=True)
            filenames = [f["name"] for f in agv_files[:count]]
            yield _sse("status", f"找到 {len(filenames)} 个文件待下载: {filenames}")

        existing = set(os.listdir(agv_log_dir))
        downloaded = []

        for fname in filenames:
            _current_file["name"] = fname

            if is_agvlog and carid and not fname.endswith(carid):
                yield _sse("status", f"跳过 {fname} (carid 不匹配)")
                continue

            if fname in existing:
                yield _sse("status", f"文件已存在，跳过: {fname}")
                downloaded.append(fname)
                continue

            yield _sse("status", f"开始下载: {fname}")
            ok = await ssh.download_file(
                remote_path=f"{prefix}{fname}",
                local_path=agv_log_dir,
                callback=progress_cb,
            )

            # 排空进度事件
            while not progress_queue.empty():
                yield f"data: {json.dumps(progress_queue.get_nowait(), ensure_ascii=False)}\n\n"

            if ok:
                downloaded.append(fname)
                yield _sse("status", f"下载完成: {fname}")
            else:
                yield _sse("error", f"下载失败: {fname}")

        yield _sse("done", "", {"files": downloaded, "count": len(downloaded)})

    except Exception as e:
        logger.exception("下载AGV日志失败")
        yield _sse("error", str(e))
    finally:
        await ssh.disconnect()


async def _sse_download_and_pio(ip_or_carid, filenames, count):
    """SSE 生成器：下载 + PIO 分析，合并为一次请求。"""
    from util.agvlog import parse_agv_logs

    # 先下载
    downloaded = []
    async for event in _sse_download(ip_or_carid, filenames, "/mnt/agv_log/", count, is_agvlog=True, need_agv_prefix=True):
        yield event
        try:
            _, data = event.split("data: ", 1)
            msg = json.loads(data)
            if msg.get("type") == "done":
                downloaded = msg.get("files", [])
        except (ValueError, json.JSONDecodeError):
            pass

    if not downloaded:
        yield _sse("error", "没有成功下载的文件，无法进行 PIO 分析")
        return

    yield _sse("status", f"开始 PIO 分析，文件: {downloaded}")
    try:
        merged = await asyncio.to_thread(get_pio_result, downloaded)
        yield _sse("done", "", {"pio_groups": merged, "count": len(merged), "files": downloaded})
    except Exception as e:
        yield _sse("error", f"PIO 分析失败: {e}")


def _sse(event_type: str, message: str, extra: dict | None = None) -> str:
    payload = {"type": event_type, "message": message}
    if extra:
        payload.update(extra)
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@log_parser_router.post("/agv_logs/pio_local")
async def api_agvlog_pio_local(
    filenames: list[str] = Body(..., description="本地 AGV 日志文件名列表"),
):
    """对本地已下载的 AGV 日志文件执行 PIO 分析。"""
    from util.agvlog import get_pio_result

    try:
        merged = await asyncio.to_thread(get_pio_result, filenames)
        return {"pio_groups": merged, "count": len(merged), "files": filenames}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── AGV 远程文件列表 (对应 CLI: tools agvlog <ip> --ls <path>) ──

@log_parser_router.post("/agv_logs/ls")
async def api_ls_agv(
    ip_or_carid: str = Body(..., description="AGV IP address or car ID"),
    path: str = Body("/mnt", description="Remote directory path"),
):
    from util.agvlog import getip_from_carid
    from util.ssh import SSHManager

    if "." not in ip_or_carid and 0 < len(ip_or_carid) < 6:
        ip = await getip_from_carid(ip_or_carid)
        if not ip:
            raise HTTPException(status_code=404, detail=f"未找到 carid={ip_or_carid} 对应的 AGV IP")
    else:
        ip = ip_or_carid

    try:
        ip_address(ip)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的 IP 地址: {ip}")

    ssh = SSHManager(ip, username="root", password="")
    try:
        await ssh.agv_auto_connect()
        output, err = await ssh.execute_command_text(f"ls -l {path}", timeout=5)
        return {"output": output or err, "ip": ip, "path": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await ssh.disconnect()


@log_parser_router.post("/agv_logs/remote_files")
async def api_list_remote_agv_files(
    ip_or_carid: str = Body(..., description="AGV IP address or car ID"),
):
    """列出远程 AGV /mnt/agv_log/ 下以 AGV_ 开头的文件，用于下载下拉选择。"""
    from util.agvlog import getip_from_carid, parse_time_from_filename
    from util.ssh import SSHManager

    carid = None
    if "." not in ip_or_carid and 0 < len(ip_or_carid) < 6:
        carid = ip_or_carid
        ip = await getip_from_carid(ip_or_carid)
        if not ip:
            raise HTTPException(status_code=404, detail=f"未找到 carid={carid} 对应的 AGV IP")
    else:
        ip = ip_or_carid

    try:
        ip_address(ip)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的 IP 地址: {ip}")

    ssh = SSHManager(ip, username="root", password="")
    try:
        await ssh.agv_auto_connect()
        res = await ssh.list_directory(path="/mnt/agv_log")
        files = [
            f for f in res
            if f.get("is_file") and f.get("name", "").startswith("AGV_")
        ]
        files.sort(key=lambda x: parse_time_from_filename(x["name"]), reverse=True)
        return {
            "ip": ip,
            "carid": carid,
            "files": [{
                "name": f["name"],
                "size": f.get("size", 0),
                "size_str": _format_size(f.get("size", 0)),
                "mtime": f.get("mtime", ""),
            } for f in files],
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        await ssh.disconnect()


# ── WCS Logs (对应 CLI: tools wcslog [files] [-c code]) ─────────────────

def _trayid_to_hex(trayid: str) -> str:
    """将 TrayID 字符串转为 hex 字节串，用于在 response hex 中快速正则匹配。"""
    return "".join(f"{ord(c):02X}" for c in trayid)


def _resolve_wcs_path(filename: str) -> str:
    """安全解析 WCS 日志文件名到完整路径，防止路径穿越。"""
    # 只取文件名，丢弃任何路径部分
    safe_name = os.path.basename(filename)
    if not safe_name or safe_name != filename:
        raise HTTPException(status_code=400, detail="只接受文件名，不支持路径")
    full = os.path.abspath(os.path.join(WCSLOG_DIR, safe_name))
    if not full.startswith(os.path.abspath(WCSLOG_DIR)):
        raise HTTPException(status_code=400, detail="非法的文件路径")
    return full


@log_parser_router.get("/wcs_logs/files")
async def api_list_wcs_log_files():
    """返回 wcslog 目录下的文件名列表（仅文件名，不含路径）。"""
    if not os.path.isdir(WCSLOG_DIR):
        return []
    files = []
    for f in os.listdir(WCSLOG_DIR):
        p = os.path.join(WCSLOG_DIR, f)
        if os.path.isfile(p):
            stat = os.stat(p)
            if stat.st_size <= 15 * 1024 * 1024:
                files.append({
                    "filename": f,
                    "size": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                })
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return files


@log_parser_router.post("/wcs_logs/parse")
async def api_parse_wcs_log(
    filename: str = Body(..., description="WCS log 文件名（仅文件名，不含路径）"),
    shortcode: str | None = Body(None, description="设备外设编号过滤, e.g. 528000 or 5280xx"),
    trayid: str | None = Body(None, description="TrayID 过滤，在 Response 中搜索"),
    taskid: str | None = Body(None, description="任务ID过滤, e.g. 324FA059DD00_WCS"),
    device_type: str | None = Body(None, description="设备类型过滤, e.g. Detector, Rotate"),
):
    filepath = _resolve_wcs_path(filename)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")

    size = os.path.getsize(filepath)
    if size > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File exceeds 15MB limit ({size / 1024 / 1024:.0f} MB)")

    try:
        tid_hex = _trayid_to_hex(trayid) if trayid else None
        rows = list(parse(filepath, shortcode, tid_hex, taskid=taskid, device_type=device_type))
        return {"count": len(rows), "rows": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@log_parser_router.post("/wcs_logs/batch_parse")
async def api_batch_parse_wcs_log(
    filenames: list[str] = Body(..., description="WCS log 文件名列表（仅文件名），max 20"),
    shortcode: str | None = Body(None, description="设备外设编号过滤"),
    trayid: str | None = Body(None, description="TrayID 过滤，在 Response 中搜索"),
    taskid: str | None = Body(None, description="任务ID过滤"),
    device_type: str | None = Body(None, description="设备类型过滤, e.g. Detector, Rotate"),
):
    if len(filenames) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Too many files, max {MAX_FILES}")

    results = {}
    tid_hex = _trayid_to_hex(trayid) if trayid else None
    for fn in filenames:
        try:
            fp = _resolve_wcs_path(fn)
        except HTTPException:
            results[fn] = {"error": "非法文件名"}
            continue
        if not os.path.isfile(fp):
            results[fn] = {"error": "File not found"}
            continue
        size = os.path.getsize(fp)
        if size > 15 * 1024 * 1024:
            results[fn] = {"error": f"File exceeds 15MB limit ({size / 1024 / 1024:.0f} MB)"}
            continue
        try:
            rows = list(parse(fp, shortcode, tid_hex, taskid=taskid, device_type=device_type))
            results[fn] = {"count": len(rows), "rows": rows}
        except Exception as e:
            results[fn] = {"error": str(e)}

    return {"results": results}


# ── WCS Remote Logs (对应 CLI: tools wcslog list / download) ───────────

@log_parser_router.get("/wcs_logs/remote")
async def api_list_remote_wcs_logs(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=200, description="Items per page"),
    search: str = Query("", description="Filter by filename (case-insensitive partial match)"),
):
    """分页列出远程 WCS 服务器上的 default.log 文件。"""
    try:
        all_items = await list_wcs_logs()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"获取远程文件列表失败: {e}")

    if search:
        q = search.lower()
        all_items = [it for it in all_items if q in it["filename"].lower()]

    total = len(all_items)
    start = (page - 1) * page_size
    page_items = all_items[start : start + page_size]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "filename": it["filename"],
                "time": it["time"].strftime("%Y-%m-%d %H:%M:%S"),
                "download_url": it.get("download_url", ""),
            }
            for it in page_items
        ],
    }


@log_parser_router.get("/wcs_logs/logbak/remote")
async def api_list_remote_wcs_logbak(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=200, description="Items per page"),
    search: str = Query("", description="Filter by filename (case-insensitive partial match)"),
):
    """分页列出远程 WCS 服务器 log_bak 目录下的压缩包。"""
    try:
        all_items = await list_wcs_logbak()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"获取 log_bak 文件列表失败: {e}")

    if search:
        q = search.lower()
        all_items = [it for it in all_items if q in it["filename"].lower()]

    total = len(all_items)
    start = (page - 1) * page_size
    page_items = all_items[start : start + page_size]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "filename": it["filename"],
                "time": it["time"].strftime("%Y-%m-%d %H:%M:%S"),
                "download_url": it.get("download_url", ""),
            }
            for it in page_items
        ],
    }


@log_parser_router.post("/wcs_logs/download")
async def api_download_wcs_logs(
    filenames: list[str] = Body(..., description="要下载的文件名列表（自动识别 log / log_bak）"),
):
    """下载远程 WCS 日志文件（含 log_bak 压缩包），通过 SSE 流式返回下载进度。

    按扩展名自动路由：``.tar.bz2`` / ``.tar.gz`` / ``.zip`` → log_bak，其余 → default.log。
    """
    return StreamingResponse(
        _sse_wcs_download(filenames),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _is_logbak(filename: str) -> bool:
    return filename.lower().endswith((".tar.bz2", ".tar.gz", ".zip"))


async def _sse_wcs_download(filenames: list[str]):
    """SSE 生成器：下载 WCS 日志/log_bak 文件，逐文件报告进度。"""
    # 分别验证 default.log 和 log_bak 文件名
    log_filenames = [f for f in filenames if not _is_logbak(f)]
    bak_filenames = [f for f in filenames if _is_logbak(f)]

    remote_names: set[str] = set()
    if log_filenames:
        try:
            remote_logs = await list_wcs_logs()
            remote_names |= {f["filename"] for f in remote_logs}
        except Exception as e:
            yield _sse("error", f"无法获取远程文件列表: {e}")
            return
    if bak_filenames:
        try:
            remote_bak = await list_wcs_logbak()
            remote_names |= {f["filename"] for f in remote_bak}
        except Exception as e:
            yield _sse("error", f"无法获取 log_bak 文件列表: {e}")
            return

    not_found = [f for f in filenames if f not in remote_names]
    if not_found:
        yield _sse("error", f"以下文件在远程不存在: {not_found}")
        return

    progress_queue: asyncio.Queue = asyncio.Queue()

    def progress_cb(downloaded, total):
        pct = round(downloaded / total * 100, 1) if total > 0 else 0
        progress_queue.put_nowait({
            "type": "progress",
            "downloaded": downloaded,
            "total": total,
            "percentage": pct,
            "downloaded_str": _format_size(downloaded),
            "total_str": _format_size(total),
        })

    os.makedirs(WCSLOG_DIR, exist_ok=True)
    logbak_dir = os.path.join(WCSLOG_DIR, "logbak")
    os.makedirs(logbak_dir, exist_ok=True)
    success, failed = [], []

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        for fname in filenames:
            is_bak = _is_logbak(fname)
            save_dir = logbak_dir if is_bak else WCSLOG_DIR
            kind = "log_bak" if is_bak else "default.log"
            yield _sse("status", f"开始下载 {kind}: {fname}", {"filename": fname})

            # 后台下载 + 实时轮询队列（不阻塞等待）
            async def _run():
                try:
                    if is_bak:
                        d = await download_wcs_logbak(fname, save_dir=save_dir, client=client, progress_cb=progress_cb)
                    else:
                        d = await download_wcs_log(fname, save_dir=save_dir, client=client, progress_cb=progress_cb)
                    progress_queue.put_nowait({"type": "done", "dest": d})
                except Exception as e:
                    progress_queue.put_nowait({"type": "error", "message": str(e)})

            task = asyncio.create_task(_run())

            while True:
                msg = await progress_queue.get()
                if msg["type"] == "progress":
                    yield _sse("progress",
                               f"下载中… {msg['percentage']}%（{msg['downloaded_str']}/{msg['total_str']}）", {
                                   "percentage": msg["percentage"],
                                   "downloaded_str": msg["downloaded_str"],
                                   "total_str": msg["total_str"],
                                   "filename": fname,
                               })
                elif msg["type"] == "done":
                    await task
                    yield _sse("status", f"下载完成: {fname}", {"filename": fname, "path": msg["dest"]})
                    success.append(fname)
                    break
                elif msg["type"] == "error":
                    await task
                    logger.exception(f"下载WCS日志失败: {fname}")
                    yield _sse("error", f"下载失败 {fname}: {msg['message']}")
                    failed.append(fname)
                    break

    yield _sse("done", "", {"success": success, "failed": failed})


# ── log_bak 解压 (SSE 流式进度) ──────────────────────────────────────

@log_parser_router.post("/wcs_logs/logbak/extract")
async def api_extract_logbak(
    filename: str = Body(..., description="wcslog/logbak 下的 .tar.bz2 文件名"),
):
    """解压 log_bak 中全部 default.log* → wcslog/，SSE 流式返回进度。

    重命名格式: ``HH.MM.SS—HH.MM.SS_default.log``。
    """
    return StreamingResponse(
        _sse_extract_logbak(filename),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _sse_extract_logbak(filename: str):
    import shutil

    from util.parse_wcs_log import (
        _get_log_time_range,
        _ts_to_time_str,
        extract_tar_files,
    )

    logbak_dir = os.path.join(WCSLOG_DIR, "logbak")
    safe_name = os.path.basename(filename)
    tar_path = os.path.join(logbak_dir, safe_name)
    if not os.path.isfile(tar_path):
        yield _sse("error", f"压缩包不存在: {filename}")
        return

    tar_size = os.path.getsize(tar_path)
    yield _sse("status", f"开始解压 {safe_name}（{tar_size / 1024 / 1024:.0f} MB）…",
               {"filename": safe_name})
    # 立即发送 0% 进度，前端不会空白等待
    yield _sse("progress", f"解压中… 0%（0.0/{tar_size / 1024 / 1024:.0f} MB）", {
        "current": 0, "total": tar_size, "percentage": 0,
    })

    # 一趟流式解压 + 实时进度（不再先 list 再 extract，避免两次解压）
    progress_queue: asyncio.Queue = asyncio.Queue()

    def _progress_cb(read_bytes: int, total_bytes: int) -> None:
        pct = round(read_bytes / total_bytes * 100, 1) if total_bytes > 0 else 0
        progress_queue.put_nowait({
            "type": "progress",
            "current": read_bytes,
            "total": total_bytes,
            "percentage": pct,
            "message": f"解压中… {pct}%（{read_bytes / 1024 / 1024:.0f}/{total_bytes / 1024 / 1024:.0f} MB）",
        })

    async def _run_extract():
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None,
                extract_tar_files, tar_path, WCSLOG_DIR,
                None, None, _progress_cb,  # pattern=None, members=None → default: all default.log*
            )
            progress_queue.put_nowait({"type": "done", "result": result})
        except Exception as e:
            progress_queue.put_nowait({"type": "error", "message": str(e)})

    task = asyncio.create_task(_run_extract())

    while True:
        msg = await progress_queue.get()
        if msg["type"] == "progress":
            yield _sse("progress", msg["message"], {
                "current": msg["current"],
                "total": msg["total"],
                "percentage": msg["percentage"],
            })
        elif msg["type"] == "done":
            extracted = msg["result"]
            await task
            break
        elif msg["type"] == "error":
            yield _sse("error", msg["message"])
            await task
            return

    if not extracted:
        yield _sse("done", "压缩包内无 default.log* 文件", {"extracted": [], "count": 0})
        return

    # 重命名（逐文件报告进度）
    total = len(extracted)
    yield _sse("status", f"正在重命名 {total} 个文件…",
               {"filename": safe_name, "total": total})
    renamed: list[str] = []
    for i, src in enumerate(extracted):
        basename = os.path.basename(src)
        time_range = _get_log_time_range(src)
        if time_range:
            start, end = time_range
            new_name = f"{_ts_to_time_str(start)}—{_ts_to_time_str(end)}_default.log"
            new_dest = os.path.join(WCSLOG_DIR, new_name)
            if os.path.exists(new_dest):
                os.remove(new_dest)
            shutil.move(src, new_dest)
            renamed.append(new_name)
        else:
            renamed.append(basename)
        yield _sse("progress", f"{i + 1}/{total} {basename} → {renamed[-1]}", {
            "current": i + 1, "total": total,
            "percentage": round((i + 1) / total * 100, 1),
        })

    yield _sse("done", f"解压完成，共 {len(renamed)} 个文件", {
        "extracted": renamed, "count": len(renamed), "source": safe_name,
    })


# ── Clean (对应 CLI: tools clean <wcslog|agvlog>) ─────────────────────

@log_parser_router.get("/clean/usage")
async def api_clean_usage():
    """返回 agvlog 和 wcslog 目录的磁盘占用概览。"""
    result = {}
    for target, directory in CLEAN_DIRS.items():
        total_size = 0
        file_count = 0
        if os.path.isdir(directory):
            for f in os.listdir(directory):
                p = os.path.join(directory, f)
                if os.path.isfile(p):
                    try:
                        total_size += os.path.getsize(p)
                        file_count += 1
                    except OSError:
                        pass
        result[target] = {
            "directory": directory,
            "file_count": file_count,
            "total_size": total_size,
            "total_size_str": _format_size(total_size),
        }
    return result


@log_parser_router.get("/clean/{target}")
async def api_list_clean_files(target: str):
    """列出待清理目录的文件。target 只能是 agvlog 或 wcslog。"""
    if target not in CLEAN_DIRS:
        raise HTTPException(status_code=400, detail=f"Invalid target '{target}', must be one of: {list(CLEAN_DIRS.keys())}")

    directory = CLEAN_DIRS[target]
    if not os.path.isdir(directory):
        return {"target": target, "directory": directory, "count": 0, "total_size_str": "0 B", "files": []}

    entries = []
    for f in os.listdir(directory):
        p = os.path.join(directory, f)
        if os.path.isfile(p):
            stat = os.stat(p)
            entries.append({
                "index": len(entries),
                "filename": f,
                "size": stat.st_size,
                "size_str": _format_size(stat.st_size),
                "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            })

    entries.sort(key=lambda x: x["mtime"], reverse=True)
    total_size = sum(e["size"] for e in entries)
    return {
        "target": target,
        "directory": directory,
        "count": len(entries),
        "total_size": total_size,
        "total_size_str": _format_size(total_size),
        "files": entries,
    }


@log_parser_router.delete("/clean/{target}")
async def api_delete_clean_files(
    target: str,
    indices: list[int] = Body(..., description="File indices to delete (from GET endpoint)"),
):
    """删除指定 target 目录下的文件。target 只能是 agvlog 或 wcslog。"""
    if target not in CLEAN_DIRS:
        raise HTTPException(status_code=400, detail=f"Invalid target '{target}', must be one of: {list(CLEAN_DIRS.keys())}")

    directory = CLEAN_DIRS[target]
    if not os.path.isdir(directory):
        raise HTTPException(status_code=404, detail=f"Directory not found: {directory}")

    entries = sorted(
        (
            (f, os.path.getsize(p), datetime.fromtimestamp(os.path.getmtime(p)))
            for f in os.listdir(directory)
            if os.path.isfile(p := os.path.join(directory, f))
        ),
        key=lambda x: x[2],
        reverse=True,
    )

    deleted = []
    errors = []
    for idx in indices:
        if idx < 0 or idx >= len(entries):
            errors.append({"index": idx, "error": "Index out of range"})
            continue
        name = entries[idx][0]
        try:
            os.remove(os.path.join(directory, name))
            deleted.append(name)
        except OSError as e:
            errors.append({"index": idx, "filename": name, "error": str(e)})

    return {"deleted": deleted, "count": len(deleted), "errors": errors}
