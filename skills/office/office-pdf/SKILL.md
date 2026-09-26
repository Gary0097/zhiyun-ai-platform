---
name: office-pdf
description: "PDF 读取识别（文本/表格提取）、合并拆分、加密水印、生成与转换。触发：PDF、提取表格、拆分合并、加水印、转Word。"
metadata:
  version: "1.0.0"
  qwenpaw:
    emoji: "📑"
---

# 办公技能 · PDF 文件

## 0. 环境说明（办公版已预装，直接用）

办公技能包依赖已由启动器预装到项目运行环境（`pdfplumber` / `pypdf` / `fpdf2` /
`Pillow` / `pandas`），**不要在对话中重复安装**。仅当 import 报缺失时才补装：

```bash
python -c "import pdfplumber, pypdf, fpdf; print('ok')"
```

## 1. 读取分流（先判断 PDF 类型，再选路线）

| PDF 类型 | 判断方法 | 路线 |
| --- | --- | --- |
| 文本型（可复制文字） | `pdfplumber` 打开后首页 `extract_text()` 有内容 | 本技能直接提取 |
| 扫描件/图片型 | 提取不到文字或乱码 | 转 `office-ocr` 技能 |
| 加密 PDF | `pypdf` 抛 `PdfReadError: File has not been decrypted` | 先向用户要密码，`pypdf` 解密后再处理 |

```python
import pdfplumber
with pdfplumber.open("文件.pdf") as pdf:
    print("页数:", len(pdf.pages))
    text = pdf.pages[0].extract_text() or ""   # 空 → 大概率是扫描件
```

## 2. 文本与表格提取

- **整篇文本**：逐页 `extract_text()`，按页标注（`## 第 N 页`），保留页码以便引用核对；
- **表格**：`page.extract_tables()`；多页表格逐页提取后合并，注意核对列数一致，
  表头跨页时只保留一次；
- **图片**：`page.images` 拿到坐标后导出，文件名 `页码_序号.png`；
- **大文件**（>100 页）：先报告总页数与预计耗时，提取结果分批落盘（JSON/CSV），
  不要一次性塞进对话。

## 3. 页面操作（pypdf）

```python
from pypdf import PdfReader, PdfWriter
# 合并
w = PdfWriter()
for f in ["a.pdf", "b.pdf"]:
    for p in PdfReader(f).pages: w.add_page(p)
w.write("合并.pdf")
# 拆分（第 2-5 页）/ 旋转 / 加密
w2 = PdfWriter(); [w2.add_page(PdfReader("a.pdf").pages[i]) for i in range(1, 5)]
w2.write("拆分_2-5页.pdf")
w3 = PdfWriter(); w3.append("a.pdf"); w3.encrypt("用户提供的密码"); w3.write("加密.pdf")
```

- 用户原件**只读**：一切产物写新文件（`原名_合并.pdf` 等），不覆盖原件。

## 4. 生成 PDF（按复杂度选路线）

1. **简单生成**（合同、清单、报告类直排文档）：`fpdf2` 从零生成；
   中文字体必须嵌入本机已有字体（如 `C:/Windows/Fonts/msyh.ttc` 思源黑体），
   否则中文变方块。
2. **复杂排版**：先用 `office-word`/`office-ppt` 生成，再由 LibreOffice 转 PDF：
   `soffice --headless --convert-to pdf 文件.docx`（转换后抽查首页与总页数）。
3. **网页/长文转 PDF**：先整理为干净的 HTML/Markdown，再走路线 2。

## 5. 转换为其他格式

- PDF → Word：文本+表格提取（路线 §2）后由 `office-word` 重建 docx，
  **告知用户**复杂版式（多栏、脚注、精确分栏）只能近似还原；
- PDF → Markdown：按"标题/段落/表格"结构化输出；配合 `office-ocr` 的
  MinerU 路线可保留公式与复杂版面；
- PDF → 图片：LibreOffice 转 PDF→PNG，或 Pillow 渲染页缩略图用于人工核对。

## 6. 交付前检查单

- [ ] 已判断 PDF 类型，扫描件走了 office-ocr；
- [ ] 提取的数字做了抽样核对（随机抽 3 处与原文对照）；
- [ ] 表格列对齐、表头无重复；产物是新文件，原件未动；
- [ ] 加密/水印操作使用的是用户提供的密码，未在日志/回复中回显明文密码；
- [ ] 大文件处理有进度汇报。

## 相关技能

- `office-ocr`：扫描件、图片型 PDF、公式的识别；
- `office-excel`：提取的表格转规范 xlsx；
- `office-word`：提取内容重建可编辑文档；
- `office-file-reader`：非 PDF 文件的通用读取入口。
