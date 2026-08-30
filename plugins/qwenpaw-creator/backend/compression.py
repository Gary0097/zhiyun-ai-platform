# -*- coding: utf-8 -*-
"""视频压缩引擎 —— 移植自 灵泽万川视频工坊（MarukoToolbox-Rewrite）的压缩核心。

仅保留压缩链路：编码器表 / 预设 / 分辨率 / 音频模式 / ffmpeg 命令构建 /
媒体探测 / 进度解析。GUI、LUT、字幕、批量压制、怀旧转码等能力已舍弃。
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# ── 编码器（GPU 自动识别在 capabilities 中按可用性过滤） ──────────────
ENCODERS = {
    "GPU H.265 / HEVC (hevc_nvenc)": "hevc_nvenc",
    "GPU H.265 10-bit / HEVC Main10": "hevc_nvenc_10bit",
    "GPU H.264 / AVC (h264_nvenc)": "h264_nvenc",
    "GPU AV1 (av1_nvenc, RTX 40+)": "av1_nvenc",
    "AMD H.265 / HEVC (hevc_amf)": "hevc_amf",
    "AMD H.264 / AVC (h264_amf)": "h264_amf",
    "Intel H.265 / HEVC (hevc_qsv)": "hevc_qsv",
    "Intel H.264 / AVC (h264_qsv)": "h264_qsv",
    "CPU H.265 / HEVC (libx265)": "libx265",
    "CPU H.264 / AVC (libx264)": "libx264",
    "CPU AV1 (libsvtav1)": "libsvtav1",
}
ENCODER_FILENAME_TAGS = {
    "hevc_nvenc": "h265", "hevc_nvenc_10bit": "h265_10bit", "h264_nvenc": "h264",
    "av1_nvenc": "av1", "hevc_amf": "amd_h265", "h264_amf": "amd_h264",
    "hevc_qsv": "intel_h265", "h264_qsv": "intel_h264", "libx265": "h265",
    "libx265_10bit": "h265_10bit", "libx264": "h264", "libsvtav1": "av1",
}
PRESETS = {
    "极速": ("p1", "ultrafast"),
    "高速": ("p3", "veryfast"),
    "均衡": ("p5", "medium"),
    "高画质": ("p7", "slow"),
}
RESOLUTIONS = {
    "保持原分辨率": "",
    "2160p / 4K": "3840:2160",
    "1440p / 2K": "2560:1440",
    "1080p": "1920:1080",
    "720p": "1280:720",
    "竖屏 1080x1920": "1080:1920",
    "竖屏 720x1280": "720:1280",
}
SHARPEN_LEVELS = {
    "关闭": "",
    "轻度": "unsharp=5:5:0.6:3:3:0.0",
    "中度": "unsharp=5:5:1.0:3:3:0.0",
    "强力": "unsharp=7:7:1.4:5:5:0.0",
}
VIDEO_MUXERS = {
    "MP4 (.mp4)": ".mp4",
    "MKV (.mkv)": ".mkv",
    "MOV (.mov)": ".mov",
    "WebM (.webm)": ".webm",
}
AUDIO_MODES = {
    "复制音频流": "copy",
    "AAC 重新编码": "aac",
    "Opus 重新编码": "libopus",
    "MP3 重新编码": "libmp3lame",
    "移除音频": "none",
}
VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".avi", ".wmv", ".flv", ".webm",
    ".m4v", ".ts", ".mts", ".m2ts", ".rm", ".rmvb", ".vob", ".mpg", ".mpeg",
}


@dataclass(frozen=True)
class CompressionSettings:
    encoder_key: str
    preset_name: str
    resolution_name: str
    sharpen_name: str
    quality_mode: str          # crf | 2pass
    cq_value: int
    bitrate: str
    audio_mode: str
    audio_bitrate: str
    muxer_name: str
    output_speed: float
    overwrite: bool
    extra_ffmpeg_args: str


def find_tool(name: str) -> str | None:
    """定位 ffmpeg/ffprobe：插件 bin → 环境变量 → imageio-ffmpeg → PATH。"""
    override = os.environ.get(f"QWENPAW_CREATOR_{name.upper()}")
    if override and Path(override).is_file():
        return override
    bundled = Path(__file__).resolve().parent.parent / "bin" / (
        f"{name}.exe" if os.name == "nt" else name)
    if bundled.is_file():
        return str(bundled)
    if name == "ffmpeg":
        try:
            import imageio_ffmpeg  # venv 依赖（qwenpaw-creator requirements）
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:  # noqa: BLE001
            pass
    found = shutil.which(name)
    return found or None


def _run_capture(cmd: list[str]) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=30)
        return (result.stdout or "") + (result.stderr or "")
    except (OSError, subprocess.TimeoutExpired):
        return ""


_GPU_PROBE_CACHE: dict[str, bool] = {}


def _gpu_encoder_works(ffmpeg: str, encoder: str) -> bool:
    """用 1 帧空源试编码验证硬件编码器真实可用（含驱动/设备）。"""
    if encoder in _GPU_PROBE_CACHE:
        return _GPU_PROBE_CACHE[encoder]
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "nullsrc=s=64x64:d=0.1",
             "-frames:v", "1", "-c:v", encoder, "-f", "null", "-"],
            capture_output=True, text=True, timeout=15)
        ok = result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        ok = False
    _GPU_PROBE_CACHE[encoder] = ok
    return ok


def detect_environment() -> dict:
    ffmpeg = find_tool("ffmpeg")
    ffprobe = find_tool("ffprobe")
    encoders_text = _run_capture([ffmpeg, "-hide_banner", "-encoders"]).lower() if ffmpeg else ""
    # GPU 家族不能只看“编译进 ffmpeg”，还要硬件/驱动真实可用：
    # 用 1 帧空源试编码验证（结果进程内缓存，capabilities 只探测一次）。
    gpu_families = {
        "nvenc": "nvenc" in encoders_text and _gpu_encoder_works(ffmpeg, "hevc_nvenc"),
        "amf": "_amf" in encoders_text and _gpu_encoder_works(ffmpeg, "hevc_amf"),
        "qsv": "_qsv" in encoders_text and _gpu_encoder_works(ffmpeg, "hevc_qsv"),
    }

    def available(label: str, key: str) -> bool:
        code = ENCODERS[label]
        base = code.replace("_10bit", "")
        if "nvenc" in code:
            return gpu_families["nvenc"]
        if code.endswith("_amf"):
            return gpu_families["amf"]
        if code.endswith("_qsv"):
            return gpu_families["qsv"]
        return base in encoders_text  # CPU 编码器

    encoders = [{"key": k, "label": k, "available": available(k, v)}
                for k, v in ENCODERS.items()]
    return {"ffmpeg": ffmpeg, "ffprobe": ffprobe, "encoders": encoders,
            "ready": bool(ffmpeg)}


def probe_media_info(source: Path) -> dict:
    """优先 ffprobe JSON；缺失时回退解析 ffmpeg -i 的 stderr。文件不存在返回空。"""
    if not source.is_file():
        return {}
    ffprobe = find_tool("ffprobe")
    if ffprobe:
        out = _run_capture([ffprobe, "-v", "error", "-show_format",
                            "-show_streams", "-of", "json", str(source)])
        try:
            data = json.loads(out[out.index("{"):out.rindex("}") + 1])
            fmt = data.get("format", {})
            video = next((s for s in data.get("streams", [])
                          if s.get("codec_type") == "video"), {})
            return {
                "duration": float(fmt.get("duration") or 0),
                "size": int(fmt.get("size") or 0),
                "bit_rate": int(fmt.get("bit_rate") or 0),
                "width": int(video.get("width") or 0),
                "height": int(video.get("height") or 0),
                "codec": video.get("codec_name") or "",
                "fps": _parse_fps(video.get("avg_frame_rate") or video.get("r_frame_rate")),
            }
        except (ValueError, json.JSONDecodeError):
            pass
    ffmpeg = find_tool("ffmpeg")
    if ffmpeg:
        out = _run_capture([ffmpeg, "-hide_banner", "-i", str(source)])
        dur = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", out)
        dim = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", out)
        return {
            "duration": (int(dur.group(1)) * 3600 + int(dur.group(2)) * 60
                         + float(dur.group(3))) if dur else 0,
            "size": source.stat().st_size if source.exists() else 0,
            "bit_rate": 0,
            "width": int(dim.group(1)) if dim else 0,
            "height": int(dim.group(2)) if dim else 0,
            "codec": "",
            "fps": 0,
        }
    return {}


def _parse_fps(rate: str | None) -> float:
    try:
        num, _, den = (rate or "").partition("/")
        return round(float(num) / float(den or 1), 2)
    except (ValueError, ZeroDivisionError):
        return 0


def _even(value: int) -> int:
    value = max(2, int(value))
    return value if value % 2 == 0 else value - 1


def _filter_number(value: float) -> str:
    return format(value, "f").rstrip("0").rstrip(".")


def _resolve_encoder(encoder_key: str) -> tuple[str, str]:
    if encoder_key == "hevc_nvenc_10bit":
        return "hevc_nvenc", "p010le"
    return encoder_key, ""


def _audio_args(settings: CompressionSettings) -> list[str]:
    mode = AUDIO_MODES[settings.audio_mode]
    speed = settings.output_speed or 1.0
    if mode == "none":
        return ["-an"]
    if mode == "copy":
        if speed != 1.0:
            args = ["-af", f"atempo={_filter_number(min(max(speed, 0.5), 2.0))}", "-c:a", "aac"]
            if settings.audio_bitrate.strip():
                args += ["-b:a", settings.audio_bitrate.strip()]
            return args
        return ["-c:a", "copy"]
    args = ["-c:a", mode]
    if settings.audio_bitrate.strip() and mode != "libopus":
        args += ["-b:a", settings.audio_bitrate.strip()]
    elif mode == "libopus" and settings.audio_bitrate.strip():
        args += ["-b:a", settings.audio_bitrate.strip()]
    return args


def _video_filters(settings: CompressionSettings, use_gpu: bool) -> list[str]:
    filters: list[str] = []
    mode = RESOLUTIONS.get(settings.resolution_name, "")
    if mode:
        scale_options = ":force_original_aspect_ratio=decrease:force_divisible_by=2"
        filt = f"scale_cuda={mode}{scale_options}" if use_gpu else f"scale={mode}{scale_options}:flags=lanczos"
        filters.append(filt)
    sharpen = SHARPEN_LEVELS.get(settings.sharpen_name, "")
    if sharpen:
        filters.append(sharpen)
    speed = settings.output_speed or 1.0
    if speed != 1.0:
        filters.append(f"setpts=PTS/{_filter_number(speed)}")
    return filters


def build_compress_command(source: Path, target: Path,
                           settings: CompressionSettings) -> list[str]:
    ffmpeg = find_tool("ffmpeg")
    encoder, pix_fmt = _resolve_encoder(ENCODERS[settings.encoder_key])
    is_nvenc = "nvenc" in encoder
    is_amf = encoder.endswith("_amf")
    is_qsv = encoder.endswith("_qsv")
    preset_gpu, preset_cpu = PRESETS[settings.preset_name]
    cq = str(settings.cq_value)
    bitrate = settings.bitrate.strip()
    use_cpu_filters = bool(_video_filters(settings, False))

    cmd = [ffmpeg, "-hide_banner", "-y" if settings.overwrite else "-n"]
    if is_nvenc and not use_cpu_filters:
        cmd += ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
    elif is_nvenc:
        cmd += ["-hwaccel", "cuda"]
    cmd += ["-i", str(source)]

    filters = _video_filters(settings, is_nvenc and not use_cpu_filters)
    if filters:
        cmd += ["-vf", ",".join(filters)]

    cmd += ["-c:v", encoder]
    if is_nvenc:
        cmd += ["-preset", preset_gpu, "-rc", "vbr", "-cq", cq, "-b:v", bitrate or "0",
                "-spatial-aq", "1", "-temporal-aq", "1", "-rc-lookahead", "32",
                "-bf", "3", "-surfaces", "64"]
    elif is_amf:
        amf_quality = {"p1": "speed", "p3": "speed",
                       "p5": "balanced", "p7": "quality"}.get(preset_gpu, "balanced")
        cmd += ["-quality", amf_quality]
        if bitrate:
            cmd += ["-rc", "vbr", "-b:v", bitrate]
        else:
            cmd += ["-rc", "cqp", "-qp_i", cq, "-qp_p", cq, "-qp_b", cq]
    elif is_qsv:
        cmd += (["-b:v", bitrate] if bitrate else ["-global_quality", cq])
    else:
        if encoder == "libsvtav1":
            cmd += ["-preset", "6", "-crf", cq]
        else:
            cmd += ["-preset", preset_cpu, "-crf", cq]
        if bitrate:
            cmd += ["-b:v", bitrate]

    if pix_fmt:
        cmd += ["-pix_fmt", pix_fmt]
    cmd += _audio_args(settings)
    if settings.extra_ffmpeg_args.strip():
        cmd += shlex.split(settings.extra_ffmpeg_args.strip(), posix=False)
    cmd += ["-map_metadata", "0", "-progress", "pipe:1", "-nostats", str(target)]
    return cmd


def output_filename(source: Path, settings: CompressionSettings) -> str:
    tag = ENCODER_FILENAME_TAGS.get(ENCODERS[settings.encoder_key], "x")
    ext = VIDEO_MUXERS.get(settings.muxer_name, ".mp4")
    return f"{source.stem}_{tag}{ext}"


PROGRESS_RE = re.compile(r"out_time_ms=(\d+)")


def parse_progress_line(line: str) -> int | None:
    """从 ffmpeg -progress 输出行提取已处理微秒数。"""
    match = PROGRESS_RE.search(line)
    return int(match.group(1)) if match else None
