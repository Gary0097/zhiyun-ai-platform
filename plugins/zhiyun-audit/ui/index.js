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
    var integrityState = React.useState(null);
    var integrity = integrityState[0];
    var setIntegrity = integrityState[1];

    function load() {
      setLoading(true); setError("");
      var query = status ? "?status=" + encodeURIComponent(status) : "";
      Promise.all([Q.host.fetch("/zhiyun-audit/events" + query), Q.host.fetch("/zhiyun-audit/integrity")]).then(function (responses) {
        if (!responses[0].ok || !responses[1].ok) throw new Error("审计接口不可用");
        return Promise.all([responses[0].json(), responses[1].json()]);
      }).then(function (bodies) { setRecords(bodies[0].events || []); setIntegrity(bodies[1]); })
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
            h("h2", { style: { marginBottom: 4 } }, "安全审计中心"),
            h("p", { style: { color: "#667085", marginTop: 0 } }, "仅展示脱敏后的执行元数据，不展示 Tool 输入、密钥或模型推理。")),
          h(antd.Button, { onClick: load, loading: loading }, "刷新")),
        h(antd.Alert, { type: integrity && integrity.status === "degraded" ? "error" : "info", showIcon: true,
          message: integrity ? (integrity.status === "available" ? "审计链完整性已验证" : "审计链完整性异常") : "正在验证审计链完整性",
          description: "灾难性操作与未确认外部写入会被阻断；键名及内容中的凭据、邮箱和手机号会脱敏。审计查看不会修改 Workspace 数据。", style: { marginBottom: 16 } }),
        h(antd.Collapse, { style: { marginBottom: 16 }, items: [{ key: "guide", label: "功能引导与使用说明", children: h("div", null, h("p", null, "功能介绍：查看 Agent 和工具的脱敏执行记录，验证日志链是否被篡改，并定位失败或被安全策略阻断的操作。"), h("ol", null, h("li", null, "先确认顶部显示“审计链完整性已验证”。"), h("li", null, "使用状态筛选查看失败或已阻断记录。"), h("li", null, "依据 Trace ID 关联具体运行；原始输入和模型推理不会在此展示。"))) }] }),
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

  Q.registerRoutes("zhiyun-audit", [{ path: "/apps/audit", component: AuditViewer, label: "安全审计中心", icon: "🛡️", priority: 74 }]);
})();
