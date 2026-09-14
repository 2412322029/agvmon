"""AGV 拓扑地图 XML 接口。

RCMS 导出的 MapCfg 拓扑地图（<PointInfo> 节点 + <NeighbInfo> 邻接段）一般下载在
``util/data/download/`` 下，本模块只负责「列出 + 取原文」：

- ``GET /api/map_topology/list``        列出可用的拓扑地图 XML
- ``GET /api/map_topology/raw/{name}``  读取指定 XML 原文（application/xml）

XML 的解析、渲染选择、地码（地面二维码）生成都在前端完成，
见 ``web/src/composables/agvTopology.js``。
"""

from __future__ import annotations

import pathlib
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

map_topology_router = APIRouter(prefix="/map_topology", tags=["map_topology"])

_BASE = pathlib.Path(__file__).parent.parent.parent
# 地图 XML 的候选目录（按优先级）
_MAP_DIRS = (
    _BASE / "util" / "data" / "download",
    _BASE / "util" / "data" / "map",
    _BASE / "util" / "data",
)
# 单文件上限，避免误把超大文件当拓扑地图
_MAX_SIZE = 64 * 1024 * 1024


def _looks_like_mapc(path: pathlib.Path) -> bool:
    """粗略判断是否为 MapCfg 拓扑地图（只读文件头）"""
    try:
        with path.open("rb") as fp:
            head = fp.read(4096).decode("utf-8", errors="ignore")
    except OSError:
        return False
    return "<MapCfg" in head or "<PointInfo>" in head


def _iter_map_files() -> list[pathlib.Path]:
    """扫描候选目录，返回去重后的拓扑地图 XML 列表"""
    seen: set[str] = set()
    found: list[pathlib.Path] = []
    for directory in _MAP_DIRS:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.xml")):
            if path.name in seen or path.stat().st_size > _MAX_SIZE:
                continue
            if not _looks_like_mapc(path):
                continue
            seen.add(path.name)
            found.append(path)
    return found


def _resolve(name: str) -> pathlib.Path:
    """按文件名查找地图文件（只允许 plain filename，防目录穿越）"""
    safe_name = pathlib.PurePath(name or "").name
    if not safe_name or not safe_name.lower().endswith(".xml"):
        raise HTTPException(status_code=400, detail="仅支持 .xml 拓扑地图文件")
    for path in _iter_map_files():
        if path.name == safe_name:
            return path
    raise HTTPException(status_code=404, detail=f"未找到地图文件: {safe_name}")


@map_topology_router.get("/list")
def list_map_files():
    """列出可用的拓扑地图 XML 文件（按修改时间倒序）"""
    files = []
    for path in _iter_map_files():
        stat = path.stat()
        try:
            rel = path.relative_to(_BASE).as_posix()
        except ValueError:
            rel = path.as_posix()
        files.append(
            {
                "name": path.name,
                "path": rel,
                "size": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            }
        )
    files.sort(key=lambda item: item["mtime"], reverse=True)
    return {"files": files, "count": len(files)}


@map_topology_router.get("/raw/{name}")
def get_map_raw(name: str):
    """返回拓扑地图 XML 原文，由前端解析"""
    path = _resolve(name)
    return FileResponse(
        path,
        media_type="application/xml",
        headers={"Cache-Control": "no-cache", "X-Map-File": path.name},
    )
