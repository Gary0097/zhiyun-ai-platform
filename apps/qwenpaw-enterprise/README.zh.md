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
qwenpaw.lock.json       上游版本锁
```

## 安装品牌插件

先按 QwenPaw 官方方式安装并初始化 2.1.0，然后从本目录安装插件：

```sh
qwenpaw plugin install ./plugins/zhiyun-brand
qwenpaw app
```

插件使用 QwenPaw 官方 Chat 扩展接口修改产品标题、Logo、主色、欢迎语和建议问题，不修改上游 Console 源码。Phase Q1 将把当前默认配置替换为管理员品牌接口，并增加上传、持久化和权限校验。

## 验证

```sh
node scripts/verify-q0.mjs
```

验证包括上游版本锁、插件清单、品牌扩展接口、敏感信息和禁止新增 DSH 依赖。

