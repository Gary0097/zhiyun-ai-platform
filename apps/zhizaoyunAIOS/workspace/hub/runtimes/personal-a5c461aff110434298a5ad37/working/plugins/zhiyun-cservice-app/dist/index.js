/* 智能客服与客户运营 插件入口（Hub 模式不支持插件加载时的元数据占位，
 * 实际注入由 console 品牌补丁 /assets/cservice-app-entry.js 完成） */
export function activate(ctx) {
  ctx.log.info('[zhiyun-cservice-app] plugin activate (entry via brand patch)')
}
