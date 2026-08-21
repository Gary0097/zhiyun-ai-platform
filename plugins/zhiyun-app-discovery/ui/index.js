(function () {
  var Q = window.QwenPaw;
  if (!Q || !Q.host || !Q.host.React || !Q.registerRoutes) return;
  var React = Q.host.React;
  var antd = Q.host.antd;
  var h = React.createElement;

  function apiSearch(query) {
    return Q.host.fetch("/zhiyun-app-discovery/search?q=" + encodeURIComponent(query) + "&limit=12")
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      });
  }

  function statusText(status) {
    return status === "installed" ? "已安装" : "可安装";
  }

  function AppDiscovery() {
    var queryState = React.useState("");
    var query = queryState[0];
    var setQuery = queryState[1];
    var resultState = React.useState([]);
    var results = resultState[0];
    var setResults = resultState[1];
    var loadingState = React.useState(false);
    var loading = loadingState[0];
    var setLoading = loadingState[1];
    var errorState = React.useState("");
    var error = errorState[0];
    var setError = errorState[1];

    function run(value) {
      var text = String(value || "").trim();
      if (!text) {
        setResults([]);
        return;
      }
      setLoading(true);
      setError("");
      apiSearch(text)
        .then(function (data) { setResults(data.results || []); })
        .catch(function () { setError("应用索引暂时不可用，请检查插件状态。"); })
        .finally(function () { setLoading(false); });
    }

    return h("div", { style: { padding: 28, height: "100%", overflow: "auto", background: "#f7f8fa" } },
      h("div", { style: { maxWidth: 980, margin: "0 auto" } },
        h("h2", { style: { marginBottom: 6 } }, "应用搜索"),
        h("p", { style: { color: "#667085", marginTop: 0 } }, "描述你要完成的事情，系统只从真实应用目录中推荐。"),
        h(antd.Input.Search, {
          value: query,
          allowClear: true,
          enterButton: "搜索",
          size: "large",
          loading: loading,
          placeholder: "例如：哪个应用能分析订单交付风险？",
          onChange: function (event) { setQuery(event.target.value); },
          onSearch: run
        }),
        h("div", { style: { marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" } },
          ["交付风险", "合同不一致", "报销审核", "供应商补货", "销售人员业绩"].map(function (sample) {
            return h(antd.Tag, {
              key: sample,
              style: { cursor: "pointer", padding: "4px 10px" },
              onClick: function () { setQuery(sample); run(sample); }
            }, sample);
          })
        ),
        error ? h(antd.Alert, { type: "error", message: error, showIcon: true, style: { marginTop: 20 } }) : null,
        !loading && query && !error && results.length === 0
          ? h(antd.Empty, { description: "真实应用目录中暂无匹配能力", style: { marginTop: 48 } })
          : null,
        h("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(290px,1fr))", gap: 14, marginTop: 22 } },
          results.map(function (item) {
            var match = item.matched_capability || {};
            return h(antd.Card, { key: item.app_id, size: "small", title: item.name, extra: h(antd.Tag, { color: item.install_status === "installed" ? "green" : "blue" }, statusText(item.install_status)) },
              h("div", { style: { fontWeight: 600, marginBottom: 8 } }, match.capability_name || "匹配应用"),
              h("div", { style: { color: "#667085", minHeight: 42 } }, match.reason || "能力索引匹配"),
              h("div", { style: { display: "flex", gap: 8, marginTop: 14 } },
                item.install_status === "installed"
                  ? h(antd.Button, { type: "primary", href: item.route }, "打开")
                  : h(antd.Button, { type: "primary", href: item.repository_url, target: "_blank" }, "查看项目"),
                h(antd.Tag, null, (item.platforms || []).join(" / "))
              )
            );
          })
        )
      )
    );
  }

  Q.registerRoutes("zhiyun-app-discovery", [{
    path: "/apps/app-discovery",
    component: AppDiscovery,
    label: "应用搜索",
    icon: "🔎",
    priority: 80
  }]);
})();
