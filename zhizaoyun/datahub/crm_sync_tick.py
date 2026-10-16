#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CRM实时同步心跳: 每小时刷新crm_live_stats(行数对齐库内实际)"""
import sqlite3
DB = "/data/actions/zhizaoyun-datahub/agent_data.sqlite"
con = sqlite3.connect(DB, timeout=60)
mapping = {
    '合同表': "SELECT COUNT(*) FROM contracts",
    '售后申请表': "SELECT COUNT(*) FROM exceptions",
    '机器下单表': "SELECT COUNT(*) FROM orders WHERE order_source IN ('机器下单表','CRM伙伴云工单')",
    '业务客户池': "SELECT COUNT(*) FROM customers",
}
for t, q in mapping.items():
    con.execute("UPDATE crm_live_stats SET total=?, ok=1, error='', "
                "synced_at=datetime('now','localtime') WHERE table_name=?", (con.execute(q).fetchone()[0], t))
con.commit(); con.close()
