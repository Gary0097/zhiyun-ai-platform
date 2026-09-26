---
name: office-file-reader
description: "任意文件读取分流入口：文本直读（编码检测、大文件分段），Office/PDF/图片分流对应技能。触发：读取文件、总结文档、乱码。"
metadata:
  version: "1.0.0"
  qwenpaw:
    emoji: "📂"
---

# 办公技能 · 通用文件读取（分流入口）

本技能是"给我看看这个文件"的**统一入口**：先识别类型，再路由到正确技能，
避免用错误的方式打开文件浪费时间。

## 1. 分流表（第一步永远是它）

| 类型 | 判断依据 | 路线 |
| --- | --- | --- |
| 文本类：txt / md / json / csv / tsv / log / ini / yaml / 代码 / sql | 扩展名 + 二进制探测为文本 | 本技能 §2 直接读 |
| .docx / .doc | 扩展名 | `office-word`（.doc 先转 .docx） |
| .xlsx / .xlsm / .csv(复杂) | 扩展名 | `office-excel` |
| .pptx | 扩展名 | `office-ppt` |
| .pdf | 扩展名 | `office-pdf`（扫描件再转 `office-ocr`） |
| 图片：png / jpg / webp / bmp | 扩展名 | 提取文字 → `office-ocr`；看内容用看图工具 |
| .zip / .rar / 7z | 扩展名 | shell 解压到 `解压_<文件名>/` 后逐个分流 |
| 未知/无扩展名 | `file` 命令 / 头字节 | 报告实际类型，向用户确认处理方式 |

```python
# 快速探测：路径读前 4KB，含大量 \x00 → 二进制
with open(path, 'rb') as f: head = f.read(4096)
is_binary = b'\x00' in head
```

## 2. 文本类读取规范

- **编码**：默认 UTF-8；报 `UnicodeDecodeError` 或出现"锟斤拷/烫烫"乱码时，
  用 `chardet`（已预装）探测后按 GBK/GB18030 重读；
  ```python
  import chardet
  raw = open(path, 'rb').read()
  enc = chardet.detect(raw[:65536])['encoding'] or 'utf-8'
  text = raw.decode(enc, errors='replace')
  ```
- **大文件**（>5MB 或 >5 万行）：
  1. 先报统计（行数、大小、首尾各 5 行）；
  2. 按需分段读取（`seek` + 分块），不要一次全读；
  3. 用户要"总结"时用滚动窗口分段摘要再合并。
- **CSV**：先看分隔符与表头再解析；乱码同上处理；转正式表格交给 `office-excel`。
- **JSON/日志**：JSON 解析失败时报告第一个非法位置；日志按时间范围/关键词过滤。

## 3. 输出规范

- 读取结果按用途输出：核对类 → 原文摘录 + 行号；总结类 → 结构化要点；
  提取类 → 目标字段表 + 来源位置（文件名+页码/行号），可溯源；
- 文件很大时先给"地图"（结构概览 + 每部分位置），让用户指定深入哪部分；
- 读不到/损坏的文件如实报告，不猜测内容。

## 4. 交付前检查单

- [ ] 走了对的分流路线（没有用文本方式硬啃 docx/pdf 二进制）；
- [ ] 编码正确无乱码；大文件有分页/分段策略；
- [ ] 提取内容带来源定位；没有编造文件里不存在的内容；
- [ ] 用户原件未被修改。

## 相关技能

`office-pdf` / `office-ocr` / `office-word` / `office-excel` / `office-ppt`
（分流目的地）；`office-computer`（批量文件操作）。
