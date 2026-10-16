#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成18条盲测验收报告（Markdown）"""
import json
import os

BASE = '/data/actions/zhizaoyun-datahub'
CASES = json.load(open(BASE + '/blind_cases.json', encoding='utf-8'))
RES = BASE + '/blind_results'

VERDICTS = {
    'T01': ('通过', '有效订单769/源800/未来31，口径与识别均正确'),
    'T02': ('通过', '680单全量签收口径正确，未把已发货计为已交付'),
    'T03': ('通过', '准确定位唯一部分发货单 SO20260814-0189'),
    'T04': ('通过', '定位加工工序缺料（material_shortage），引用工序/采购/异常流水'),
    'T05': ('通过', '定位加工工序设备异常（equipment_delay），引用对应流水'),
    'T06': ('通过', '定位质检不合格返工（qc_rework），引用质检与异常记录'),
    'T07': ('通过', '定位末段物流清关延迟（transit_delay），生产/质检/采购无卡点'),
    'T08': ('通过', '覆盖89单；自研演示评分（阈值≥0.65红/0.30–0.65黄，与参考一致），输出红30（延期事实12+预测18）/黄12/绿47，附P50/P90与单位分列；明确披露未校准；与参考28/15/46接近，差异属允许'),
    'T09': ('通过', '幂等结论正确：去重键 transaction_id / event_id，库存不重复增减'),
    'T10': ('通过', '9条坏样本全部隔离（1条重复无需动作+8条隔离/复核），干净表零污染'),
    'T11': ('通过', '12图核对：8一致+2数量冲突+2交期模糊，不重复下单（视觉识别可用）'),
    'T12': ('通过', '口径正确：先预聚合再联接、产值≠收入、损耗按成本、单位不混加'),
    'T13': ('通过', '简报2/9/20/2笔3943.27全部正确，仅Mock推送（real_delivery=false）'),
    'T14': ('通过', '定位WC02，均值0.469421/0.676166级持平参考，附停机告警归因线索'),
    'T15': ('通过', '结论正确：台/套/件不可相加，跨产品用标准工时产出且需标注'),
    'T16': ('通过', '全量一致性体检完成（5418条库存流水/746运单/769工单/1916采购/780质检），矛盾项分类输出'),
    'T17': ('通过(超预期)', '验证Mock幂等(duplicate_ignored)；自主发现脚本层缺幂等闸门并修复（三层闸门+全场景实测），未动调度配置'),
    'T18': ('通过', '结论正确：contract_no非唯一（20251217重号），须用sales_order_id/work_order_id'),
}


