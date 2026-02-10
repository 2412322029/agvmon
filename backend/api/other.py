import hashlib
import json
import pathlib
from datetime import datetime

from fastapi import APIRouter, Body, File, Query, UploadFile
from fastapi.responses import FileResponse

from util.config import cfg, r

util_web_router = APIRouter(
    prefix="/util",
    tags=["util"],
)

upload_path = (
    pathlib.Path(__file__).parent.parent.parent / "util" / "data" / "upload"
)
# print(f"upload_path: {upload_path}")
if not upload_path.exists():
    upload_path.mkdir(parents=True)

# Redis key prefix for uploaded files
UPLOAD_FILE_PREFIX = "upload:file:"

# 文件上传接口
@util_web_router.post("/upload")
async def upload_file(file: UploadFile = File(...), expire_days: int = Query(7, description="文件过期天数，默认为7天")):
    """上传文件到服务器"""
    try:
        # 计算文件内容的MD5哈希值作为存储文件名
        content = await file.read()
        md5_hash = hashlib.md5(content).hexdigest()
        file_extension = pathlib.Path(file.filename).suffix
        stored_filename = f"{md5_hash}{file_extension}"
        
        # 保存文件到指定目录，使用MD5哈希作为文件名
        file_path = upload_path / stored_filename
        with open(file_path, "wb") as f:
            f.write(content)
        
        # 计算过期时间（秒）
        expire_seconds = expire_days * 24 * 60 * 60  # 转换天数为秒数
        
        # 在Redis中存储文件元数据
        file_metadata = {
            "original_filename": file.filename,  # 原始文件名
            "stored_filename": stored_filename,  # 存储文件名（MD5哈希）
            "size": len(content),
            "content_type": file.content_type,
            "upload_time": datetime.now().isoformat(),
            "expire_days": expire_days
        }
        # 为每个文件使用单独的带有TTL的键
        r.setex(f"{UPLOAD_FILE_PREFIX}{stored_filename}", expire_seconds, json.dumps(file_metadata))  # 可配置的过期时间
        

        
        return {"message": "文件上传成功", "filename": file.filename, "stored_filename": stored_filename}
    except Exception as e:
        return {"error": str(e)}

# 列出上传目录下的所有 files
@util_web_router.get("/list")
async def list_upload_files():
    """列出上传目录下的所有文件"""
    try:
        files = []
        
        # 扫描上传目录中的所有文件
        if upload_path.exists():
            for file_path in upload_path.iterdir():
                if file_path.is_file():
                    stored_filename = file_path.name
                    
                    # 从Redis获取文件元数据
                    metadata_bytes = r.get(f"{UPLOAD_FILE_PREFIX}{stored_filename}")
                    if metadata_bytes:
                        metadata = json.loads(metadata_bytes.decode('utf-8'))
                        
                        files.append({
                            "original_filename": metadata["original_filename"],
                            "stored_filename": metadata["stored_filename"],
                            "size": metadata.get("size"),
                            "content_type": metadata.get("content_type"),
                            "upload_time": metadata.get("upload_time"),
                            "expire_days": metadata.get("expire_days")
                        })
                    else:
                        # 如果元数据不存在，删除文件
                        file_path.unlink()
                
        return {"files": files}
    except Exception as e:
        return {"error": str(e)}

# 删除上传目录下的文件
@util_web_router.delete("/delete")
async def delete_upload_file(stored_filename: str = Body(..., embed=True)):
    """删除上传目录下的文件"""
    try:
        file_path = upload_path / stored_filename
        if file_path.exists():
            file_path.unlink()
            # 同时从Redis中删除
            r.delete(f"{UPLOAD_FILE_PREFIX}{stored_filename}")
            return {"message": "文件删除成功", "stored_filename": stored_filename}
        else:
            return {"error": "文件不存在"}
    except Exception as e:
        return {"error": str(e)}

# 修改文件过期时间
@util_web_router.put("/expire/{stored_filename}")
async def modify_expire_time(stored_filename: str, expire_days: int = Query(..., ge=1, le=365, description="新的过期天数")):
    """修改文件的过期时间"""
    try:
        # 检查文件是否在Redis中有记录（未过期）
        key = f"{UPLOAD_FILE_PREFIX}{stored_filename}"
        if not r.exists(key):
            return {"error": "文件不存在或已过期"}
        
        # 获取当前文件元数据
        metadata_bytes = r.get(key)
        if not metadata_bytes:
            return {"error": "无法获取文件元数据"}
        
        metadata = json.loads(metadata_bytes.decode('utf-8'))
        
        # 更新过期时间和元数据
        expire_seconds = expire_days * 24 * 60 * 60
        metadata['expire_days'] = expire_days
        metadata['updated_expire_time'] = datetime.now().isoformat()
        
        # 重新设置带新TTL的键
        r.setex(key, expire_seconds, json.dumps(metadata))
        
        return {
            "message": "文件过期时间更新成功",
            "stored_filename": stored_filename,
            "new_expire_days": expire_days
        }
    except Exception as e:
        return {"error": str(e)}

# 下载上传的文件
@util_web_router.get("/download/{stored_filename}")
async def download_file(stored_filename: str):
    """下载上传的文件"""
    try:
        # 检查文件是否在Redis中有记录（未过期）
        if not r.exists(f"{UPLOAD_FILE_PREFIX}{stored_filename}"):
            return {"error": "文件不存在或已过期"}
        
        file_path = upload_path / stored_filename
        if not file_path.exists():
            # 从Redis中清除该记录，因为文件不存在
            r.delete(f"{UPLOAD_FILE_PREFIX}{stored_filename}")
            return {"error": "文件不存在"}
        
        # 获取原始文件名用于下载时的文件名
        metadata_bytes = r.get(f"{UPLOAD_FILE_PREFIX}{stored_filename}")
        if metadata_bytes:
            metadata = json.loads(metadata_bytes.decode('utf-8'))
            original_filename = metadata.get("original_filename", stored_filename)
            content_type = metadata.get("content_type", "application/octet-stream")
        else:
            original_filename = stored_filename
            content_type = "application/octet-stream"
            
        # Determine if it's an image file for preview
        image_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/bmp', 'image/webp']
        if content_type in image_types:
            # Return image with appropriate content type for preview
            return FileResponse(
                path=file_path,
                media_type=content_type,
                headers={"Content-Disposition": f"inline; filename={original_filename}"}
            )
        else:
            # Return other files as attachment for download
            return FileResponse(
                path=file_path,
                filename=original_filename,
                media_type=content_type or 'application/octet-stream'
            )
    except Exception as e:
        return {"error": str(e)}


def cleanup_expired_files():
    """
    清理由Redis键过期后仍存在于文件系统的过期文件
    """
    try:
        # 扫描上传目录中的所有文件
        if upload_path.exists():
            for file_path in upload_path.iterdir():
                if file_path.is_file():
                    stored_filename = file_path.name
                    # 检查Redis键是否仍然存在（未过期）
                    if not r.exists(f"{UPLOAD_FILE_PREFIX}{stored_filename}"):
                        # 键已过期或不存在，删除文件
                        file_path.unlink()
                        print(f"已删除过期文件: {stored_filename}")
        # redis中存在，实际不存在的删除
        for key in r.keys(f"{UPLOAD_FILE_PREFIX}*"):
            stored_filename = key.decode('utf-8').replace(f"{UPLOAD_FILE_PREFIX}", "")
            if not (upload_path / stored_filename).exists():
                r.delete(key)
                print(f"已删除过期文件记录: {stored_filename}")
                    
    except Exception as e:
        print(f"清理过期文件时出错: {str(e)}")
