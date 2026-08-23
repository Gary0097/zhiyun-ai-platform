(function () {
  var Q = window.QwenPaw;
  if (!Q || !Q.host || !Q.host.React || !Q.registerRoutes) return;
  var React = Q.host.React;
  var antd = Q.host.antd;
  var h = React.createElement;

  function getJson(path) {
    return Q.host.fetch(path).then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    });
  }

  function statusLabel(status) {
    return ({ installed: "已安装", planned: "未开发", in_progress: "开发中", testing: "测试中", completed: "已完成" })[status] || status;
  }

  function statusColor(status) {
    return ({ installed: "green", planned: "default", in_progress: "blue", testing: "orange", completed: "green" })[status] || "default";
  }

  function MyApps(props) {
    var apps = (props.apps || []).filter(function (item) { return item.install_status === "installed"; });
    return h("div", null,
      h(antd.Alert, { type: "info", showIcon: true, message: "这里只展示当前真实安装的应用与系统组件。", style: { marginBottom: 18 } }),
      h("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(280px,1fr))", gap: 14 } },
        apps.map(function (item) {
          return h(antd.Card, { key: item.app_id, title: item.name, extra: h(antd.Tag, { color: "green" }, "已安装") },
            h("p", { style: { color: "#667085", minHeight: 42 } }, item.category === "system" ? "AI-OS 系统组件" : "可运行的业务应用"),
            h("div", { style: { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" } },
              h(antd.Tag, null, "v" + (item.version || "-")),
              h(antd.Tag, { color: item.health === "available" ? "green" : "orange" }, item.health === "available" ? "运行可用" : item.health),
              item.route ? h(antd.Button, { type: "primary", size: "small", href: item.route }, "打开") : h(antd.Button, { size: "small", disabled: true }, "后台服务")
            )
          );
        })
      )
    );
  }

  function AppSearch() {
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
      if (!text) { setResults([]); return; }
      setLoading(true); setError("");
      getJson("/zhiyun-app-discovery/search?q=" + encodeURIComponent(text) + "&limit=12")
        .then(function (data) { setResults(data.results || []); })
        .catch(function () { setError("应用索引暂时不可用，请检查插件状态。"); })
        .finally(function () { setLoading(false); });
    }

    return h("div", null,
      h("p", { style: { color: "#667085" } }, "搜索已安装应用和规划能力；未开发功能会明确标识，不能打开。"),
      h(antd.Input.Search, { value: query, allowClear: true, enterButton: "搜索", size: "large", loading: loading, placeholder: "例如：哪个应用能分析订单交付风险？", onChange: function (event) { setQuery(event.target.value); }, onSearch: run }),
      h("div", { style: { marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" } },
        ["交付风险", "合同不一致", "报销审核", "供应商补货", "销售人员业绩"].map(function (sample) {
          return h(antd.Tag, { key: sample, style: { cursor: "pointer", padding: "4px 10px" }, onClick: function () { setQuery(sample); run(sample); } }, sample);
        })
      ),
      error ? h(antd.Alert, { type: "error", message: error, showIcon: true, style: { marginTop: 20 } }) : null,
      !loading && query && !error && results.length === 0 ? h(antd.Empty, { description: "目录中暂无匹配能力", style: { marginTop: 48 } }) : null,
      h("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(290px,1fr))", gap: 14, marginTop: 22 } },
        results.map(function (item) {
          var match = item.matched_capability || {};
          var installed = item.install_status === "installed";
          return h(antd.Card, { key: item.app_id, size: "small", title: item.name, extra: h(antd.Tag, { color: statusColor(item.install_status) }, statusLabel(item.install_status)) },
            h("div", { style: { fontWeight: 600, marginBottom: 8 } }, match.capability_name || "匹配应用"),
            h("div", { style: { color: "#667085", minHeight: 42 } }, match.reason || "能力索引匹配"),
            h("div", { style: { display: "flex", gap: 8, marginTop: 14 } },
              installed && item.route ? h(antd.Button, { type: "primary", href: item.route }, "打开") : h(antd.Button, { disabled: true }, "尚未开发"),
              h(antd.Tag, null, (item.platforms || []).join(" / "))
            )
          );
        })
      )
    );
  }

  function ProjectProgress(props) {
    var progress = props.progress;
    if (!progress) return h(antd.Skeleton, { active: true });
    var summary = progress.summary || {};
    var names = {};
    (props.apps || []).forEach(function (item) { names[item.app_id] = item.name; });
    var columns = [
      { title: "序号", dataIndex: "id", width: 70 },
      { title: "PRD 功能", dataIndex: "name", width: 230 },
      { title: "承载应用", dataIndex: "app_id", width: 180, render: function (value) { return names[value] || value; } },
      { title: "状态", dataIndex: "status", width: 100, render: function (value) { return h(antd.Tag, { color: statusColor(value) }, statusLabel(value)); } },
      { title: "进度", dataIndex: "progress", width: 180, render: function (value) { return h(antd.Progress, { percent: value, size: "small" }); } },
      { title: "真实情况", dataIndex: "note" }
    ];
    return h("div", null,
      h(antd.Alert, { type: "warning", showIcon: true, message: "进度按可验收功能统计，不把规划目录视为已开发。", style: { marginBottom: 18 } }),
      h(antd.Row, { gutter: [12, 12], style: { marginBottom: 18 } },
        [["功能总数", summary.total], ["开发中", summary.in_progress], ["已完成", summary.completed], ["总体进度", (summary.overall_progress || 0) + "%"]].map(function (item) {
          return h(antd.Col, { xs: 12, md: 6, key: item[0] }, h(antd.Card, { size: "small" }, h(antd.Statistic, { title: item[0], value: item[1] })));
        })
      ),
      h(antd.Table, { rowKey: "id", size: "small", scroll: { x: 1050 }, pagination: { pageSize: 10 }, columns: columns, dataSource: progress.features || [] })
    );
  }

  function AppCenter() {
    var catalogState = React.useState([]);
    var apps = catalogState[0];
    var setApps = catalogState[1];
    var progressState = React.useState(null);
    var progress = progressState[0];
    var setProgress = progressState[1];
    var errorState = React.useState("");
    var error = errorState[0];
    var setError = errorState[1];
    React.useEffect(function () {
      Promise.all([getJson("/zhiyun-app-discovery/catalog"), getJson("/zhiyun-app-discovery/progress")])
        .then(function (values) { setApps(values[0].apps || []); setProgress(values[1]); })
        .catch(function () { setError("应用与进度数据加载失败，请检查插件状态。"); });
    }, []);
    var items = [
      { key: "mine", label: "我的应用", children: h(MyApps, { apps: apps }) },
      { key: "search", label: "应用搜索", children: h(AppSearch) },
      { key: "progress", label: "项目进度", children: h(ProjectProgress, { apps: apps, progress: progress }) }
    ];
    return h("div", { style: { padding: 28, height: "100%", overflow: "auto", background: "#f7f8fa" } },
      h("div", { style: { maxWidth: 1280, margin: "0 auto" } },
        h("h2", { style: { marginBottom: 4 } }, "应用与项目中心"),
        h("p", { style: { color: "#667085", marginTop: 0 } }, "真实应用入口、能力检索和 31 项 PRD 交付进度。"),
        h(antd.Collapse, { style: { marginBottom: 16 }, items: [{ key: "guide", label: "功能引导与使用说明", children: h("div", null, h("p", null, "功能介绍：按中文名称、业务功能或自然语言需求查找真实已登记应用，并区分已安装与功能已交付。"), h("ol", null, h("li", null, "在“我的应用”输入要解决的业务问题。"), h("li", null, "查看匹配功能、原因、健康和安装状态。"), h("li", null, "只有已验收能力才会显示可用；计划中功能不会被虚构为可用。"))) }] }),
        error ? h(antd.Alert, { type: "error", message: error, showIcon: true, style: { marginBottom: 16 } }) : null,
        h(antd.Tabs, { defaultActiveKey: "mine", items: items })
      )
    );
  }

  Q.registerRoutes("zhiyun-app-discovery", [{ path: "/apps/app-discovery", component: AppCenter, label: "应用与进度", icon: "🧭", priority: 80 }]);
})();
