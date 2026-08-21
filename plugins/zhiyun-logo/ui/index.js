(function () {
  var Q = window.QwenPaw;
  var pluginId = "zhiyun-logo";
  if (!Q || !Q.slot || !Q.host || !Q.host.React) return;
  var React = Q.host.React;
  var fallback = "/api/frontend_plugin/zhiyun-logo/files/assets/default-logo.png";

  function install(logo) {
    Q.slot.replace(pluginId, "header.logo", function () {
      return React.createElement("img", {
        src: logo || fallback,
        alt: "AI-OS",
        style: { height: 32, width: "auto", maxWidth: 190, objectFit: "contain" }
      });
    }, { id: "zhiyun-configurable-logo" });
  }

  install(fallback);
  var token = Q.host.getApiToken && Q.host.getApiToken();
  fetch(Q.host.getApiUrl("/zhiyun-logo/config"), {
    headers: token ? { Authorization: "Bearer " + token } : {}
  })
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(function (config) { install(config.logo); })
    .catch(function (error) {
      console.warn("[zhiyun-logo] using packaged logo:", error.message);
    });
})();
