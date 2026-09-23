---
name: huoban-sync
version: 1.0.0
description: "伙伴云(Huoban)CRM数据同步：把伙伴云合同表（业务员/推广人员/原始业务员/合同金额）同步进销售分析平台(8302)的业绩归因，并查询三本账与归因明细。当用户要求\"同步伙伴云\"、\"更新业绩归因\"、\"销售贡献排行\"、\"查某人的归因\"时使用。"
metadata:
  builtin_skill_version: "1.0.0"
  qwenpaw:
    emoji: "🔗"
    requires:
      bins: ["python3"]
---

# huoban-sync（伙伴云CRM → 销售分析平台·业绩归因）

伙伴云工作台页面（数据来源）：`https://app.huoban.com/navigations/3300000036414292/pages/7000000000360617`
当前数据通道：销售分析平台 `data/huoban/crm_contract.json`（伙伴云合同表导出，6881 行）；伙伴云 OpenAPI 凭据开通后切换直连。

## 命令速查（工作区根目录执行）

| 想做什么 | 命令 |
|---|---|
| 同步状态/覆盖情况 | `python3 skills/huoban-sync/huoban.py status` |
| **触发同步** | `python3 skills/huoban-sync/huoban.py sync` |
| 三本账排行 | `python3 skills/huoban-sync/huoban.py report --top 10` |
| 归因明细检索 | `python3 skills/huoban-sync/huoban.py orders --q 合同号/客户/工号` |

## 归因口径（与平台一致）

- 主销售 ← 伙伴云「业务员」；跟单 ← 「推广人员」（与业务员同人则不计）；协同 ← 「原始业务员」（与前两者同人则不计）
- 比例：单人 100% / 双人 75%+25% / 三人 60%+25%+15%；贡献金额 = 合同金额（元）× 比例
- 按「合同编号」UPSERT：已存在的归因行回填五字段，新合同插入

## 纪律

- 同步前先 `status` 查看最近一次结果；非必要不重复全量同步（幂等但没必要刷）。
- 数字一律以 `report`/`orders` 返回为准，不心算；回答注明"数据来源：伙伴云CRM合同表（同步于 <时间>）"。
