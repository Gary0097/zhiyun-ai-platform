# 智造云 QwenPaw 企业扩展

本目录承载 AI-OS V4.0 对 QwenPaw 的企业扩展，不复制 QwenPaw 核心运行时。

## 基线

- 上游：`agentscope-ai/QwenPaw`
- 分支：`release/v2.1.0`
- 锁定提交：见 `qwenpaw.lock.json`
- 许可证：Apache-2.0，部署和分发时必须保留上游许可证与声明

## 目录

```text
plugins/zhiyun-brand/   品牌扩展最小样例
scripts/verify-q0.mjs   Phase Q0 静态契约验证
scripts/verify-q1.mjs   Phase Q1 集成契约验证
scripts/start-dev.mjs   QwenPaw + 企业服务一键开发启动
qwenpaw.lock.json       上游版本锁
```

## 一键开发启动

要求 Python 3.11–3.13、Node.js 24+，并先安装锁定版本：

```sh
pip install qwenpaw==2.1.0
node scripts/start-dev.mjs
```

启动器会校验 QwenPaw 版本、重新安装当前品牌插件，再同时启动 QwenPaw 8088 和企业服务 8390。只检查环境可执行：

```sh
node scripts/start-dev.mjs --check
```

## 单独安装品牌插件

先按 QwenPaw 官方方式安装并初始化 2.1.0，然后从本目录安装插件：

```sh
qwenpaw plugin install ./plugins/zhiyun-brand
qwenpaw app
```

插件使用 QwenPaw 官方 Chat/Slot 扩展接口修改产品标题、全局 Logo、主色、欢迎语和建议问题，不修改上游 Console 源码。品牌配置继续由企业后台“品牌与入口”管理，QwenPaw 通过只读桥接动态同步。插件还提供首个只读 Tool：`enterprise_platform_status`。

## 验证

```sh
node scripts/verify-q0.mjs
node scripts/verify-q1.mjs
```

验证包括上游版本锁、插件清单、品牌扩展接口、敏感信息和禁止新增 DSH 依赖。
