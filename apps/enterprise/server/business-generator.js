// 企业业务数据自动生成器（Business Data Generator）
// 按租户生成"关联成体系"的业务数据：客户 → 订单（状态机推进）→ 库存（随订单消耗）
// → 财务（月度收入/应收随订单额派生）→ 售后工单（按设备安装量派生）。
// 与 simulator.js（运行数据模拟）互补：本模块只写 business_* 业务表，
// 全部 data_origin = 'generated'，不碰 runtime_*/log_*。
import { db } from './db.js'

const ORIGIN = 'generated'

function mulberry32 (seed) {
  return function () {
    seed |= 0; seed = seed + 0x6D2B79F5 | 0
    let t = Math.imul(seed ^ seed >>> 15, 1 | seed)
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t
    return ((t ^ t >>> 14) >>> 0) / 4294967296
  }
}

const pick = (rnd, arr) => arr[Math.floor(rnd() * arr.length)]
const round2 = n => Math.round(n * 100) / 100
const day = d => d.toISOString().slice(0, 10)

// ---------------------------------------------------------------------------
// 行业画像：每租户一套产品/物料/客户池，数据成体系不串味
// ---------------------------------------------------------------------------

const TENANT_PROFILE = {
  1: { // 智造精密：精密零部件制造
    customers: ['华南汽车集团', '华东重工', '北方轨道交通', '江门摩托车厂', '株洲电力机车', '佛山家电配件厂', '东莞智能装备', '长沙工程机械'],
    products: [['主轴组件 S-200', 850], ['精密齿轮箱 G-50', 3200], ['伺服支架 X-8', 96], ['谐波减速器 R-32', 5600], ['直线导轨 L-45', 420], ['滚珠丝杠 B-20', 780], ['精密联轴器 C-15', 310], ['气动夹爪 P-8', 1240]],
    materials: [['42CrMo 圆钢', 200, 45, '宝钢'], ['SKF 轴承 6208', 120, 25, 'SKF 中国'], ['铝合金 6061-T6 板', 300, 38, '南山铝业'], ['精密齿坯锻件', 80, 12, '江苏丰东'], ['直线导轨毛坯', 60, 9, '银泰科技']],
    devices: ['CNC-加工中心 VMC850', '数控车床 CK6150', '磨床 MK1320', '加工中心 VMC1160'],
    faults: ['主轴异响，加工精度下降', '液压系统漏油', '导轨润滑不足报警', '伺服电机过热', '刀库换刀卡滞', '冷却液泵流量不足'],
    regions: ['华南', '华东', '华北', '华中'],
    orderScale: 28, // 月均新订单
  },
  2: { // 华越装备：矿山/电力重型装备
    customers: ['中西部矿业', '南方电力', '山西煤矿集团', '云南水电十四局', '贵州磷化工', '内蒙古风场', '广西港口机械'],
    products: [['矿用减速机 K-7', 15800], ['高压配电柜 D-3', 42000], ['带式输送机驱动单元', 86000], ['斗轮堆取料机部件', 128000], ['重型联轴器 Z-100', 9600], ['提升机变频控制柜', 68000], ['破碎机衬板组件', 22000]],
    materials: [['H62 黄铜板', 300, 60, '洛阳铜业'], ['42CrMo 锻件', 90, 14, '中信重工'], ['高压断路器触头', 40, 6, '西电集团'], ['重型轴承 23256', 25, 5, '洛阳轴承']],
    devices: ['矿用提升机 JK-2.5', '带式输送机 DTII', '高压开关柜 KYN28', '斗轮取料机 DQ1000'],
    faults: ['减速机齿轮点蚀', '液压站油温过高', '制动器响应迟滞', '皮带跑偏报警', '变频器过流跳闸'],
    regions: ['西南', '华南', '华北'],
    orderScale: 12,
  },
  3: { // 恒新零部件：模具与冲压件
    customers: ['珠三角电子厂', '深圳连接器厂', '惠州电池壳体厂', '广州汽配城商户', '珠海医疗器件厂'],
    products: [['冲压模具 M-12', 68000], ['级进模 P-8', 92000], ['精密冲压件 J-05', 3.8], ['电池托盘冲压件', 46], ['连接器端子模组', 128], ['医疗导管注塑模', 58000]],
    materials: [['Cr12MoV 模具钢', 60, 8, '东北特钢'], ['SKD11 冲子料', 40, 6, '日立金属'], ['高速钢 W6Mo5Cr4V2', 30, 5, '河冶科技'], ['注塑机螺杆套件', 15, 3, '震雄集团']],
    devices: ['冲床 J23-125', '注塑机 HTL-250', '线切割 DK7740', '磨床 M7130'],
    faults: ['冲床滑块异响', '模具刃口崩裂', '注塑机射嘴堵塞', '线切割丝断频发', '液压过载报警'],
    regions: ['华南'],
    orderScale: 16,
  },
  4: { // 金汉隆：智能装备（发票数据已导入，这里只补客户/库存/售后配套）
    customers: ['东莞智能装备', '广州瑞锦机电', '佛山力诚炜兴', '惠州亿铭机械', '中山金鸿谊'],
    products: [['自动化生产线集成', 268000], ['工业机器人工作站', 186000], ['视觉检测设备 V-500', 96000], ['非标自动化设备', 128000]],
    materials: [['伺服电机 750W', 40, 6, '汇川技术'], ['直线模组 KK60', 30, 5, '上银科技'], ['视觉相机 500W', 20, 3, '海康机器人'], ['气动元件组合', 60, 8, '亚德客']],
    devices: ['六轴机器人 HS-R20', '视觉检测线 V-500', '自动锁螺丝机 ZL-30', '贴膜机 TM-60'],
    faults: ['机器人示教器通讯中断', '视觉系统误检率升高', '锁螺丝机滑牙报警', '贴膜张力不稳'],
    regions: ['华南'],
    orderScale: 5,
  },
}

