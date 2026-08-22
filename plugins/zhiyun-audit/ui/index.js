(function () {
  var Q = window.QwenPaw;
  if (!Q || !Q.host || !Q.host.React || !Q.registerRoutes) return;
  var React = Q.host.React;
  var antd = Q.host.antd;
  var h = React.createElement;

  function AuditViewer() {
    var recordsState = React.useState([]);
    var records = recordsState[0];
    var setRecords = recordsState[1];
    var statusState = React.useState("");
    var status = statusState[0];
    var setStatus = statusState[1];
    var loadingState = React.useState(false);
    var loading = loadingState[0];
    var setLoading = loadingState[1];
    var errorState = React.useState("");
    var error = errorState[0];
    var setError = errorState[1];

    function load() {
      setLoading(true); setError("");
      var query = status ? "?status=" + encodeURIComponent(status) : "";
      Q.host.fetch("/zhiyun-audit/events" + query).then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      }).then(function (body) { setRecords(body.events || []); })
        .catch(function (reason) { setError(reason.message || "审计记录加载失败"); })
        .finally(function () { setLoading(false); });
    }

    React.useEffect(load, [status]);
    var statusColors = { success: "green", failed: "red", blocked: "orange" };
    var columns = [
      { title: "时间", dataIndex: "created_at", width: 210 },
      { title: "Tool", dataIndex: "tool_name", width: 180 },
      { title: "状态", dataIndex: "status", width: 100, render: function (value) { return h(antd.Tag, { color: statusColors[value] || "default" }, value); } },
      { title: "耗时(ms)", dataIndex: "duration_ms", width: 110 },
      { title: "Agent", dataIndex: "agent_id", width: 140 },
      { title: "Session", dataIndex: "session_id", width: 180, ellipsis: true },
      { title: "Trace", dataIndex: "trace_id", width: 240, ellipsis: true },
      { title: "错误类型", dataIndex: "error_type", width: 190, ellipsis: true }
    ];

    return h("div", { style: { padding: 28, height: "100%", overflow: "auto", background: "#f7f8fa" } },
      h("div", { style: { maxWidth: 1400, margin: "0 auto" } },
        h("div", { style: { display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center" } },
          h("div", null,
            h("h2", { style: { marginBottom: 4 } }, "Tool 调用审计"),
            h("p", { style: { color: "#667085", marginTop: 0 } }, "仅展示脱敏后的执行元数据，不展示 Tool 输入、密钥或模型推理。")),
          h(antd.Button, { onClick: load, loading: loading }, "刷新")),
        h(antd.Alert, { type: "info", showIcon: true, message: "灾难性操作会被硬阻断并记录为 blocked。审计查看不会修改 Workspace 数据。", style: { marginBottom: 16 } }),
        error ? h(antd.Alert, { type: "error", showIcon: true, message: error, style: { marginBottom: 16 } }) : null,
        h(antd.Card, { size: "small", style: { marginBottom: 16 } },
          h(antd.Space, null,
            h("span", null, "状态"),
            h(antd.Select, { value: status, style: { width: 140 }, onChange: setStatus, options: [
              { value: "", label: "全部" }, { value: "success", label: "成功" }, { value: "failed", label: "失败" }, { value: "blocked", label: "已阻断" }
            ] }))),
        h(antd.Table, { rowKey: "trace_id", size: "small", loading: loading, columns: columns, dataSource: records, scroll: { x: 1350 }, pagination: { pageSize: 20 } })
      ));
  }

  Q.registerRoutes("zhiyun-audit", [{ path: "/apps/audit", component: AuditViewer, label: "Tool 调用审计", icon: "🛡️", priority: 74 }]);
})();
