# -*- coding: utf-8 -*-
"""QwenPaw Creator（视频压缩版）— PawApp backend.

官方 QwenPaw Creator 的企业裁剪版：仅保留视频压缩能力，压缩引擎移植自
灵泽万川视频工坊（MarukoToolbox-Rewrite）。剧本/导演/视觉/动效等创作
能力已全部舍弃。

REST 路由挂在 /api/qwenpaw-creator（PawApp 路由前缀契约）：
  GET  /capabilities        编码器/预设/分辨率/音频模式 + ffmpeg 环境探测
  POST /files               上传视频（multipart）
  POST /files/local         登记服务器本地路径的视频
  GET  /files               输入文件列表（含探测信息）
  DELETE /files/{file_id}   删除已登记的输入文件
  POST /compress            创建压缩任务
  GET  /jobs                任务列表
  GET  /jobs/{job_id}       任务状态与进度
  POST /jobs/{job_id}/cancel 取消任务
  GET  /jobs/{job_id}/download 下载压缩产物
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from qwenpaw.pawapp import PawApp

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:  # 官方 Creator 同款布局：绝对导入
    sys.path.insert(0, str(BACKEND_DIR))

from compression import (
    AUDIO_MODES,
    ENCODERS,
    PRESETS,
    RESOLUTIONS,
    SHARPEN_LEVELS,
    VIDEO_EXTENSIONS,
    VIDEO_MUXERS,
    CompressionSettings,
    build_compress_command,
    detect_environment,
    output_filename,
    parse_progress_line,
    probe_media_info,
)

logger = logging.getLogger("qwenpaw").getChild("plugin.qwenpaw_creator")

PLUGIN_DIR = BACKEND_DIR.parent
DATA_DIR = PLUGIN_DIR / "data"
INPUT_DIR = DATA_DIR / "inputs"
OUTPUT_DIR = DATA_DIR / "outputs"
REGISTRY_FILE = DATA_DIR / "files.json"
MAX_UPLOAD_BYTES = 4 * 1024 * 1024 * 1024  # 4 GB

INPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter()

# file_id -> 登记信息；job_id -> 任务状态（内存 + 启动时落盘的注册表）
_FILES: Dict[str, Dict[str, Any]] = {}
_JOBS: Dict[str, Dict[str, Any]] = {}
_RUNNING: Dict[str, "asyncio.Task"] = {}


def _load_registry() -> None:
    try:
        raw = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        for file_id, entry in raw.items():
            if Path(entry.get("path", "")).is_file():
                _FILES[file_id] = entry
    except (OSError, json.JSONDecodeError):
        pass


def _save_registry() -> None:
    REGISTRY_FILE.write_text(
        json.dumps(_FILES, ensure_ascii=False, indent=2), encoding="utf-8")


_load_registry()


@router.get("/capabilities")
async def capabilities() -> Dict[str, Any]:
    env = detect_environment()
    return {
        "name": "QwenPaw Creator · 视频压缩",
        "presets": list(PRESETS.keys()),
        "resolutions": list(RESOLUTIONS.keys()),
        "sharpen_levels": list(SHARPEN_LEVELS.keys()),
        "audio_modes": list(AUDIO_MODES.keys()),
        "muxers": list(VIDEO_MUXERS.keys()),
        "environment": env,
    }


async def _register_input(path: Path, display_name: str, source: str) -> Dict[str, Any]:
    file_id = f"f-{uuid.uuid4().hex[:10]}"
    info = probe_media_info(path)
    entry = {
        "file_id": file_id,
        "name": display_name,
        "path": str(path),
        "source": source,
        "size": path.stat().st_size,
        "registered_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        **info,
    }
    _FILES[file_id] = entry
    _save_registry()
    return entry


@router.post("/files")
async def upload_file(file: UploadFile) -> Dict[str, Any]:
    suffix = Path(file.filename or "video.mp4").suffix.lower()
    if suffix not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=422, detail=f"不支持的视频格式：{suffix}")
    target = INPUT_DIR / f"{uuid.uuid4().hex[:10]}{suffix}"
    written = 0
    with target.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="视频文件超过 4 GB 上限")
            out.write(chunk)
    return await _register_input(target, file.filename or target.name, "upload")


class LocalFileRequest(BaseModel):
    path: str = Field(min_length=2, max_length=1024)


@router.post("/files/local")
async def register_local(body: LocalFileRequest) -> Dict[str, Any]:
    path = Path(body.path).expanduser().resolve()
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在：{path}")
    if path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=422, detail=f"不支持的视频格式：{path.suffix}")
    return await _register_input(path, path.name, "local")


@router.get("/files")
async def list_files() -> Dict[str, Any]:
    return {"files": sorted(_FILES.values(), key=lambda e: e["registered_at"], reverse=True)}


@router.delete("/files/{file_id}")
async def delete_file(file_id: str) -> Dict[str, Any]:
    entry = _FILES.pop(file_id, None)
    if entry is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    if entry.get("source") == "upload":
        Path(entry["path"]).unlink(missing_ok=True)
    _save_registry()
    return {"deleted": file_id}


class CompressRequest(BaseModel):
    file_id: str
    encoder_key: str
    preset_name: str = "均衡"
    resolution_name: str = "保持原分辨率"
    sharpen_name: str = "关闭"
    quality_mode: str = "crf"
    cq_value: int = Field(default=28, ge=0, le=51)
    bitrate: str = ""
    audio_mode: str = "复制音频流"
    audio_bitrate: str = "192k"
    muxer_name: str = "MP4 (.mp4)"
    output_speed: float = Field(default=1.0, ge=0.25, le=4.0)
    overwrite: bool = False
    extra_ffmpeg_args: str = ""


@router.post("/compress")
async def compress(body: CompressRequest) -> Dict[str, Any]:
    entry = _FILES.get(body.file_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="输入文件不存在")
    if body.encoder_key not in _VALID_ENCODER_KEYS:
        raise HTTPException(status_code=422, detail=f"未知编码器：{body.encoder_key}")

    settings = CompressionSettings(
        encoder_key=body.encoder_key,
        preset_name=body.preset_name,
        resolution_name=body.resolution_name,
        sharpen_name=body.sharpen_name,
        quality_mode=body.quality_mode,
        cq_value=body.cq_value,
        bitrate=body.bitrate,
        audio_mode=body.audio_mode,
        audio_bitrate=body.audio_bitrate,
        muxer_name=body.muxer_name,
        output_speed=body.output_speed,
        overwrite=body.overwrite,
        extra_ffmpeg_args=body.extra_ffmpeg_args,
    )
    source = Path(entry["path"])
    target = OUTPUT_DIR / output_filename(source, settings)
    if target.exists() and not settings.overwrite:
        target = OUTPUT_DIR / f"{target.stem}_{uuid.uuid4().hex[:4]}{target.suffix}"

    job_id = f"j-{uuid.uuid4().hex[:10]}"
    job = {
        "job_id": job_id,
        "file_id": body.file_id,
        "file_name": entry["name"],
        "status": "running",
        "progress": 0.0,
        "source_size": source.stat().st_size,
        "output_size": 0,
        "output_path": str(target),
        "output_name": target.name,
        "duration": entry.get("duration") or 0,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "error": "",
        "command": [],
    }
    _JOBS[job_id] = job
    _RUNNING[job_id] = asyncio.create_task(_run_job(job_id, source, target, settings))
    return {"job_id": job_id}


_VALID_ENCODER_KEYS = set(ENCODERS.keys())


async def _run_job(job_id: str, source: Path, target: Path,
                   settings: CompressionSettings) -> None:
    job = _JOBS[job_id]
    cmd = build_compress_command(source, target, settings)
    job["command"] = cmd
    logger.info("[creator] 压缩任务 %s 启动：%s", job_id, target.name)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        job["pid"] = proc.pid
        duration_us = max(job.get("duration") or 0, 0) * 1_000_000
        assert proc.stdout is not None
        async for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").strip()
            done_us = parse_progress_line(line)
            if done_us is not None and duration_us:
                job["progress"] = min(1.0, done_us / duration_us)
        returncode = await proc.wait()
        stderr = (await proc.stderr.read()).decode("utf-8", errors="replace") if proc.stderr else ""
        if returncode == 0 and target.is_file():
            job["status"] = "done"
            job["progress"] = 1.0
            job["output_size"] = target.stat().st_size
            logger.info("[creator] 压缩任务 %s 完成：%s（%.1f%% 体积）",
                        job_id, target.name,
                        100 * job["output_size"] / max(1, job["source_size"]))
        else:
            job["status"] = "failed"
            job["error"] = stderr.strip()[-800:] or f"ffmpeg 退出码 {returncode}"
            logger.warning("[creator] 压缩任务 %s 失败：%s", job_id, job["error"][:200])
    except asyncio.CancelledError:
        job["status"] = "cancelled"
        raise
    except Exception as exc:  # noqa: BLE001
        job["status"] = "failed"
        job["error"] = str(exc)
        logger.exception("[creator] 压缩任务 %s 异常", job_id)
    finally:
        _RUNNING.pop(job_id, None)


@router.get("/jobs")
async def list_jobs() -> Dict[str, Any]:
    return {"jobs": sorted(_JOBS.values(),
                           key=lambda j: j["created_at"], reverse=True)}


@router.get("/jobs/{job_id}")
async def job_status(job_id: str) -> Dict[str, Any]:
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> Dict[str, Any]:
    task = _RUNNING.get(job_id)
    if task is None:
        raise HTTPException(status_code=409, detail="任务不在运行中")
    task.cancel()
    return {"cancelling": job_id}


@router.get("/jobs/{job_id}/download")
async def download_output(job_id: str) -> FileResponse:
    job = _JOBS.get(job_id)
    if job is None or job.get("status") != "done":
        raise HTTPException(status_code=404, detail="产物不存在或任务未完成")
    path = Path(job["output_path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="产物文件已丢失")
    return FileResponse(path, filename=path.name)


app = PawApp(name="QwenPaw Creator · 视频压缩", app_id="qwenpaw-creator")
app.include_router(router)


@app.on_terminate
async def shutdown_creator() -> None:
    for job_id, task in list(_RUNNING.items()):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    logger.info("[creator] 已取消全部运行中的压缩任务")


# The 'plugin' variable is what PluginLoader looks for.
plugin = app
