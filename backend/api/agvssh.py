import json
import pathlib
import uuid
from datetime import datetime
from urllib.parse import quote

#导入弃用警告装饰器DeprecationWarning
from fastapi import APIRouter, Body
from fastapi.responses import StreamingResponse

from util.config import cfg, r
from util.ssh import SSHManager

agv_web_router = APIRouter(
    prefix="/agv",
    tags=["agv"],
)

download_path = (
    pathlib.Path(__file__).parent.parent.parent / "util" / "data" / "download"
)
# print(f"download_path: {download_path}")
if not download_path.exists():
    download_path.mkdir(parents=True)


@agv_web_router.post("/connect")
async def connect_agv(
    host: str = Body(...),
    port: int = Body(22, description="SSH端口，默认22"),
    username: str = Body(cfg.get("agv.username"), description="ssh用户名"),
    password: str = Body(cfg.get("agv.password"), description="ssh密码"),
):
    if not username:
        username = cfg.get("agv.username")
    if not password:
        password = cfg.get("agv.password")
    if not port:
        port = 22
    # print(f"connect_agv: {host}, {port}, {username}, {password}")
        
    ssh_manager = SSHManager(host, username, password, port)
    success, error = ssh_manager.connect()
    if success:
        return {"message": "连接成功", "id": ssh_manager.id}
    else:
        return {"message": "连接失败", "error": error}


@agv_web_router.get("/disconnect")
async def disconnect_agv(id: str):
    """断开AGV连接"""
    ssh_manager = SSHManager.get_ssh_manager(id)
    if not ssh_manager:
        return {"success": False, "error": "连接失败, id不存在"}
    ssh_manager.disconnect()
    return {"message": "断开成功", "success": True}


@agv_web_router.get("/list_ssh")
async def list_ssh():
    """列出所有SSH连接"""
    return {"data": SSHManager.get_all_ssh_managers(), "success": True}


@agv_web_router.post("/list_dir")
async def list_dir(id: str = Body(...), path: str = Body(".")):
    """列出目录内容"""
    ssh_manager = SSHManager.get_ssh_manager(id)
    if not ssh_manager:
        return {"success": False, "error": "连接失败, id不存在"}
    try:
        ls_output = ssh_manager.list_directory(path)
    except Exception as e:
        return {"success": False, "error": str(e)}
    return {"data": ls_output, "success": True}

@DeprecationWarning
@agv_web_router.get("/download")
async def download_file(id: str, filepath: str):
    """下载文件到本地（保留原有功能）"""
    ssh_manager = SSHManager.get_ssh_manager(id)
    if not ssh_manager:
        return {"success": False, "error": "连接失败, id不存在"}
    try:
        ssh_manager.download_file(filepath, download_path)
    except Exception as e:
        return {"success": False, "error": str(e)}
    return {"message": "下载成功", "success": True}


@agv_web_router.post("/stream_download")
async def stream_download_file(id: str = Body(...), filepath: str = Body(...)):
    """流式下载文件到浏览器"""
    ssh_manager = SSHManager.get_ssh_manager(id)
    if not ssh_manager:
        return {"success": False, "error": "连接失败, id不存在"}

    # 获取文件名
    filename = pathlib.PurePath(filepath).name
    # 使用英文标识符避免HTTP头部编码问题
    disc = f"{ssh_manager.username}@{ssh_manager.host}:{filepath}"
    # 生成下载任务ID

    download_id = f"download_{uuid.uuid4().hex}"

    def make_progress(progress, total):
        # 确保进度信息中不包含可能导致问题的特殊字符
        safe_disc = disc.encode('utf-8', errors='replace').decode('utf-8')
        return json.dumps(
            {
                "progress": progress,
                "total": total,
                "filename": safe_disc,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    # 初始化下载进度
    r.set(f"download_progress:{download_id}", make_progress(0, 0), ex=3600 * 24)

    # 创建流式响应
    def iter_stream():
        def progress_callback(downloaded, total):
            r.set(f"download_progress:{download_id}", make_progress(downloaded, total), ex=3600 * 24)

        for chunk in ssh_manager.stream_file(filepath, callback=progress_callback):
            yield chunk

    # 安全处理Content-Disposition头部，避免非ASCII字符导致的编码错误
    # 先尝试使用ASCII兼容的文件名，如果失败则使用通用方法
    try:
        # 尝试直接使用文件名（对于纯ASCII字符）
        filename.encode('ascii')
        content_disposition = f'attachment; filename="{filename}"'
    except UnicodeEncodeError:
        # 对于非ASCII字符，使用RFC 5987标准
        encoded_filename = quote(filename, safe='')
        content_disposition = f'attachment; filename*=UTF-8\'\'{encoded_filename}'
    
    return StreamingResponse(
        iter_stream(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": content_disposition,
            "X-Download-ID": download_id,  # 添加下载ID到响应头
        },
    )

@agv_web_router.get("/download_progress")
async def get_download_progress(download_id: str):
    """获取下载进度"""
    progress = r.get(f"download_progress:{download_id}")
    if progress:
        progress = progress.decode("utf-8")
    else:
        progress = "0"
    return {"progress": progress}


