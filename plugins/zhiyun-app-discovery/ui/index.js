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

  function readToken() {
    try { return window.localStorage.getItem("zhiyun_token") || ""; } catch (e) { return ""; }
  }
  function request(path, options) {
    var opts = Object.assign({}, options || {});
    var token = readToken();
    opts.headers = Object.assign({}, (options && options.headers) || {}, token ? { Authorization: "Bearer " + token } : {});
    return Q.host.fetch(path, opts).then(function (response) {
      if (!response.ok) return response.json().catch(function () { return {}; }).then(function (body) {
        throw new Error(body.detail || ("HTTP " + response.status));
      });
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
    var openAppAgent = props.openAppAgent || function () {};
    var user = props.user || {};
    var apps = (props.apps || []).filter(function (item) { return item.install_status === "installed"; });
    var catMap = {
      data: "数据分析", order: "订单管理", service: "售后服务", supply: "供应链",
      sales: "销售客户", finance: "财务", people: "组织协同", integration: "系统集成",
      knowledge: "知识库", system: "系统组件"
    };
    var catStyle = {
      data: ["📊", "#1f5ed6"], order: ["📦", "#4338ca"], service: ["🎧", "#0e7490"], supply: ["🚚", "#c2570a"],
      sales: ["📈", "#0e9f6e"], finance: ["💰", "#b45309"], people: ["👥", "#6d28d9"], integration: ["🔌", "#0891b2"],
      knowledge: ["📚", "#475569"], system: ["⚙️", "#64748b"]
    };
    var grouped = {};
    var order = [];
    apps.forEach(function (item) {
      var cat = catMap[item.category] || item.category || "其他";
      if (!grouped[cat]) { grouped[cat] = []; order.push({ key: cat, raw: item.category }); }
      grouped[cat].push(item);
    });
    var bizCount = apps.filter(function (a) { return a.category !== "system"; }).length;
    var capCount = apps.reduce(function (n, a) { return n + ((a.capabilities || []).length); }, 0);
    var healthy = apps.filter(function (a) { return a.health === "available"; }).length;
    var now = new Date();
    var dateText = (now.getMonth() + 1) + "月" + now.getDate() + "日 " + "星期" + "日一二三四五六"[now.getDay()];
    var hello = user.display_name || user.username || "";
    var stat = function (label, value, color) {
      return h("div", { style: { background: "#fff", border: "1px solid #e8edf4", borderRadius: 10, padding: "14px 18px", minWidth: 128 } },
        h("div", { style: { fontSize: 12, color: "#667085" } }, label),
        h("div", { style: { fontSize: 24, fontWeight: 750, color: color || "#182640", marginTop: 2 } }, value));
    };
    return h("div", null,
      h("div", { style: { borderRadius: 12, padding: "22px 26px", marginBottom: 18, color: "#fff", background: "linear-gradient(120deg, #1749a8 0%, #1f5ed6 55%, #3d7ce4 100%)", boxShadow: "0 8px 24px rgba(23,73,168,0.25)" } },
        h("div", { style: { fontSize: 21, fontWeight: 750 } }, (hello ? hello + "，" : "") + "欢迎回来"),
        h("div", { style: { fontSize: 12.5, opacity: 0.85, marginTop: 6 } }, (user.enterprise || "灵泽万川智造云") + " · " + dateText + " · 今天要从哪个应用开始？")
      ),
      h("div", { style: { display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 20 } },
        stat("业务应用", bizCount, "#1f5ed6"), stat("系统组件", apps.length - bizCount, "#64748b"),
        stat("可交付能力", capCount, "#0e9f6e"), stat("运行可用", healthy + "/" + apps.length, healthy === apps.length ? "#0e9f6e" : "#c2570a")
      ),
      order.map(function (grp) {
        var style = catStyle[grp.raw] || ["🧩", "#475569"];
        return h("div", { key: grp.key, style: { marginBottom: 20 } },
          h("div", { style: { display: "flex", alignItems: "center", gap: 8, marginBottom: 10 } },
            h("span", { style: { width: 4, height: 16, borderRadius: 2, background: style[1] } }),
            h("span", { style: { fontWeight: 700, fontSize: 14.5, color: "#182640" } }, grp.key),
            h("span", { style: { fontSize: 12, color: "#98a2b3" } }, grouped[grp.key].length + " 个应用")
          ),
          h("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(300px,1fr))", gap: 12 } },
            grouped[grp.key].map(function (item) {
              return h("div", { key: item.app_id, style: { background: "#fff", border: "1px solid #e8edf4", borderRadius: 10, padding: "14px 16px", display: "flex", gap: 12, transition: "box-shadow .15s ease", cursor: item.route ? "pointer" : "default" },
                  onClick: function () { if (item.route) window.location.href = item.route; } },
                h("div", { style: { width: 42, height: 42, borderRadius: 9, background: style[1] + "14", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 21, flex: "0 0 auto" } }, style[0]),
                h("div", { style: { flex: "1 1 auto", minWidth: 0 } },
                  h("div", { style: { display: "flex", alignItems: "center", gap: 8 } },
                    h("span", { style: { fontWeight: 700, fontSize: 13.5, color: "#182640" } }, item.name),
                    h(antd.Tag, { style: { margin: 0, fontSize: 11 } }, "v" + (item.version || "-")),
                    item.health === "available" ? h(antd.Tag, { color: "green", style: { margin: 0, fontSize: 11 } }, "可用") : h(antd.Tag, { color: "orange", style: { margin: 0, fontSize: 11 } }, item.health)
                  ),
                  (item.capabilities || []).length ? h("div", { style: { display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 } },
                    (item.capabilities || []).slice(0, 4).map(function (cap) {
                      return h("span", { key: cap.id, style: { fontSize: 11.5, color: "#35405a", background: "#f1f5fb", borderRadius: 5, padding: "3px 8px", cursor: "pointer" },
                          onClick: function (e) { e.stopPropagation(); if (item.route) window.location.href = item.route; } }, cap.name);
                    })
                  ) : h("div", { style: { color: "#98a2b3", fontSize: 12, marginTop: 6 } }, item.category === "system" ? "AI-OS 系统组件" : "业务应用"),
                  h("div", { style: { display: "flex", gap: 6, marginTop: 10 } },
                    item.route ? h(antd.Button, { size: "small", type: "primary", onClick: function (e) { e.stopPropagation(); window.location.href = item.route; } }, "打开") : h(antd.Button, { size: "small", disabled: true }, "后台服务"),
                    h(antd.Button, { size: "small", onClick: function (e) { e.stopPropagation(); openAppAgent(item.app_id, item.name, item.capabilities); } }, "问数")
                  )
                )
              );
            })
          )
        );
      })
    );
  }

  function AppSearch(props) {
    var openAppAgent = props.openAppAgent || function () {};
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
      request("/zhiyun-app-discovery/search?q=" + encodeURIComponent(text) + "&limit=12")
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
              installed && item.route ? h(antd.Button, { size: "small", type: "default", onClick: function () { openAppAgent(item.app_id, item.name, item.capabilities); } }, "问数") : null,
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
    var agentAppState = React.useState("zhiyun-app-discovery"), agentApp = agentAppState[0], setAgentApp = agentAppState[1];
    var agentModuleState = React.useState("应用与项目中心"), agentModule = agentModuleState[0], setAgentModule = agentModuleState[1];
    var DEFAULT_CHIPS = [{ key: "mine", label: "我的应用" }, { key: "search", label: "能力检索" }, { key: "progress", label: "查看进度" }];
    var agentChipsState = React.useState(DEFAULT_CHIPS), agentChips = agentChipsState[0], setAgentChips = agentChipsState[1];
    function agentAdd(role, text, card) { setAgentMessages(function (prev) { return prev.concat([{ role: role, text: text, card: card }]); }); }
    function agentCommand(key, label) {
      var prompt;
      if (agentApp === "zhiyun-app-discovery") {
        prompt = key === "mine" ? "我有哪些已安装、可用的应用？"
          : key === "search" ? "帮我检索能完成某业务的真实应用，应该用哪个？"
          : key === "progress" ? "当前应用中心 31 项 PRD 交付进度是怎样的？"
          : (label || key);
      } else {
        prompt = label || key;
      }
      startAgentChat(prompt);
    }
    function openAppAgent(app_id, name, capabilities) {
      var id = app_id || "zhiyun-app-discovery";
      var label = name || "应用与项目中心";
      var caps = capabilities || [];
      setAgentApp(id);
      setAgentModule(label);
      var chips = caps.length ? caps.map(function (c) { return { key: c.id || c.name, label: c.name }; }) : DEFAULT_CHIPS;
      setAgentChips(chips);
      setAgentMessages([]);
      agentSessionRef.current = "app-dock-" + id + "-" + Date.now().toString(36);
      setAgentOpen(true);
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
      zyPushAgent({ app_id: agentApp, kind: "chat", label: text, summary: { apps: apps, progress: progress }, source_type: "real" });
      function setLastBot(value) {
        setAgentMessages(function (prev) {
          var next = prev.slice();
          next[next.length - 1] = { role: "bot", text: value, card: null };
          return next;
        });
      }
      var token = "";
      try { token = window.localStorage.getItem("zhiyun_token") || ""; } catch (e) {}
      var agentHeaders = { "Content-Type": "application/json" };
      if (token) agentHeaders["Authorization"] = "Bearer " + token;
      Q.host.fetch("/zhiyun-app-discovery/agent/chat", {
        method: "POST",
        headers: agentHeaders,
        body: JSON.stringify({ text: text, session_id: agentSessionRef.current, user_id: "default", app_id: agentApp, history: history })
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
    var userState = React.useState({}); var user = userState[0]; var setUser = userState[1];
    React.useEffect(function () {
      Promise.all([getJson("/zhiyun-app-discovery/catalog"), getJson("/zhiyun-app-discovery/progress")])
        .then(function (values) { setApps(values[0].apps || []); setProgress(values[1]); })
        .catch(function () { setError("应用与进度数据加载失败，请检查插件状态。"); });
      try {
        var token = window.localStorage.getItem("zhiyun_token") || "";
        Q.host.fetch("/zhiyun-auth/me", { headers: token ? { Authorization: "Bearer " + token } : {} })
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(function (body) { if (body && body.user) setUser(body.user); });
      } catch (e) {}
    }, []);
    var items = [
      { key: "mine", label: "我的应用", children: h(MyApps, { apps: apps, user: user, openAppAgent: openAppAgent }) },
      { key: "search", label: "应用搜索", children: h(AppSearch, { openAppAgent: openAppAgent }) },
      { key: "progress", label: "项目进度", children: h(ProjectProgress, { apps: apps, progress: progress }) }
    ];
    return h("div", { style: { padding: 28, height: "100%", overflow: "auto", background: "#f7f8fa" } },
      h("div", { style: { maxWidth: 1280, margin: "0 auto" } },
        h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 } },
          h("div", null,
            h("h2", { style: { marginBottom: 4 } }, "应用与项目中心"),
            h("p", { style: { color: "#667085", marginTop: 0 } }, "真实应用入口、能力检索和 31 项 PRD 交付进度。")),
          h(antd.Button, { type: "primary", onClick: function () { openAppAgent("zhiyun-app-discovery", "应用与项目中心"); } }, zySpark(), " 问 Agent")),
        h(antd.Collapse, { style: { marginBottom: 16 }, items: [{ key: "guide", label: "功能引导与使用说明", children: h("div", null, h("p", null, "功能介绍：按中文名称、业务功能或自然语言需求查找真实已登记应用，并区分已安装与功能已交付。"), h("ol", null, h("li", null, "在“我的应用”输入要解决的业务问题。"), h("li", null, "查看匹配功能、原因、健康和安装状态。"), h("li", null, "只有已验收能力才会显示可用；计划中功能不会被虚构为可用。"))) }] }),
        error ? h(antd.Alert, { type: "error", message: error, showIcon: true, style: { marginBottom: 16 } }) : null,
        h(antd.Tabs, { defaultActiveKey: "mine", items: items }),
        h(AgentDock, { open: agentOpen, onClose: function () { setAgentOpen(false); }, moduleLabel: agentModule, chips: agentChips, placeholder: agentApp === "zhiyun-app-discovery" ? "例如：帮我找交付风险应用" : "直接输入业务问题，例如：统计本月订单情况", messages: agentMessages, draft: agentDraft, setDraft: setAgentDraft, busy: agentBusy, onSend: agentSend, onCommand: agentCommand })
      )
    );
  }

  Q.registerRoutes("zhiyun-app-discovery", [{ path: "/apps/zhiyun-app-discovery", component: AppCenter, label: "应用与进度", icon: "🧭", priority: 80 }]);
})();