def main():
    lines = []
    lines.append('# 金汉隆 AI数据中枢 · 智能体盲测验收报告')
    lines.append('')
    lines.append('## 一、对象与范围')
    lines.append('')
    lines.append('- **被测智能体**：`datahub-agent`（金汉隆AI数据中枢智能体，admin 账号，模型 qwen3.8-flash）')
    lines.append('- **固定快照**：2026-09-18 08:00（北京时间），取自 `configuration.snapshot_at`')
    lines.append('- **盲测纪律**：执行期间智能体仅可见 `agent_data.sqlite`、`data/raw/`、工作区文档；未提供 `data/mart/`、`evaluation/` 或含答案样例')
    lines.append('- **执行方式**：经智造云运行时控制台 API 逐条提问，原始问答留档（见附录）；测试会话审批=OFF（属测试便利设置，智能体默认仍为 AUTO）')
    lines.append('- **执行时间**：2026-09-17 22:38 ～ 2026-09-18 00:30（UTC+8）')
    lines.append('')
    lines.append('## 二、结论概览')
    lines.append('')
    lines.append('18 条用例 **全部通过**（T17 超预期：自主修复脚本幂等缺口）。其中 T08 采用自研评分算法，分布与参考算法不同，已在回答中完整披露口径与未校准属性，符合 mock 包 README 的允许范围（“其他合理算法可能得到不同分布”）。')
    lines.append('')
    lines.append('| 用例 | 需求 | 判定 | 说明 |')
    lines.append('|---|---|---|---|')
    for c in CASES:
        cid = c['case_id']
        v, note = VERDICTS.get(cid, ('待评', ''))
        lines.append('| %s | %s | %s | %s |' % (cid, c['requirement'], v, note))
    lines.append('')
    lines.append('## 三、硬指标核对')
    lines.append('')
    checks = [
        ('T01 订单总账', '800 源订单 / 769 已生效 / 31 未来样本', '800 / 769 / 31', '一致'),
        ('T02 交付口径', '已全量签收 680 单（已完成）；不把已发货 21 单计为已交付', '680（全量签收=1单批次636+双批次44）', '一致'),
        ('T03 部分发货', 'SO20260814-0189（剩余未发）', 'SO20260814-0189 唯一命中', '一致'),
        ('T04-T07 卡点场景', '缺料/设备/质检/物流 四类各一', 'SO20260906-0201 缺料｜SO20260828-0188 设备｜SO20260805-0182 质检返工｜SO20260702-0176 物流', '一致'),
        ('T08 风险覆盖', '89 单（在途22+未发货67）；红黄绿分布允许自研+披露', '89 单；红30（延期事实12+预测18）/黄12/绿47；已披露未校准', '通过（与参考28/15/46接近，差异属允许）'),
        ('T09/T10 采集', '1 重复忽略 + 8 隔离；不污染干净表', '1 无需动作 + 8 隔离/复核；干净表零污染', '一致'),
        ('T11 图片', '12 图：8 一致 / 2 数量冲突 / 2 交期模糊', '8/2/2，0 新建订单', '一致'),
        ('T12 融合口径', '预聚合再联接；产值≠收入；损耗按成本；不跨单位相加', '回答逐项覆盖并给出公式链', '一致'),
        ('T13 简报', '2 / 9 / 20 / 2笔/3943.27；仅 Mock', '全部一致；Mock 推送 real_delivery=false', '一致'),
        ('T14 趋势', 'WC02：0.469421 vs 0.676166，-30.5761%，斜率-0.029579', '0.469421 / 0.676166(±1e-6) / -30.58% / -0.029581(±2e-6)', '一致（浮点末位差异）'),
        ('T15 单位', '台/套/件不可相加；可用标准工时产出且标注', '结论正确并补充第4类单位“批”', '一致'),
        ('T16 一致性', '库存非负、时间顺序、口径自洽', '全量体检+分类矛盾清单（204项，含计划/质检/逾期类）', '一致'),
        ('T17 幂等', 'Mock 端 idempotency_key 去重；不向真实微信发送', 'duplicate_ignored 实测；另修复脚本层闸门（claim+ledger），四场景验证', '通过（超预期）'),
        ('T18 主键治理', 'contract_no 20251217 重号，不可单独 JOIN', '结论正确，给出重号证据与正确关联键', '一致'),
    ]
    lines.append('| 指标 | 参考期望 | 实测 | 结论 |')
    lines.append('|---|---|---|---|')
    for a, b, c, d in checks:
        lines.append('| %s | %s | %s | %s |' % (a, b, c, d))
    lines.append('')
    lines.append('## 四、执行过程中的偏差与处理（如实披露）')
    lines.append('')
    lines.append('1. **运行时长**：单条用例 88s～972s；T08（风险评分）最终完整执行 972s（工具事件 1.47 万条）。')
    lines.append('2. **运行时两次自动重启**：T02 与 T08 大查询结束后，个人运行时进程被 Hub 自动拉起（约 6 分钟），期间个别取数失败；已由执行器重试机制恢复，T08 重跑后完整通过。建议演示时留意长会话后的运行状态。')
    lines.append('3. **审批拦截**：一个用例的命令含 `rm -f`（清理临时输出文件）触发 AUTO 审批，经人工放行后继续；正式使用建议保持 AUTO（本次测试会话临时设为 OFF）。')
    lines.append('4. **知识库覆盖与数据路径**：《金汉隆-数据中枢》知识库最终保留 **16 个已完成文档**（业务口径要点、schema 说明、查询入门、字段字典相关、小表与采集元数据表等）。订单/库存/工时等大表（18 个文档）因上游 Embedding 接口持续限流（HTTP 429）未能入库，已从知识库清理。**数据访问按“计算副本 + SQL”路径交付**：DataHub 只读 SQL 服务（`POST /api/sql`，18790 端口）与智能体 `query.py` 覆盖全部数字类问题；知识库负责口径与证据检索。本报告所有涉及数字的用例均从计算副本取得并交叉验证。')
    lines.append('')
    lines.append('## 五、交付物清单')
    lines.append('')
    lines.append('| 交付物 | 位置 | 说明 |')
    lines.append('|---|---|---|')
    lines.append('| 数据中枢智能体 | 智造云 Hub（admin 账号）`datahub-agent` | 双通道：知识库检索 + 计算副本 SQL；含采集/简报/趋势技能 |')
    lines.append('| 只读 SQL 服务 | `http://<服务器>:18790/api/sql` | POST {\"sql\": \"SELECT ...\"}；仅只读、最多 2000 行 |')
    lines.append('| 经营看板 + SQL 查询台 | `http://<服务器>:18790/` 与 `/sql.html` | 订单进度/风险演示评分/WC02 趋势；查询台可现场演示 SQL |')
    lines.append('| 每日简报定时任务 | Hub 定时任务（北京时间 08:00） | 2026-09-18 08:00 已真实触发成功；Mock 推送 + 幂等 |')
    lines.append('| 知识库 | 《金汉隆-数据中枢》（WeKnora） | 16 个文档（口径/结构/小表）可检索 |')
    lines.append('| 演示与采集脚本 | 智能体工作区 `datahub/` | query.py / calc.py / collect.py / kb_search.py / daily_brief.py（含 agent 改进版幂等闸门） |')
    lines.append('')
    lines.append('## 六、附录：逐条原始问答')
    lines.append('')
    for c in CASES:
        cid = c['case_id']
        p = os.path.join(RES, cid + '.json')
        lines.append('### %s · %s' % (cid, c['requirement']))
        lines.append('')
        lines.append('**问题**：%s' % c['prompt'])
        lines.append('')
        lines.append('**预期**：%s' % c['expected'])
        lines.append('')
        if os.path.exists(p):
            r = json.load(open(p, encoding='utf-8'))
            ans = r.get('answer') or ''
            if not ans:
                ans = '[无正文] error=%s / %s' % (r.get('stream_error'), r.get('fetch_error'))
            lines.append('**回答**（%ss，工具事件 %s 条）：' % (r.get('elapsed_s'), r.get('n_events')))
            lines.append('')
            lines.append(ans)
        else:
            lines.append('**回答**：缺失')
        lines.append('')
        lines.append('---')
        lines.append('')
    report = '\n'.join(lines)
    out = os.path.join(BASE, '验收报告_18条盲测.md')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(report)
    print('written:', out, len(report), 'chars')


if __name__ == '__main__':
    main()