// ---------------------------------------------------------------------------
// 订单状态机：节点按进度推进，延迟/风险与之联动
// ---------------------------------------------------------------------------

const NODES = [['计划', 5], ['设计', 20], ['采购', 35], ['生产', 55], ['质检', 75], ['包装', 90], ['发货', 100]]

function makeOrder (rnd, tid, profile, seq, date, customerId, customersLen) {
  const [product, price] = pick(rnd, profile.products)
  // 大件低频小批量，小件高频大批量
  const qty = price > 50000 ? 1 + Math.floor(rnd() * 6) : price > 5000 ? 8 + Math.floor(rnd() * 40) : 200 + Math.floor(rnd() * 1500)
  const amount = round2(qty * price)
  // 状态分布：约 12% 已完成、8% 已取消、其余在制（节点随机）
  const roll = rnd()
  let status = 'wip'; let nodeIdx = Math.floor(rnd() * NODES.length); let progress = NODES[nodeIdx][1]; let delay = 0; let risk = '绿色'
  if (roll < 0.12) { status = 'done'; nodeIdx = NODES.length - 1; progress = 100 }
  else if (roll < 0.20) { status = 'cancelled'; nodeIdx = Math.min(nodeIdx, 3); progress = NODES[nodeIdx][1]; risk = '红色' }
  else {
    // 在制订单：进度越深延迟概率越低；延迟带动风险升级
    if (rnd() < 0.35 - nodeIdx * 0.03) delay = 4 + Math.floor(rnd() * 72)
    if (delay > 48) risk = '红色'
    else if (delay > 0) risk = '黄色'
  }
  const dueDays = 20 + Math.floor(rnd() * 70)
  const due = new Date(date.getTime() + dueDays * 86_400_000)
  return {
    orderNo: `SO-${date.getFullYear()}-${String(10000 + seq).slice(1)}`,
    customerId, product, qty, price, amount,
    dueDate: day(due), status, node: NODES[nodeIdx][0], progress, delay,
    risk, ownerId: 1 + Math.floor(rnd() * 3), // 归属销售（种子用户池前几名）
  }
}

// ---------------------------------------------------------------------------
// 主入口
// ---------------------------------------------------------------------------

