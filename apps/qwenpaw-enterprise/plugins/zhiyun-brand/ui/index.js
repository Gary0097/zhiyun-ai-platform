(function () {
  var runtime = window.QwenPaw;
  var pluginId = "zhiyun-brand";
  if (!runtime || !runtime.chat) {
    console.error("[zhiyun-brand] QwenPaw Chat SDK is unavailable");
    return;
  }

  var logo = "/api/frontend_plugin/zhiyun-brand/files/ui/logo.svg";
  runtime.chat.leftHeader.set(pluginId, {
    logo: logo,
    title: "智造云 AI-OS",
  });
  runtime.chat.theme.set(pluginId, { colorPrimary: "#1677ff" });
  runtime.chat.welcome.set(pluginId, {
    greeting: "你好，我是智造云企业 AI 助手",
    description: "可以对话，也可以调用企业应用完成真实任务。",
    avatar: logo,
    nick: "智造云 AI",
    prompts: [
      "查看我正在进行的任务",
      "上传文件并查询企业知识",
      "创建一个售前报价任务",
      "打开 AI-OS 运行监视器"
    ],
  });
  runtime.chat.sender.set(pluginId, {
    placeholder: "描述目标、上传文件，或直接启动企业应用",
    disclaimer: "AI 结果需结合企业数据与业务规则核验；高风险操作将受到控制。",
  });
})();
