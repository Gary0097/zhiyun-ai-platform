(function () {
  var runtime = window.QwenPaw;
  var pluginId = "zhiyun-brand";
  if (!runtime || !runtime.chat) {
    console.error("[zhiyun-brand] QwenPaw Chat SDK is unavailable");
    return;
  }

  var fallbackLogo = "/api/frontend_plugin/zhiyun-brand/files/ui/logo.svg";
  var host = runtime.host;
  var React = host && host.React;

  function applyBrand(brand) {
    var logo = brand.logo || fallbackLogo;
    var name = brand.name || "智造云 AI-OS";
    var subtitle = brand.subtitle || "企业 AI 操作系统";
    var primaryColor = brand.primaryColor || "#1677ff";
    runtime.chat.leftHeader.set(pluginId, { logo: logo, title: name });
    runtime.chat.theme.set(pluginId, { colorPrimary: primaryColor });
    runtime.chat.welcome.set(pluginId, {
      greeting: "你好，我是" + name,
      description: subtitle + "。可以对话，也可以调用企业应用完成真实任务。",
      avatar: logo,
      nick: name,
      prompts: [
        "检查企业平台连接状态",
        "查看我正在进行的任务",
        "上传文件并查询企业知识",
        "创建一个售前报价任务"
      ],
    });
    runtime.chat.sender.set(pluginId, {
      placeholder: "描述目标、上传文件，或直接启动企业应用",
      disclaimer: "AI 结果需结合企业数据与业务规则核验；高风险操作将受到控制。",
    });
    if (runtime.slot && React) {
      runtime.slot.replace(pluginId, "header.logo", function () {
        return React.createElement("img", {
          src: logo,
          alt: name,
          style: { height: 30, maxWidth: 160, objectFit: "contain" },
        });
      }, { id: "zhiyun-global-logo" });
    }
    document.title = name;
  }

  applyBrand({});
  if (host && host.getApiUrl) {
    fetch(host.getApiUrl("/zhiyun-brand/config"), {
      headers: host.getApiToken && host.getApiToken()
        ? { Authorization: "Bearer " + host.getApiToken() }
        : {},
    })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(applyBrand)
      .catch(function (err) {
        console.warn("[zhiyun-brand] using fallback brand:", err.message);
      });
  }
})();