/**
 * 生成企业业务数据。
 * @param {object} cfg {months:生成月数(默认6), tenantId:指定租户(默认全部), seed, clear:先清后生成}
 */
export function generateBusinessData (cfg = {}) {
  const months = Math.max(1, Math.min(Number(cfg.months) || 6, 24))
  const seed = cfg.seed ?? 20260820
  const rnd = mulberry32(seed)
  const tenantIds = cfg.tenantId ? [Number(cfg.tenantId)] : db.prepare("SELECT id FROM business_tenant WHERE status = 'active'").all().map(r => r.id)

  // 1) 清除旧的生成数据（可跳过以增量叠加）
  let removed = 0
  if (cfg.clear !== false) {
    for (const [table, tenantCol] of [
      ['business_after_sale', true], ['business_finance', true], ['business_inventory', true],
      ['business_order', true], ['business_customer', true],
    ]) {
      const where = tenantCol ? "WHERE data_origin = 'generated' AND (tenant_id IS NULL OR tenant_id IS NOT NULL)" : "WHERE data_origin = 'generated'"
      const r = db.prepare(`DELETE FROM ${table} ${where}`).run()
      removed += r.changes
    }
  }

  const summary = { tenants: tenantIds.length, months, customers: 0, orders: 0, inventory: 0, finance: 0, afterSale: 0, removed }
  const today = new Date()
  const startMonth = new Date(today.getFullYear(), today.getMonth() - months + 1, 1)

  db.exec('BEGIN')
  try {
    const insCust = db.prepare(`INSERT INTO business_customer (tenant_id, name, tag, region, owner_id, data_origin) VALUES (?,?,?,?,?,?)`)
    const insOrder = db.prepare(`INSERT INTO business_order (tenant_id, order_no, customer_id, product, quantity, price, amount, due_date, status, current_node, progress, delay_hours, owner_id, risk_level, updated_at, data_origin) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`)
    const insInv = db.prepare(`INSERT INTO business_inventory (tenant_id, material, stock, safety_stock, consumption_rate, supplier, data_origin) VALUES (?,?,?,?,?,?,?)`)
    const insFin = db.prepare(`INSERT INTO business_finance (tenant_id, category, amount, month, note, data_origin) VALUES (?,?,?,?,?,?)`)
    const insAS = db.prepare(`INSERT INTO business_after_sale (tenant_id, customer_id, device, fault, status, engineer_id, created_at, data_origin) VALUES (?,?,?,?,?,?,?,?)`)

    for (const tid of tenantIds) {
      const profile = TENANT_PROFILE[tid]
      if (!profile) continue
      // 客户：全量入池（含活跃度分层）
      const custIds = []
      for (const [i, name] of profile.customers.entries()) {
        const tag = i < 2 ? '战略客户' : rnd() < 0.4 ? '潜力客户' : '普通客户'
        custIds.push(Number(insCust.run(tid, name, tag, pick(rnd, profile.regions), 1 + Math.floor(rnd() * 3), ORIGIN).lastInsertRowid))
        summary.customers++
      }

      // 订单：按月生成，月度有淡旺季（Q1 低、Q3-Q4 高），订单额派生财务
      let seq = 0
      const monthAmounts = {}
      for (let m = 0; m < months; m++) {
        const monthDate = new Date(startMonth.getFullYear(), startMonth.getMonth() + m, 1)
        const season = [0.75, 1.0, 1.15, 1.1, 1.2, 1.3, 1.25, 1.3, 1.4, 1.45, 1.35, 0.9][monthDate.getMonth()]
        const count = Math.max(1, Math.round(profile.orderScale * season * (0.8 + rnd() * 0.4)))
        let monthTotal = 0
        for (let i = 0; i < count; i++) {
          seq++
          // 订单日期随机落在月内
          const d = new Date(monthDate.getFullYear(), monthDate.getMonth(), 1 + Math.floor(rnd() * 28))
          if (d > today) continue
          const o = makeOrder(rnd, tid, profile, seq, d, pick(rnd, custIds), custIds.length)
          insOrder.run(tid, o.orderNo, o.customerId, o.product, o.qty, o.price, o.amount,
            o.dueDate, o.status, o.node, o.progress, o.delay, o.ownerId, o.risk, d.toISOString(), ORIGIN)
          summary.orders++
          if (o.status !== 'cancelled') monthTotal += o.amount
        }
        // 财务：月度收入 ≈ 当月订单额（done 订单即时确认、wip 部分挂应收）
        if (monthTotal > 0) {
          const key = `${monthDate.getFullYear()}-${String(monthDate.getMonth() + 1).padStart(2, '0')}`
          monthAmounts[key] = monthTotal
        }
      }
      for (const [month, total] of Object.entries(monthAmounts)) {
        const income = round2(total * (0.85 + rnd() * 0.1))
        const receivable = round2(total - income)
        insFin.run(tid, 'income', income, month, '销售回款（自动生成）', ORIGIN)
        insFin.run(tid, 'receivable', receivable, month, '应收账款（自动生成）', ORIGIN)
        insFin.run(tid, 'expense', round2(income * (0.62 + rnd() * 0.12)), month, '生产成本与费用（自动生成）', ORIGIN)
        summary.finance += 3
      }

      // 库存：物料池 + 消耗率，按概率出现低于安全线的告警项
      for (const [material, safety, rate, supplier] of profile.materials) {
        const lowRatio = rnd() < 0.25 // 四分之一物料低于安全库存（演示告警）
        const stock = lowRatio ? Math.round(safety * (0.4 + rnd() * 0.5)) : Math.round(safety * (1.2 + rnd() * 1.8))
        insInv.run(tid, material, stock, safety, rate, supplier, ORIGIN)
        summary.inventory++
      }

      // 售后：工单密度 ≈ 客户数 × 设备安装基数；状态随时间分布
      const asCount = Math.max(2, Math.round(profile.customers.length * (0.8 + rnd() * 0.7)))
      for (let i = 0; i < asCount; i++) {
        const created = new Date(today.getTime() - Math.floor(rnd() * months * 30) * 86_400_000)
        if (created < startMonth) continue
        const roll = rnd()
        const status = roll < 0.3 ? 'open' : roll < 0.65 ? 'processing' : roll < 0.9 ? 'resolved' : 'closed'
        insAS.run(tid, pick(rnd, custIds), pick(rnd, profile.devices), pick(rnd, profile.faults), status,
          status === 'open' ? null : 1 + Math.floor(rnd() * 3), created.toISOString(), ORIGIN)
        summary.afterSale++
      }
    }
    db.exec('COMMIT')
  } catch (e) {
    db.exec('ROLLBACK')
    throw e
  }
  return summary
}

