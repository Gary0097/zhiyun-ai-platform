---
name: zhibang-erp
version: 1.0.0
description: "智邦国际ERP数据导入与查询：通过智邦开放平台 OpenApi 快速把客户等业务数据写入智邦ERP（支持 Excel/CSV 批量导入、自动去重），也支持客户查询、详情、调用任意已文档化接口。当用户要求\"导入ERP\"、\"数据写入智邦ERP\"、\"ERP批量导入客户\"、\"查ERP客户\"时使用。内置金汉隆内网ERP地址与账号。"
metadata:
  builtin_skill_version: "1.0.0"
  qwenpaw:
    emoji: "🏢"
    requires:
      bins: ["python3"]
---

# zhibang-erp（智邦国际 ERP 数据导入）

内网智邦 ERP（金汉隆）：`http://192.167.30.5:6088`，凭据在本技能目录 `config.json`（admin / 88888888）。

## 命令速查

CLI：`python3 skills/zhibang-erp/erp.py <命令>`（在本智能体工作区根目录执行；若当前目录不是工作区，先定位 `zhibang-erp/erp.py`）

| 想做什么 | 命令 |
|---|---|
| 测试连通/登录 | `erp.py login` |
| 搜客户 | `erp.py list-customers --name 关键词` |
| 客户详情 | `erp.py customer-detail --ord 190` |
| **单个新增客户** | `erp.py add-customer --name 公司名 --person 联系人 --mobile 138... --address 地址 [--intro 备注] [--sort "终端客户,潜在客户"]` |
| **Excel/CSV 批量导入客户** | `erp.py import-customers 文件.xlsx [--sheet 表名] [--dry-run]` |
| 调用任意开放接口 | `erp.py call <接口路径> '<datas JSON>'` |

## 批量导入格式

Excel/CSV 需含表头，自动识别以下列名（顺序无关，缺联系人会自动填"待补充"）：

```
客户名称 | 联系人 | 手机 | 地址 | 备注
```

金汉隆《企业客户管理表》可直接导入（客户名称/联系人/联系电话/详细地址 列自动映射）。

- 自动按客户名称去重：已存在的跳过并在结果里标注
- `--dry-run` 只打印将要导入的行，不写入
- 分类默认「终端客户/潜在客户」，可用 `--sort "终端客户,潜在客户"` 覆盖（父,子 路径格式）
- 仅依赖 Python 标准库；xlsx 直接解析，无需安装第三方包

## v3 原生写入（已验证真实落库）

- 端点：`POST /webapi/v3/sales/customer/add`
- 格式：**直传 JSON 字段** + `token` 放**请求体**（如 `{"token":"...","sort2":1,"name":"公司","sort":"终端客户","sort1":"潜在客户","person_name":"联系人"}`）
- sort/sort1 传**分类名称**（不是数字路径）
- `--cate 施伟超` 可指定销售人员（客户直接进他的列表）
- ⚠️ ov1 手机端点（add.asp?__sys_dosave）保存会丢数据，勿用

## 对接要点（踩坑记录）

1. 登录：`POST /webapi/v3/ov1/login`，用户名/密码加 `txt:` 前缀（明文），`serialnum` 随机
2. Token 放**请求体**（v3 直传接口用 `token` 字段；旧式 datas 数组接口用 `{"session": "...", "datas": [{"id":"字段","val":"值"}]}`），不是 Header
3. 新增类接口两步走：先 POST 普通端点拿表单对象（取 `value` 作为 ord），再按 `tools` 里的 `__sys_dosave` 地址提交
4. 树形字段（客户分类等）传 `"父,子"` 路径，如 `"终端客户,潜在客户"`
5. 全部接口文档：`http://192.167.30.5:6088/sysn/view/OpenApi/help.ashx`（219 个接口：客户/合同/采购/库存/生产/财务）
6. 连接超时/拒绝时脚本会明确报网络不可达——如实转告用户，勿编造数据

## 典型用法

- "把这批客户 Excel 导入 ERP" → `import-customers 文件.xlsx --dry-run` 预览 → 用户确认后去掉 `--dry-run` 执行 → 汇报成功/跳过/失败
- "查一下 ERP 里有没有 XX 公司" → `list-customers --name XX`
- "给 ERP 加个客户" → 复述关键字段请用户确认 → `add-customer ...`
