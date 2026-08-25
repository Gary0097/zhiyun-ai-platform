(function () {
  var Q = window.QwenPaw;
  if (!Q || !Q.host || !Q.host.React || !Q.registerRoutes) return;
  var React = Q.host.React;
  var antd = Q.host.antd;
  var h = React.createElement;

  function zySpark() { return h("span", { style: { fontSize: 13 } }, "✦"); }
  function zyPushAgent(ctx) {
    if (Q.setAgentContext) Q.setAgentContext(ctx);
    else window.dispatchEvent(new CustomEvent("qwenpaw:agent-context", { detail: ctx }));
  }
  function AgentDock(props) {
    var listRef = React.useRef(null);
    React.useEffect(function () {
      if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
    }, [props.messages]);
    if (!props.open) return null;
    var S = {
      mask: { position: "fixed", inset: 0, background: "rgba(15,23,42,0.32)", zIndex: 1200 },
      dock: { position: "fixed", top: 0, right: 0, bottom: 0, width: "min(420px,92vw)", background: "#ffffff", borderLeft: "1px solid #e3e8ef", boxShadow: "-10px 0 30px rgba(16,24,40,0.16)", zIndex: 1201, display: "flex", flexDirection: "column" },
      chat: { display: "flex", flexDirection: "column", height: "100%" },
      head: { padding: "14px 16px", background: "#ffffff", borderBottom: "1px solid #e3e8ef" },
      close: { border: "none", background: "transparent", cursor: "pointer", fontSize: 18, lineHeight: 1, color: "#98a2b3", padding: "4px 8px", borderRadius: 6 },
      list: { flex: "1 1 auto", overflow: "auto", padding: 16 },
      msg: { display: "flex", flexDirection: "column", gap: 6, marginBottom: 14 },
      bubble: { maxWidth: "92%", padding: "10px 12px", borderRadius: 11, fontSize: "12.5px", lineHeight: 1.6, boxShadow: "0 1px 2px rgba(16,24,40,0.04)", whiteSpace: "pre-wrap" },
      card: { maxWidth: "92%", background: "#ffffff", border: "1px solid #e3e8ef", borderRadius: 11, padding: "12px 14px", boxShadow: "0 1px 2px rgba(16,24,40,0.04)", fontSize: 12.5 },
      input: { padding: "12px 14px", background: "#ffffff", borderTop: "1px solid #e3e8ef" },
      chips: { display: "flex", flexWrap: "wrap", gap: 8, marginTop: 10 },
      chip: { border: "1px solid #e3e8ef", background: "#ffffff", borderRadius: 999, padding: "6px 12px", fontSize: 12, color: "#5b6472", cursor: "pointer" }
    };
    return h("div", null,
      h("div", { style: S.mask, onClick: props.onClose }),
      h("div", { style: S.dock },
        h("div", { style: S.chat },
          h("div", { style: S.head },
            h("div", { style: { display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 } },
              h("span", { style: { fontWeight: 650, fontSize: 15, color: "#1f2933" } }, "智能体助手 · " + (props.moduleLabel || "")),
              h("button", { "aria-label": "关闭", onClick: props.onClose, style: S.close }, "✕")
            ),
            h("div", { style: { fontSize: 12, color: "#5b6472", marginTop: 8, lineHeight: 1.5 } }, "直接打字告诉我要做什么，或点击下方快捷指令，自动载入示例并交给智能体处理。"),
            h("div", { style: S.chips },
              (props.chips || []).map(function (c) {
                return h("span", { key: c.key, style: S.chip, onClick: function () { props.onCommand(c.key, c.label); } }, c.label);
              })
            )
          ),
          h("div", { style: S.list, ref: listRef },
            (props.messages || []).map(function (msg, i) {
              var user = msg.role === "user";
              return h("div", { key: i, style: Object.assign({}, S.msg, user ? { alignItems: "flex-end" } : { alignItems: "flex-start" }) },
                h("div", { style: Object.assign({}, S.bubble, user ? { background: "#2563eb", color: "#fff", borderBottomRightRadius: 3 } : { background: "#ffffff", border: "1px solid #e3e8ef", color: "#1f2933", borderBottomLeftRadius: 3 }) }, msg.text),
                msg.card ? h("div", { style: S.card }, msg.card) : null
              );
            })
          ),
          h("div", { style: S.input },
            h(antd.Input, { value: props.draft, placeholder: props.placeholder || "例如：帮我定位失败操作", onChange: function (e) { props.setDraft(e.target.value); }, onPressEnter: function (e) { if (props.draft.trim()) { props.onSend(props.draft); e.preventDefault(); } } }),
            h(antd.Button, { type: "primary", style: { marginTop: 10, width: "100%" }, loading: props.busy, onClick: function () { if (props.draft.trim()) props.onSend(props.draft); } }, "发送")
          )
        )
      )
    );
  }

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
    var agentOpenState = React.useState(false), agentOpen = agentOpenState[0], setAgentOpen = agentOpenState[1];
    var agentDraftState = React.useState(""), agentDraft = agentDraftState[0], setAgentDraft = agentDraftState[1];
    var agentMsgState = React.useState([]), agentMessages = agentMsgState[0], setAgentMessages = agentMsgState[1];
    var agentBusyState = React.useState(false), agentBusy = agentBusyState[0], setAgentBusy = agentBusyState[1];
    function agentAdd(role, text, card) { setAgentMessages(function (prev) { return prev.concat([{ role: role, text: text, card: card }]); }); }
    function agentCommand(key, label) {
      agentAdd("user", label || key);
      setAgentBusy(true);
      setTimeout(function () {
        zyPushAgent({ app_id: "zhiyun-audit", kind: key, label: label || key, summary: { records: records, integrity: integrity, status: status }, source_type: "real" });
        setAgentBusy(false);
        var text = key === "chain" ? "已汇总审计链完整性上下文，可直接在下方查看审计记录与哈希链状态。" : key === "failed" ? "已聚焦失败与被阻断记录，可在状态筛选中切换到「失败 / 已阻断」查看。" : "已定位完整性校验，顶部告警会显示校验可用或异常结论。";
        agentAdd("bot", text, null);
      }, 240);
    }
    function agentSend(text) {
      agentAdd("user", text);
      setAgentBusy(true);
      var key = /失败|阻断/.test(text) ? "failed" : (/完整|校验|篡改/.test(text) ? "integrity" : "chain");
      setTimeout(function () {
        zyPushAgent({ app_id: "zhiyun-audit", kind: key, label: text, summary: { records: records, integrity: integrity, status: status }, source_type: "real" });
        setAgentBusy(false);
        agentAdd("bot", "已将「" + text + "」交给安全审计智能体，可回到界面按状态筛选并核对 Trace。", null);
      }, 240);
    }

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
          h("div", { style: { display: "flex", gap: 8 } },
            h(antd.Button, { type: "primary", onClick: function () { setAgentOpen(true); } }, zySpark(), " 问 Agent"),
            h(antd.Button, { onClick: load, loading: loading }, "刷新"))),
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
        h(antd.Table, { rowKey: "trace_id", size: "small", loading: loading, columns: columns, dataSource: records, scroll: { x: 1350 }, pagination: { pageSize: 20 } }),
        h(AgentDock, { open: agentOpen, onClose: function () { setAgentOpen(false); }, moduleLabel: "安全审计中心", chips: [{ key: "chain", label: "查看审计链" }, { key: "failed", label: "筛选失败" }, { key: "integrity", label: "完整性校验" }], messages: agentMessages, draft: agentDraft, setDraft: setAgentDraft, busy: agentBusy, onSend: agentSend, onCommand: agentCommand })
      ));
  }

  Q.registerRoutes("zhiyun-audit", [{ path: "/apps/zhiyun-audit", component: AuditViewer, label: "安全审计中心", icon: "🛡️", priority: 74 }]);
})();
