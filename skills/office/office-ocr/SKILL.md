---
name: office-ocr
description: "OCR 与文档识别技能。扫描件、图片型 PDF、照片、截图中的文字需要识别时使用；复杂版面（论文、书籍、报表）需要保留版式/公式/表格结构的高精度解析也用本技能（MinerU 云端/本地路线）。触发词：OCR、识别文字、扫描件、图片转文字、提取公式、论文解析、票据识别、截图内容、MinerU、扫描PDF。"
metadata:
  version: "1.0.0"
  qwenpaw:
    emoji: "🔍"
---

# 办公技能 · OCR 与文档识别

## 1. 路线选择（按精度需求与网络条件，从上往下选第一个可用的）

| 优先级 | 路线 | 适用 | 成本 |
| --- | --- | --- | --- |
| 1 | **文档解析 MCP 工具**（若已配置，如 MinerU MCP） | 任何复杂文档 | 零安装，直接调用 |
| 2 | **MinerU 云端 API**（`MINERU_API_KEY`） | 论文/书籍/复杂版面，需保留公式、表格结构 | 轻量 CLI，注册送免费额度 |
| 3 | **本地 RapidOCR**（已预装 `rapidocr_onnxruntime`） | 普通扫描件/截图/票据，离线可用 | 已预装，零等待 |
| 4 | 本地 MinerU 完整版（`mineru[core]`） | 无网络 + 复杂版面 | 重依赖（模型+GPU 更佳），仅在用户明确要求时安装 |

选择原则：**能不装包就不装包**。路线 3 已随办公技能包预装，开箱即用；
路线 2 只装轻量 CLI（不装本地模型）；路线 4 除非用户点名，否则不主动装。

## 2. 路线 1：文档解析 MCP 工具

如果控制台「MCP 与内置工具」中配置了文档解析类 MCP 服务（如 MinerU MCP、
其他 parse/ocr 工具），优先直接调用其工具，跳过本技能其余路线。
调用前确认该工具的隐私边界（是否上传文件到外部服务）并向用户说明。

## 3. 路线 2：MinerU 云端（推荐用于复杂文档）

MinerU（OpenDataLab）可把 PDF/图片精准解析为 Markdown/JSON，保留版面、
公式、表格。云端模式不下载本地模型，安装轻量：

```bash
pip install "mineru>=4"        # 仅 CLI；不要装 mineru[core]（那是本地模型路线）
export MINERU_API_KEY=<在 mineru.net 控制台申请>   # Windows: setx MINERU_API_KEY "..."
mineru usage --json            # 查询额度/限额
mineru parse "论文.pdf" --remote --output-dir 解析结果/
```

纪律：
- **隐私红线**：`--remote` 会把文件上传到云端解析。**必须先告知用户并取得同意**
  （"该文件将上传至 MinerU 云端解析，是否继续？"），机密文件改走路线 3/4。
- 额度错误码处理：`invalid_api_key` → 检查 Key；`quota_exceeded` → 告知用户
  额度用尽并降级路线 3；`rate_limit_exceeded` → 等待后重试一次。
- 未配置 `MINERU_API_KEY` 时直接降级路线 3，不要反复尝试云端。

## 4. 路线 3：本地 RapidOCR（默认兜底，已预装）

```python
from rapidocr_onnxruntime import RapidOCR
ocr = RapidOCR()
result, _ = ocr("扫描件.png")
for line in result or []:      # [box, text, score]
    print(line[1], round(line[2], 2))
```

- 扫描 PDF 先转图片再逐页 OCR：`pdfplumber`/`pypdf` 提取页面图片，或
  LibreOffice/PyMuPDF 渲染整页（`page.to_image(resolution=200)`）；
- 输出按页分组、按坐标 y 排序恢复阅读顺序；置信度 < 0.6 的行标注 `[?]`
  供人工复核；
- 票据/证件类：只提取用户要求的字段，输出结构化 JSON；识别结果涉及
  身份证号/银行卡号等敏感信息时，仅在用户明确要求时整理输出，不主动扩散。

## 5. 识别后处理（所有路线通用）

1. **结构恢复**：OCR 结果按"标题/段落/表格"重排；表格用坐标聚类还原行列；
2. **校对**：抽 3–5 处与原图人工核对（对话中贴出对照截图坐标）；数字、
  日期、金额重点复核；
3. **交付**：输出 Markdown（保留结构）或由 `office-word`/`office-excel`
  生成可编辑文件；注明识别路线与置信度概况；
4. **不做的事**：不臆造 OCR 没识别出的内容；模糊处标注"[无法辨认]"。

## 6. 交付前检查单

- [ ] 选择了最少安装的可用路线，未无谓安装重依赖；
- [ ] 云端路线已获用户对上传的明确同意；
- [ ] 阅读顺序正确，表格结构还原，低置信度处已标注；
- [ ] 敏感信息按用户要求处理；
- [ ] 产物可编辑（md/docx/xlsx），并说明识别路线与局限。

## 相关技能

- `office-pdf`：文本型 PDF 直接提取（无需 OCR）；
- `office-file-reader`：文件类型分流入口；
- `office-excel` / `office-word`：识别结果成表成文。
