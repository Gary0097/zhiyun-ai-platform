# -*- coding: utf-8 -*-
"""智能混剪 — PawApp backend.

多素材智能混剪：片段按时间线拼接、转场（淡入淡出/交叉溶解）、背景音乐混音、
字幕与水印，ffmpeg filter_complex 一次合成，实时进度与产物下载。

REST（挂 /api/qwenpaw-creator-mixcut）：
  GET  /capabilities        可用转场/滤镜/环境探测
  POST /clips               上传片段（multipart）
  GET  /clips               片段列表（含探测信息）
  DELETE /clips/{id}        删除片段
  POST /projects            创建混剪工程（时间线：片段顺序+入出点+转场+BGM+字幕+水印）
  GET  /projects            工程列表
  POST /projects/{id}/render 渲染（异步任务）
  GET  /jobs / /jobs/{id} /cancel / download  同视频压缩版
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

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from qwenpaw.pawapp import PawApp

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from mixcut_auth_guard import verify_token_user  # 唯一模块名，避免共享 sys.path 冲突  # noqa: E402
from mixcut_av_tools import VIDEO_EXTENSIONS, detect_environment, parse_progress_line, probe_media_info  # noqa: E402

logger = logging.getLogger("qwenpaw").getChild("plugin.qwenpaw_creator_mixcut")

PLUGIN_DIR = BACKEND_DIR.parent
DATA_DIR = PLUGIN_DIR / "data"
CLIPS_DIR = DATA_DIR / "clips"
BGM_DIR = DATA_DIR / "bgm"
OUTPUT_DIR = DATA_DIR / "outputs"
CLIP_REGISTRY = DATA_DIR / "clips.json"
PROJECTS_FILE = DATA_DIR / "projects.json"
JOBS_FILE = DATA_DIR / "jobs.json"
MAX_UPLOAD_BYTES = 4 * 1024 * 1024 * 1024

for d in (CLIPS_DIR, BGM_DIR, OUTPUT_DIR):
    d.mkdir(parents=True, exist_ok=True)

router = APIRouter()

# ── 鉴权（与平台同源） ────────────────────────────────────────────────
def require_user(authorization: str = Header(default="")) -> dict:
    user = verify_token_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="未登录或凭证已过期")
    return user


# ── 转场定义（ffmpeg xfade） ──────────────────────────────────────────
TRANSITIONS = {
    "直接切换": None,
    "交叉溶解": "fade",
    "淡入淡出（黑白）": "fadeblack",
    "淡入淡出（白场）": "fadewhite",
    "滑动": "slideleft",
    "上滑": "slideup",
    "擦除": "wipeleft",
    "圆形展开": "circleopen",
}
RESOLUTION_PRESETS = {
    "1080p 横屏": "1920:1080",
    "720p 横屏": "1280:720",
    "竖屏 1080x1920": "1080:1920",
    "竖屏 720x1280": "720:1280",
}


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _save(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


_CLIPS: Dict[str, Dict[str, Any]] = _load(CLIP_REGISTRY, {})
_PROJECTS: Dict[str, Dict[str, Any]] = _load(PROJECTS_FILE, {})
_JOBS: Dict[str, Dict[str, Any]] = {}
_RUNNING: Dict[str, "asyncio.Task"] = {}
try:
    for jid, job in _load(JOBS_FILE, {}).items():
        if job.get("status") == "running":
            job["status"] = "interrupted"
            job["error"] = "服务重启导致渲染中断，请重新发起"
        _JOBS[jid] = job
except TypeError:
    pass


def _public(job: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in job.items() if not k.startswith("_")}


def _ffprobe_dur(path: Path) -> float:
    info = probe_media_info(path)
    return float(info.get("duration") or 0)


# ── 能力 ──────────────────────────────────────────────────────────────
@router.get("/capabilities")
async def capabilities() -> Dict[str, Any]:
    return {
        "name": "QwenPaw Creator · 智能混剪",
        "transitions": list(TRANSITIONS.keys()),
        "resolutions": list(RESOLUTION_PRESETS.keys()),
        "environment": detect_environment(),
    }


# ── 片段管理 ──────────────────────────────────────────────────────────
async def _register_clip(path: Path, name: str, source: str) -> Dict[str, Any]:
    clip_id = f"c-{uuid.uuid4().hex[:10]}"
    info = await asyncio.to_thread(probe_media_info, path)
    entry = {
        "clip_id": clip_id, "name": name, "path": str(path), "source": source,
        "size": path.stat().st_size,
        "registered_at": time.strftime("%Y-%m-%d %H:%M:%S"), **info,
    }
    _CLIPS[clip_id] = entry
    _save(CLIP_REGISTRY, _CLIPS)
    return entry


@router.post("/clips")
async def upload_clip(file: UploadFile, user: dict = Depends(require_user)) -> Dict[str, Any]:
    suffix = Path(file.filename or "clip.mp4").suffix.lower()
    if suffix not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=422, detail=f"不支持的视频格式：{suffix}")
    target = CLIPS_DIR / f"{uuid.uuid4().hex[:10]}{suffix}"
    written = 0
    with target.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="片段超过 4 GB 上限")
            out.write(chunk)
    return await _register_clip(target, file.filename or target.name, "upload")


@router.get("/clips")
async def list_clips(user: dict = Depends(require_user)) -> Dict[str, Any]:
    return {"clips": sorted(_CLIPS.values(), key=lambda c: c["registered_at"], reverse=True)}


@router.delete("/clips/{clip_id}")
async def delete_clip(clip_id: str, user: dict = Depends(require_user)) -> Dict[str, Any]:
    entry = _CLIPS.pop(clip_id, None)
    if entry is None:
        raise HTTPException(status_code=404, detail="片段不存在")
    Path(entry["path"]).unlink(missing_ok=True)
    _save(CLIP_REGISTRY, _CLIPS)
    return {"deleted": clip_id}


# ── BGM ──────────────────────────────────────────────────────────────
@router.post("/bgm")
async def upload_bgm(file: UploadFile, user: dict = Depends(require_user)) -> Dict[str, Any]:
    suffix = Path(file.filename or "bgm.mp3").suffix.lower()
    if suffix not in {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg"}:
        raise HTTPException(status_code=422, detail=f"不支持的音频格式：{suffix}")
    target = BGM_DIR / f"bgm{suffix}"
    with target.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            out.write(chunk)
    return {"bgm": str(target), "name": file.filename}


# ── 工程 ──────────────────────────────────────────────────────────────
class TimelineItem(BaseModel):
    clip_id: str
    trim_start: float = Field(default=0, ge=0)
    trim_end: float = Field(default=0, ge=0, description="0=到片尾")
    transition: str = "交叉溶解"
    transition_duration: float = Field(default=0.5, ge=0, le=3)


class ProjectRequest(BaseModel):
    name: str = Field(default="混剪工程", max_length=80)
    resolution: str = "1080p 横屏"
    timeline: list[TimelineItem] = Field(min_length=1)
    bgm_volume: float = Field(default=0.3, ge=0, le=1)
    bgm_fadeout: bool = True
    subtitle_text: str = Field(default="", max_length=400)
    watermark: str = Field(default="", max_length=40)
    output_speed: float = Field(default=1.0, ge=0.25, le=4)


@router.post("/projects")
async def create_project(body: ProjectRequest, user: dict = Depends(require_user)) -> Dict[str, Any]:
    for i, item in enumerate(body.timeline):
        if item.clip_id not in _CLIPS:
            raise HTTPException(status_code=422, detail=f"时间线第 {i+1} 项的片段不存在")
        if item.transition not in TRANSITIONS:
            raise HTTPException(status_code=422, detail=f"未知转场：{item.transition}")
    project_id = f"p-{uuid.uuid4().hex[:10]}"
    project = {"project_id": project_id, **body.model_dump(),
               "created_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    _PROJECTS[project_id] = project
    _save(PROJECTS_FILE, _PROJECTS)
    return project


@router.get("/projects")
async def list_projects(user: dict = Depends(require_user)) -> Dict[str, Any]:
    return {"projects": sorted(_PROJECTS.values(), key=lambda p: p["created_at"], reverse=True)}


# ── 渲染 ──────────────────────────────────────────────────────────────
def build_mixcut_command(ffmpeg: str, timeline: list[dict], resolution: str,
                         bgm: str | None, bgm_volume: float, bgm_fadeout: bool,
                         subtitle: str, watermark: str, speed: float,
                         target: Path) -> tuple[list[str], float]:
    """构建 filter_complex 混剪命令，返回 (cmd, 预估总时长秒)。"""
    scale = RESOLUTION_PRESETS.get(resolution, "1920:1080")
    inputs: list[str] = []
    probe = av_probe = None
    import subprocess as _sp
    ffprobe = None
    from mixcut_av_tools import find_tool
    ffprobe = find_tool("ffprobe")

    stream_idx = 0
    video_labels: list[str] = []
    audio_labels: list[str] = []
    total = 0.0
    parts: list[str] = []
    for i, item in enumerate(timeline):
        path = item["clip_path"]
        dur = float(item.get("duration") or 0)
        trim_start = float(item.get("trim_start") or 0)
        trim_end = float(item.get("trim_end") or 0) or dur
        seg = max(0.05, trim_end - trim_start)
        # trim + scale + 统一帧率/fps 与像素格式
        inputs += ["-ss", f"{trim_start:.3f}", "-t", f"{seg:.3f}", "-i", str(path)]
        parts.append(
            f"[{stream_idx}:v]scale={scale}:force_original_aspect_ratio=decrease,"
            f"pad={scale}:(ow-iw)/2:(oh-ih)/2,fps=30,setsar=1[v{i}]")
        has_audio = bool(item.get("has_audio", True))
        if has_audio:
            parts.append(f"[{stream_idx}:a]aresample=48000,aformat=sample_fmts=fltp[a{i}]")
            audio_labels.append(f"[a{i}]")
        video_labels.append(f"[v{i}]")
        total += seg / max(0.1, float(speed))
        stream_idx += 1

    # 视频链：逐段 xfade 串联
    prev = video_labels[0]
    offset_acc = 0.0
    seg_durs = []
    for i, item in enumerate(timeline):
        dur = float(item.get("duration") or 0)
        trim_start = float(item.get("trim_start") or 0)
        trim_end = float(item.get("trim_end") or 0) or dur
        seg_durs.append(max(0.05, trim_end - trim_start) / max(0.1, float(speed)))
    for i in range(1, len(video_labels)):
        trans = TRANSITIONS.get(timeline[i].get("transition", "交叉溶解"))
        td = min(float(timeline[i].get("transition_duration") or 0.5), seg_durs[i - 1] * 0.8, seg_durs[i] * 0.8)
        if trans is None or td <= 0:
            # 直接切换：concat
            parts.append(f"{prev}{video_labels[i]}concat=n=2:v=1:a=0[xv{i}]")
            prev = f"[xv{i}]"
            offset_acc += seg_durs[i - 1]
        else:
            offset_acc += seg_durs[i - 1] - td
            parts.append(f"{prev}{video_labels[i]}xfade=transition={trans}:duration={td:.2f}:offset={offset_acc:.2f}[xv{i}]")
            prev = f"[xv{i}]"

    # 音频链：concat（无音频片段补静音较复杂，此处用 anullsrc 对齐简化为有音频片段拼接）
    if audio_labels:
        joined = "".join(audio_labels)
        if len(audio_labels) == 1:
            parts.append(f"{joined}anull[aout0]")
        else:
            parts.append(f"{joined}concat=n={len(audio_labels)}:v=0:a=1[aout0]")
        audio_map = ["-map", "[aout0]"]
    else:
        audio_map = ["-an"]

    # 字幕/水印（作用于最终视频流）
    post = []
    esc = subtitle.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    if subtitle:
        post.append(f"drawtext=text='{esc}':fontcolor=white:fontsize={int(int(scale.split(':')[1]) / 18)}"
                    f":borderw=2:x=(w-text_w)/2:y=h-120:enable='between(t,1,6)'")
    wesc = watermark.replace(":", "\\:").replace("'", "\\'")
    if watermark:
        post.append(f"drawtext=text='{wesc}':fontcolor=white@0.7:fontsize={int(int(scale.split(':')[1]) / 26)}"
                    f":borderw=1:x=w-text_w-30:y=30")
    if post:
        parts.append(f"{prev}{','.join(post)}[vout]")
        vout = "[vout]"
    else:
        vout = prev

    cmd = [ffmpeg, "-hide_banner", "-y"]
    for extra in inputs:
        cmd += [extra]
    if bgm and Path(bgm).is_file():
        cmd += ["-i", str(bgm)]

    filters = ";".join(parts)
    bgm_chain = ""
    if bgm and Path(bgm).is_file():
        bgm_idx = stream_idx
        fade = f",afade=t=out:st={max(0, total - 2):.2f}:d=2" if bgm_fadeout else ""
        bgm_chain = (f";[{bgm_idx}:a]volume={bgm_volume},aloop=loop=-1:size=2e9,"
                     f"atrim=0:{total:.2f}{fade},aresample=48000[bmg]")
        filters += bgm_chain
        # 若主音轨存在则混音，否则 BGM 单独
        if audio_labels:
            filters += f";[aout0][bmg]amix=inputs=2:duration=first:dropout_transition=3[aout]"
            audio_map = ["-map", "[aout]"]
        else:
            audio_map = ["-map", "[bmg]"]

    cmd += ["-filter_complex", filters, "-map", vout, *audio_map,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-shortest",
            "-progress", "pipe:1", "-nostats", str(target)]
    return cmd, total


class RenderRequest(BaseModel):
    project_id: str


@router.post("/projects/{project_id}/render")
async def render(project_id: str, body: RenderRequest | None = None,
                 user: dict = Depends(require_user)) -> Dict[str, Any]:
    project = _PROJECTS.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="工程不存在")
    from mixcut_av_tools import find_tool
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        raise HTTPException(status_code=503, detail="未找到 ffmpeg，无法渲染")

    timeline = []
    for item in project["timeline"]:
        clip = _CLIPS.get(item["clip_id"])
        if clip is None:
            raise HTTPException(status_code=422, detail=f"片段 {item['clip_id']} 已不存在，请先补传")
        timeline.append({**item, "clip_path": clip["path"], "duration": clip.get("duration") or 0,
                         "has_audio": bool(clip.get("codec") or True)})

    bgm_file = None
    bgms = sorted(BGM_DIR.glob("bgm.*"))
    if bgms:
        bgm_file = str(bgms[0])

    target = OUTPUT_DIR / f"mixcut-{project_id}-{uuid.uuid4().hex[:4]}.mp4"
    try:
        cmd, est = await asyncio.to_thread(
            build_mixcut_command, ffmpeg, timeline, project["resolution"], bgm_file,
            float(project.get("bgm_volume", 0.3)), bool(project.get("bgm_fadeout", True)),
            project.get("subtitle_text", ""), project.get("watermark", ""),
            float(project.get("output_speed", 1.0)), target)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"混剪参数构建失败：{exc}") from None

    job_id = f"j-{uuid.uuid4().hex[:10]}"
    job = {"job_id": job_id, "project_id": project_id, "status": "running", "progress": 0.0,
           "output_path": str(target), "output_name": target.name, "output_size": 0,
           "estimated_duration": est, "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
           "error": "", "command": cmd}
    _JOBS[job_id] = job
    _save(JOBS_FILE, {k: _public(v) for k, v in _JOBS.items()})
    _RUNNING[job_id] = asyncio.create_task(_run_job(job_id, cmd, est, target))
    return {"job_id": job_id}


async def _run_job(job_id: str, cmd: list[str], est: float, target: Path) -> None:
    job = _JOBS[job_id]
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.PIPE)
        job["_proc"] = proc
        est_us = max(est, 0.1) * 1_000_000
        assert proc.stdout is not None
        async for raw in proc.stdout:
            done_us = parse_progress_line(raw.decode("utf-8", errors="replace").strip())
            if done_us is not None:
                job["progress"] = min(0.99, done_us / est_us)
        rc = await proc.wait()
        stderr = (await proc.stderr.read()).decode("utf-8", errors="replace") if proc.stderr else ""
        if rc == 0 and target.is_file():
            job.update(status="done", progress=1.0, output_size=target.stat().st_size)
        else:
            job.update(status="failed", error=stderr.strip()[-600:] or f"ffmpeg 退出码 {rc}")
    except asyncio.CancelledError:
        proc = job.get("_proc")
        if proc is not None and proc.returncode is None:
            proc.kill()
        job["status"] = "cancelled"
        raise
    except Exception as exc:  # noqa: BLE001
        job.update(status="failed", error=str(exc))
    finally:
        job.pop("_proc", None)
        _RUNNING.pop(job_id, None)
        _save(JOBS_FILE, {k: _public(v) for k, v in _JOBS.items()})


@router.get("/jobs")
async def list_jobs(user: dict = Depends(require_user)) -> Dict[str, Any]:
    return {"jobs": sorted((_public(j) for j in _JOBS.values()),
                           key=lambda j: j["created_at"], reverse=True)}


@router.get("/jobs/{job_id}")
async def job_status(job_id: str, user: dict = Depends(require_user)) -> Dict[str, Any]:
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _public(job)


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, user: dict = Depends(require_user)) -> Dict[str, Any]:
    task = _RUNNING.get(job_id)
    if task is None:
        raise HTTPException(status_code=409, detail="任务不在运行中")
    job = _JOBS.get(job_id) or {}
    proc = job.get("_proc")
    if proc is not None and proc.returncode is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
    task.cancel()
    return {"cancelling": job_id}


@router.get("/jobs/{job_id}/download")
async def download(job_id: str, user: dict = Depends(require_user)) -> FileResponse:
    job = _JOBS.get(job_id)
    if job is None or job.get("status") != "done":
        raise HTTPException(status_code=404, detail="产物不存在或任务未完成")
    path = Path(job["output_path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="产物文件已丢失")
    return FileResponse(path, filename=path.name)


app = PawApp(name="QwenPaw Creator · 智能混剪", app_id="qwenpaw-creator-mixcut")
app.include_router(router)


@app.on_terminate
async def shutdown_mixcut() -> None:
    for jid, task in list(_RUNNING.items()):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


plugin = app
