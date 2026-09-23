---
name: weknora_kb_qa
description: "智造云知识库(WeKnora)问数技能。当用户询问金汉隆/公司产品、设备型号、技术规格、包装机、装盒机、售后服务、生产工艺等企业知识问题，或明确要求查询知识库/问数时使用。通过 WeKnora API 检索知识库并生成基于文档的回答。Use when the user asks about company products, equipment specs, packaging machinery knowledge, or explicitly requests a knowledge-base lookup."
metadata:
  builtin_skill_version: "1.0"
  qwenpaw:
    emoji: "📚"
    requires: {}
---

# 智造云知识库问数 (WeKnora Knowledge QA)

通过本技能调用智造云知识库（WeKnora，服务地址 http://127.0.0.1:18000）的「通用产品知识库」进行检索问答（问数）。回答基于知识库中的真实文档，涉及产品型号、技术参数、适用范围等事实性问题必须优先使用本技能。

## 使用方法

本技能所在目录下有 `scripts/ask_weknora.py`（以本 SKILL.md 所在目录为根）。对用户的问题，在本技能目录中执行：

```bash
python3 scripts/ask_weknora.py "用户的问题"
```

（若当前目录不是本技能目录，先用 find/glob 定位 `weknora_kb_qa/scripts/ask_weknora.py` 再执行。）

脚本会自动完成登录、创建会话、绑定知识库、提问并汇总回答，最终把知识库生成的完整答案打印到 stdout。把该答案作为回答依据整理后回复用户。

说明：
- 脚本参数即自然语言问题，务必加引号。
- 默认检索「通用产品知识库」(id: b861158f-4b89-4715-bada-01d4bed1e40b)；如需检索其他知识库，用 `--kb <知识库ID>` 指定，多个知识库用逗号分隔。
- 回答通常为 Markdown（含表格），直接采用其中的数据，不要凭记忆改写数字。
- 若输出提示登录失败或连接失败，向用户说明知识库服务暂不可用。

## 适用场景

- 金汉隆（KITECH）包装设备：线性称重包装机、自动装盒机、数袋线、螺杆包装机、液体包装机、热收缩包装机等的型号、技术规格、适用袋型/盒型
- 公司产品资料、售后知识、生产工艺相关问题
- 用户明确说"问一下知识库"、"查知识库"、"问数"时

## 不适用场景

- 与企业知识库无关的通用编程、写作、闲聊问题（直接回答即可）
