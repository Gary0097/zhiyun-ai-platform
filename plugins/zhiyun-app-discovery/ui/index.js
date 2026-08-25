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
            h(antd.Input, { value: props.draft, placeholder: props.placeholder || "例如：帮我找交付风险应用", onChange: function (e) { props.setDraft(e.target.value); }, onPressEnter: function (e) { if (props.draft.trim()) { props.onSend(props.draft); e.preventDefault(); } } }),
            h(antd.Button, { type: "primary", style: { marginTop: 10, width: "100%" }, loading: props.busy, onClick: function () { if (props.draft.trim()) props.onSend(props.draft); } }, "发送")
          )
        )
      )
    );
  }

  function getJson(path) {
    return Q.host.fetch(path).then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    });
  }

  function statusLabel(status) {
    return ({ installed: "已安装", planned: "未开发", in_progress: "开发中", testing: "验证中", completed: "已完成" })[status] || status;
  }

  function statusColor(status) {
    return ({ installed: "green", planned: "default", in_progress: "blue", testing: "orange", completed: "green" })[status] || "default";
  }

  function MyApps(props) {
    var apps = (props.apps || []).filter(function (item) { return item.install_status === "installed"; });
    var catMap = {
      data: "数据分析", order: "订单管理", service: "售后服务", supply: "供应链",
      sales: "销售客户", finance: "财务", people: "组织协同", integration: "系统集成",
      knowledge: "知识库", system: "系统组件"
    };
    var grouped = {};
    apps.forEach(function (item) {
      var cat = catMap[item.category] || item.category || "其他";
      (grouped[cat] = grouped[cat] || []).push(item);
    });
    return h("div", null,
      h(antd.Alert, { type: "info", showIcon: true, message: "这里只展示当前真实安装的应用与系统组件，按功能大类分组。", style: { marginBottom: 18 } }),
      Object.keys(grouped).map(function (cat) {
        return h("div", { key: cat, style: { marginBottom: 22 } },
          h("h3", { style: { marginBottom: 10, color: "#1f2933" } }, cat),
          h("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(280px,1fr))", gap: 14 } },
            grouped[cat].map(function (item) {
              return h(antd.Card, { key: item.app_id, title: item.name, extra: h(antd.Tag, { color: "green" }, "已安装") },
                h("p", { style: { color: "#667085", minHeight: 22 } }, item.category === "system" ? "AI-OS 系统组件" : "可运行的业务应用"),
                (item.capabilities || []).length ? h("div", { style: { marginBottom: 10 } },
                  (item.capabilities || []).map(function (cap) {
                    return h(antd.Button, { key: cap.id, size: "small", style: { margin: "2px 4px 2px 0" }, href: item.route, title: cap.name }, cap.name);
                  })
                ) : null,
                h("div", { style: { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" } },
                  h(antd.Tag, null, "v" + (item.version || "-")),
                  h(antd.Tag, { color: item.health === "available" ? "green" : "orange" }, item.health === "available" ? "运行可用" : item.health),
                  item.route ? h(antd.Button, { type: "primary", size: "small", href: item.route }, "打开") : h(antd.Button, { size: "small", disabled: true }, "后台服务")
                )
              );
            })
          )
        );
      })
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
    var agentOpenState = React.useState(false), agentOpen = agentOpenState[0], setAgentOpen = agentOpenState[1];
    var agentDraftState = React.useState(""), agentDraft = agentDraftState[0], setAgentDraft = agentDraftState[1];
    var agentMsgState = React.useState([]), agentMessages = agentMsgState[0], setAgentMessages = agentMsgState[1];
    var agentBusyState = React.useState(false), agentBusy = agentBusyState[0], setAgentBusy = agentBusyState[1];
    var agentSessionRef = React.useRef("app-dock-" + Date.now().toString(36));
    function agentAdd(role, text, card) { setAgentMessages(function (prev) { return prev.concat([{ role: role, text: text, card: card }]); }); }
    function agentCommand(key, label) {
      var prompt = key === "mine" ? "我有哪些已安装、可用的应用？"
        : key === "search" ? "帮我检索能完成某业务的真实应用，应该用哪个？"
        : key === "progress" ? "当前应用中心 31 项 PRD 交付进度是怎样的？"
        : (label || key);
      startAgentChat(prompt);
    }
    function startAgentChat(text) {
      text = String(text == null ? "" : text).trim();
      if (!text || agentBusy) return;
      var history = (agentMessages || [])
        .filter(function (m) { return m && m.role !== "system"; })
        .map(function (m) { return { role: m.role === "bot" ? "assistant" : "user", text: m.text || "" }; })
        .slice(-12);
      agentAdd("user", text, null);
      agentAdd("bot", "", null);
      setAgentBusy(true);
      zyPushAgent({ app_id: "zhiyun-app-discovery", kind: "chat", label: text, summary: { apps: apps, progress: progress }, source_type: "real" });
      function setLastBot(value) {
        setAgentMessages(function (prev) {
          var next = prev.slice();
          next[next.length - 1] = { role: "bot", text: value, card: null };
          return next;
        });
      }
      Q.host.fetch("/zhiyun-app-discovery/agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text, session_id: agentSessionRef.current, user_id: "default", history: history })
      })
      .then(function (response) {
        if (!response.ok || !response.body) {
          return response.text().then(function (t) { throw new Error("HTTP " + response.status + (t && t.trim() ? ": " + t.trim() : "")); });
        }
        var reader = response.body.getReader();
        var decoder = new TextDecoder();
        var buffer = "";
        var full = "";
        function read() {
          return reader.read().then(function (chunk) {
            if (chunk.done) return;
            buffer += decoder.decode(chunk.value, { stream: true });
            var lines = buffer.split("\n");
            buffer = lines.pop();
            lines.forEach(function (line) {
              line = line.trim();
              if (line.indexOf("data: ") !== 0) return;
              var raw = line.slice(6).trim();
              if (!raw || raw === "[DONE]") return;
              var event;
              try { event = JSON.parse(raw); } catch (e) { return; }
              if (event.error) {
                if (!full) { full = "智能体返回失败：" + event.error; setLastBot(full); }
                return;
              }
              if (event.type === "text" && event.delta && typeof event.text === "string" && event.text) {
                full += event.text;
                setLastBot(full);
              }
              if (event.type === "message" && event.status === "completed" && Array.isArray(event.content)) {
                for (var i = 0; i < event.content.length; i++) {
                  var part = event.content[i];
                  if (part && part.type === "text" && !part.delta && typeof part.text === "string" && part.text) {
                    full = part.text;
                    setLastBot(full);
                  }
                }
              }
              if (event.status === "failed" && !full) {
                full = event.error || "智能体返回失败";
                setLastBot(full);
              }
            });
            return read();
          });
        }
        return read();
      })
      .then(function () {
        setAgentBusy(false);
        if (!full) setLastBot("（智能体未返回可显示内容）");
      })
      .catch(function (err) {
        setAgentBusy(false);
        setLastBot("调用智能体失败：" + (err && err.message ? err.message : String(err)));
      });
    }
    function agentSend(text) {
      startAgentChat(text);
    }
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
        h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 } },
          h("div", null,
            h("h2", { style: { marginBottom: 4 } }, "应用与项目中心"),
            h("p", { style: { color: "#667085", marginTop: 0 } }, "真实应用入口、能力检索和 31 项 PRD 交付进度。")),
          h(antd.Button, { type: "primary", onClick: function () { setAgentOpen(true); } }, zySpark(), " 问 Agent")),
        h(antd.Collapse, { style: { marginBottom: 16 }, items: [{ key: "guide", label: "功能引导与使用说明", children: h("div", null, h("p", null, "功能介绍：按中文名称、业务功能或自然语言需求查找真实已登记应用，并区分已安装与功能已交付。"), h("ol", null, h("li", null, "在“我的应用”输入要解决的业务问题。"), h("li", null, "查看匹配功能、原因、健康和安装状态。"), h("li", null, "只有已验收能力才会显示可用；计划中功能不会被虚构为可用。"))) }] }),
        error ? h(antd.Alert, { type: "error", message: error, showIcon: true, style: { marginBottom: 16 } }) : null,
        h(antd.Tabs, { defaultActiveKey: "mine", items: items }),
        h(AgentDock, { open: agentOpen, onClose: function () { setAgentOpen(false); }, moduleLabel: "应用与项目中心", chips: [{ key: "mine", label: "我的应用" }, { key: "search", label: "能力检索" }, { key: "progress", label: "查看进度" }], messages: agentMessages, draft: agentDraft, setDraft: setAgentDraft, busy: agentBusy, onSend: agentSend, onCommand: agentCommand })
      )
    );
  }

  Q.registerRoutes("zhiyun-app-discovery", [{ path: "/apps/zhiyun-app-discovery", component: AppCenter, label: "应用与进度", icon: "🧭", priority: 80 }]);
})();
