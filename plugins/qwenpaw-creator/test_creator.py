# -*- coding: utf-8 -*-
"""QwenPaw Creator（视频压缩版）引擎与路由单元测试。

不依赖运行中的服务：命令构建用假 ffmpeg 路径校验参数拼装；
进度解析与探测回退逻辑独立验证。运行：python -m unittest discover plugins/qwenpaw-creator
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from compression import (  # noqa: E402
    AUDIO_MODES,
    ENCODERS,
    PRESETS,
    RESOLUTIONS,
    CompressionSettings,
    build_compress_command,
    output_filename,
    parse_progress_line,
    probe_media_info,
)


def _settings(**overrides):
    base = dict(
        encoder_key="GPU H.265 / HEVC (hevc_nvenc)",
        preset_name="均衡",
        resolution_name="保持原分辨率",
        sharpen_name="关闭",
        quality_mode="crf",
        cq_value=28,
        bitrate="",
        audio_mode="复制音频流",
        audio_bitrate="192k",
        muxer_name="MP4 (.mp4)",
        output_speed=1.0,
        overwrite=False,
        extra_ffmpeg_args="",
    )
    base.update(overrides)
    return CompressionSettings(**base)


class EngineTests(unittest.TestCase):
    def test_nvenc_command_shape(self):
        cmd = build_compress_command(Path("in.mp4"), Path("out.mp4"), _settings())
        self.assertIn("-hwaccel", cmd)
        self.assertIn("cuda", cmd)
        self.assertIn("hevc_nvenc", cmd)
        self.assertIn("-cq", cmd)
        self.assertIn("28", cmd)
        self.assertIn("-c:a", cmd)
        self.assertIn("copy", cmd)
        # 进度输出必须开启，前端进度依赖它
        self.assertIn("-progress", cmd)

    def test_cpu_command_shape(self):
        cmd = build_compress_command(
            Path("in.mp4"), Path("out.mp4"),
            _settings(encoder_key="CPU H.264 / AVC (libx264)"))
        self.assertNotIn("cuda", cmd)
        self.assertIn("libx264", cmd)
        self.assertIn("-crf", cmd)

    def test_resolution_scale_filter(self):
        cmd = build_compress_command(
            Path("in.mp4"), Path("out.mp4"),
            _settings(encoder_key="CPU H.264 / AVC (libx264)",
                      resolution_name="1080p"))
        vf = cmd[cmd.index("-vf") + 1]
        self.assertIn("scale=1920:1080", vf)
        self.assertIn("force_original_aspect_ratio=decrease", vf)

    def test_remove_audio(self):
        cmd = build_compress_command(
            Path("in.mp4"), Path("out.mp4"),
            _settings(audio_mode="移除音频"))
        self.assertIn("-an", cmd)
        self.assertNotIn("-c:a", cmd)

    def test_output_filename_tag(self):
        name = output_filename(Path("会议录屏.mp4"), _settings())
        self.assertTrue(name.startswith("会议录屏_h265"))
        self.assertTrue(name.endswith(".mp4"))

    def test_progress_parsing(self):
        self.assertEqual(parse_progress_line("out_time_ms=1234567"), 1234567)
        self.assertIsNone(parse_progress_line("frame=  42 fps=30"))

    def test_catalogs_present(self):
        self.assertGreaterEqual(len(ENCODERS), 10)
        self.assertEqual(len(PRESETS), 4)
        self.assertIn("保持原分辨率", RESOLUTIONS)
        self.assertIn("移除音频", AUDIO_MODES)

    def test_probe_missing_file_returns_empty(self):
        self.assertEqual(probe_media_info(Path("Z:/definitely/missing.mp4")), {})


if __name__ == "__main__":
    unittest.main()