/** 清除全部生成业务数据 */
export function clearGeneratedBusinessData (tenantId = null) {
  const t = tenantId ? 'AND tenant_id = ?' : ''
  const p = tenantId ? [Number(tenantId)] : []
  let removed = 0
  for (const table of ['business_after_sale', 'business_finance', 'business_inventory', 'business_order', 'business_customer']) {
    const r = db.prepare(`DELETE FROM ${table} WHERE data_origin = 'generated' ${t}`).run(...p)
    removed += r.changes
  }
  return removed
}

/** 生成数据统计（设置页展示用） */
export function generatedBusinessStats (tenantId = null) {
  const t = tenantId ? 'AND tenant_id = ?' : ''
  const p = tenantId ? [Number(tenantId)] : []
  const one = (sql) => db.prepare(sql).get(...p).c
  return {
    customers: one(`SELECT COUNT(*) c FROM business_customer WHERE data_origin='generated' ${t}`),
    orders: one(`SELECT COUNT(*) c FROM business_order WHERE data_origin='generated' ${t}`),
    inventory: one(`SELECT COUNT(*) c FROM business_inventory WHERE data_origin='generated' ${t}`),
    finance: one(`SELECT COUNT(*) c FROM business_finance WHERE data_origin='generated' ${t}`),
    afterSale: one(`SELECT COUNT(*) c FROM business_after_sale WHERE data_origin='generated' ${t}`),
    totalAmount: one(`SELECT ROUND(SUM(amount)) c FROM business_order WHERE data_origin='generated' ${t}`) ?? 0,
  }
}
