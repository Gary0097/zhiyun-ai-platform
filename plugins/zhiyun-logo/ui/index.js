(function () {
  var Q = window.QwenPaw;
  var pluginId = "zhiyun-logo";
  if (!Q || !Q.slot || !Q.host || !Q.host.React) return;
  var React = Q.host.React;
  var antd = Q.host.antd;
  var h = React.createElement;
  var fallback = "/api/frontend_plugin/zhiyun-logo/files/assets/default-logo.png";

  function token() {
    try { return (Q.host.getApiToken && Q.host.getApiToken()) || window.localStorage.getItem("zhiyun_token") || ""; } catch (e) { return ""; }
  }
  function authHeaders(extra) {
    var headers = { "Content-Type": "application/json" };
    var t = token();
    if (t) headers["Authorization"] = "Bearer " + t;
    if (extra) for (var k in extra) headers[k] = extra[k];
    return headers;
  }
  function getApiUrl(path) { return Q.host.getApiUrl ? Q.host.getApiUrl(path) : path; }

  function install(logo) {
    Q.slot.replace(pluginId, "header.logo", function () {
      return React.createElement("img", {
        src: logo || fallback,
        alt: "AI-OS",
        style: { height: 32, width: "auto", maxWidth: 190, objectFit: "contain" }
      });
    }, { id: "zhiyun-configurable-logo" });
  }

  function LogoPage() {
    var configState = React.useState({ logo: "", source: "", preview: "" });
    var config = configState[0];
    var setConfig = configState[1];
    var loadingState = React.useState(true);
    var loading = loadingState[0];
    var setLoading = loadingState[1];
    var savingState = React.useState(false);
    var saving = savingState[0];
    var setSaving = savingState[1];
    var errorState = React.useState("");
    var error = errorState[0];
    var setError = errorState[1];

    function loadConfig() {
      setLoading(true); setError("");
      Q.host.fetch("/zhiyun-logo/config", { headers: authHeaders() })
        .then(function (response) {
          if (!response.ok) throw new Error("HTTP " + response.status);
          return response.json();
        })
        .then(function (body) {
          setConfig({ logo: body.logo || "", source: body.source || "", preview: body.logo || "" });
          if (body.logo) install(body.logo);
        })
        .catch(function (err) { setError("加载 Logo 配置失败：" + (err && err.message ? err.message : String(err))); })
        .finally(function () { setLoading(false); });
    }

    function onFile(event) {
      var file = event.target.files && event.target.files[0];
      if (!file) return;
      if (file.size > 2 * 1024 * 1024) { setError("Logo 文件不能超过 2 MB"); return; }
      var reader = new FileReader();
      reader.onload = function () {
        setConfig(function (prev) { return Object.assign({}, prev, { preview: String(reader.result || "") }); });
        setError("");
      };
      reader.onerror = function () { setError("读取文件失败"); };
      reader.readAsDataURL(file);
    }

    function save() {
      if (!config.preview || config.preview.indexOf("data:image/") !== 0) { setError("请先选择一张 PNG/JPEG/SVG/WebP 图片"); return; }
      setSaving(true); setError("");
      Q.host.fetch("/zhiyun-logo/config", {
        method: "PUT",
        headers: authHeaders(),
        body: JSON.stringify({ logo: config.preview })
      })
        .then(function (response) {
          if (!response.ok) return response.text().then(function (t) { throw new Error("HTTP " + response.status + (t && t.trim() ? ": " + t.trim() : "")); });
          return response.json();
        })
        .then(function (body) {
          setConfig(function (prev) { return Object.assign({}, prev, { logo: body.logo || prev.logo, source: body.source || prev.source, preview: body.logo || prev.preview }); });
          if (body.logo) install(body.logo);
        })
        .catch(function (err) { setError("保存 Logo 失败：" + (err && err.message ? err.message : String(err))); })
        .finally(function () { setSaving(false); });
    }

    function reset() {
      setSaving(true); setError("");
      Q.host.fetch("/zhiyun-logo/reset", { method: "POST", headers: authHeaders() })
        .then(function (response) {
          if (!response.ok) throw new Error("HTTP " + response.status);
          return response.json();
        })
        .then(function () { loadConfig(); })
        .catch(function (err) { setError("重置 Logo 失败：" + (err && err.message ? err.message : String(err))); })
        .finally(function () { setSaving(false); });
    }

    React.useEffect(loadConfig, []);

    return h("div", { style: { padding: 28, height: "100%", overflow: "auto", background: "#f7f8fa" } },
      h("div", { style: { maxWidth: 900, margin: "0 auto" } },
        h("h2", { style: { marginBottom: 4 } }, "品牌 Logo 配置"),
        h("p", { style: { color: "#667085", marginTop: 0 } }, "上传 Logo 将替换顶部导航栏的品牌标识，支持 PNG/JPEG/SVG/WebP，最大 2 MB。"),
        error ? h(antd.Alert, { type: "error", showIcon: true, message: error, style: { marginBottom: 16 } }) : null,
        h(antd.Card, { loading: loading, style: { marginBottom: 16 } },
          h("div", { style: { textAlign: "center", padding: "16px 0" } },
            h("img", { src: config.preview || fallback, alt: "Logo 预览", style: { maxHeight: 80, maxWidth: 260, objectFit: "contain" } })),
          h("div", { style: { display: "flex", flexDirection: "column", gap: 12 } },
            h("input", { type: "file", accept: "image/png,image/jpeg,image/svg+xml,image/webp", onChange: onFile, style: { padding: 8, border: "1px solid #e3e8ef", borderRadius: 8 } }),
            h("div", { style: { display: "flex", gap: 8 } },
              h(antd.Button, { type: "primary", loading: saving, onClick: save, disabled: !config.preview }, "保存配置"),
              h(antd.Button, { loading: saving, onClick: reset }, "恢复默认")),
            config.source ? h("div", { style: { fontSize: 12, color: "#667085" } }, "当前来源：" + config.source) : null
          )
        ),
        h(antd.Alert, { type: "info", showIcon: true, message: "说明", description: "Logo 会以 base64 保存到工作区 branding 目录，位图与 SVG 均可；仅系统管理员或已授权用户可修改。", style: { marginBottom: 16 } })
      )
    );
  }

  install(fallback);
  Q.host.fetch(getApiUrl("/zhiyun-logo/config"), { headers: authHeaders() })
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(function (config) { install(config.logo); })
    .catch(function (error) { console.warn("[zhiyun-logo] using packaged logo:", error.message); });

  if (Q.registerRoutes) {
    Q.registerRoutes("zhiyun-logo", [{ path: "/apps/zhiyun-logo", component: LogoPage, label: "品牌 Logo 配置", icon: "💠", priority: 90 }]);
  }
})();