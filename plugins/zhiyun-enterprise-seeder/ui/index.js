(function () {
  var Q = window.QwenPaw;
  if (!Q || !Q.host || !Q.host.React || !Q.registerRoutes) return;
  var React = Q.host.React;
  var antd = Q.host.antd;
  var h = React.createElement;

  var NOW = (function () { var d = new Date(); var m = String(d.getMonth() + 1).padStart(2, "0"); var day = String(d.getDate()).padStart(2, "0"); return d.getFullYear() + "-" + m + "-" + day; })();

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
      dock: { position: "fixed", top: 0, right: 0, bottom: 0, width: "min(400px,92vw)", background: "#ffffff", borderLeft: "1px solid #e3e8ef", boxShadow: "-10px 0 30px rgba(16,24,40,0.16)", zIndex: 1201, display: "flex", flexDirection: "column" },
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
              h("span", { style: { fontWeight: 650, fontSize: 15, color: "#1f2933" } }, "智能体助手 · 企业环境初始化器"),
              h("button", { "aria-label": "关闭", onClick: props.onClose, style: S.close }, "✕")
            ),
            h("div", { style: { fontSize: 12, color: "#5b6472", marginTop: 8, lineHeight: 1.5 } }, "直接描述要生成的企业环境，或点击下方快捷指令，我会调用初始化能力并给出结果。"),
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
            h(antd.Input, { value: props.draft, placeholder: props.placeholder || "例如：帮我生成一个60人的制造企业环境", onChange: function (e) { props.setDraft(e.target.value); }, onPressEnter: function (e) { if (props.draft.trim()) { props.onSend(props.draft); e.preventDefault(); } } }),
            h(antd.Button, { type: "primary", style: { marginTop: 10, width: "100%" }, loading: props.busy, onClick: function () { if (props.draft.trim()) props.onSend(props.draft); } }, "发送")
          )
        )
      )
    );
  }

function templateLabel(k) {
  var map = { manufacturing: "智能制造", sales: "商贸零售", finance: "财务共享" };
  return map[k] || k;
}

var ENTITIES = [
  { key: "departments", label: "部门" },
  { key: "org_users", label: "员工" },
  { key: "roles", label: "角色" },
  { key: "agents", label: "智能体" },
  { key: "skills", label: "技能" },
  { key: "apps", label: "应用" },
  { key: "agent_app_access", label: "应用权限" },
  { key: "data_sources", label: "数据源" },
  { key: "sessions", label: "会话" },
  { key: "tasks", label: "任务" },
  { key: "token_usage", label: "Token" },
  { key: "operation_logs", label: "操作日志" },
  { key: "files", label: "文件" },
  { key: "file_downloads", label: "下载" },
  { key: "login_activity", label: "登录" }
];


var RANGE_PRESETS = [
  { key: "all", label: "全部" },
  { key: "today", label: "今天" },
  { key: "yesterday", label: "昨天" },
  { key: "7d", label: "近7天" },
  { key: "30d", label: "近30天" },
  { key: "month", label: "本月" },
  { key: "last_month", label: "上月" },
  { key: "quarter", label: "本季度" },
  { key: "year", label: "今年" },
  { key: "custom", label: "自定义" }
];

function isoDay(d) { var m = String(d.getMonth() + 1).padStart(2, "0"); var day = String(d.getDate()).padStart(2, "0"); return d.getFullYear() + "-" + m + "-" + day; }
function addDays(d, n) { var x = new Date(d); x.setDate(x.getDate() + n); return x; }

function rangeFor(key, customStart, customEnd) {
  if (key === "all") return { key: "all", start: "", end: "" };
  if (key === "custom") return { key: "custom", start: customStart || "", end: customEnd || "" };
  var now = new Date();
  if (key === "today") { var t = isoDay(now); return { key: "today", start: t, end: t }; }
  if (key === "yesterday") { var y = isoDay(addDays(now, -1)); return { key: "yesterday", start: y, end: y }; }
  if (key === "7d") { return { key: "7d", start: isoDay(addDays(now, -6)), end: isoDay(now) }; }
  if (key === "30d") { return { key: "30d", start: isoDay(addDays(now, -29)), end: isoDay(now) }; }
  if (key === "month") { var s = new Date(now.getFullYear(), now.getMonth(), 1); return { key: "month", start: isoDay(s), end: isoDay(now) }; }
  if (key === "last_month") { var ls = new Date(now.getFullYear(), now.getMonth() - 1, 1); var le = new Date(now.getFullYear(), now.getMonth(), 0); return { key: "last_month", start: isoDay(ls), end: isoDay(le) }; }
  if (key === "quarter") { var qm = Math.floor(now.getMonth() / 3) * 3; var qs = new Date(now.getFullYear(), qm, 1); return { key: "quarter", start: isoDay(qs), end: isoDay(now) }; }
  if (key === "year") { return { key: "year", start: isoDay(new Date(now.getFullYear(), 0, 1)), end: isoDay(now) }; }
  return { key: "all", start: "", end: "" };
}

function makeCols(rows) {
  if (!rows.length) return [];
  var first = rows[0];
  return Object.keys(first).filter(function (k) {
    return k !== "env_id" && k !== "data_mode" && k !== "tenant_id";
  }).map(function (k) {
    return { title: k, dataIndex: k, key: k, ellipsis: true, width: Math.min(200, Math.max(96, k.length * 8 + 40)) };
  });
}

function statusCard(s) {
  if (!s) return null;
  return h("div", null,
    h("div", { style: { fontWeight: 650, marginBottom: 6 } }, (s.enterprise || "企业") + " · " + (s.data_mode || "demo").toUpperCase()),
    h("div", { style: { display: "grid", gridTemplateColumns: "repeat(2,1fr)", gap: "4px 10px", fontSize: 12, color: "#475467" } },
      h("div", null, "部门 " + (s.departments || 0)),
      h("div", null, "员工 " + (s.org_users || 0)),
      h("div", null, "智能体 " + (s.agents || 0)),
      h("div", null, "应用 " + (s.apps || 0)),
      h("div", null, "会话 " + (s.sessions || 0)),
      h("div", null, "任务 " + (s.tasks || 0)),
      h("div", null, "Token " + (s.token_total || 0)),
      h("div", null, "调用 " + (s.calls || 0))
    )
  );
}

function TrendSpark(props) {
  var values = props.values || [];
  var width = props.width || 640;
  var height = props.height || 120;
  var max = Math.max.apply(null, values.concat([1]));
  var n = values.length;
  if (!n) return h("div", { style: { fontSize: 12, color: "#98a2b3", padding: "18px 0" } }, "当前范围暂无活动数据。");
  var pad = 8;
  var single = n === 1;
  var step = n > 1 ? (width - pad * 2) / (n - 1) : 0;
  var pts = values.map(function (v, idx) {
    var x = single ? width / 2 : pad + idx * step;
    var y = height - pad - (v / max) * (height - pad * 2);
    return (idx === 0 ? "M" : "L") + x.toFixed(1) + "," + y.toFixed(1);
  }).join(" ");
  var areaPts = pts + " L" + (single ? width / 2 : pad + (n - 1) * step).toFixed(1) + "," + (height - pad) + " L" + (single ? width / 2 : pad).toFixed(1) + "," + (height - pad) + " Z";
  var idxLast = values.length - 1;
  var lastX = single ? width / 2 : pad + idxLast * step;
  var lastY = height - pad - (values[idxLast] / max) * (height - pad * 2);
  return h("svg", { width: "100%", viewBox: "0 0 " + width + " " + height, preserveAspectRatio: "none", style: { display: "block", height: height } },
    single ? h("path", { d: "M" + pad + "," + (height - pad) + " L" + (width - pad) + "," + (height - pad), stroke: "#dbe1ea", strokeWidth: 1 }) : null,
    h("path", { d: areaPts, fill: "rgba(37,99,235,0.10)", stroke: "none" }),
    h("path", { d: pts, fill: "none", stroke: "#2563eb", strokeWidth: 2, strokeLinejoin: "round", strokeLinecap: "round" }),
    h("circle", { cx: lastX, cy: lastY, r: single ? 5 : 3.5, fill: "#2563eb", stroke: "#fff", strokeWidth: 1.5 })
  );
}

function TrendPanel(props) {
  var t = props.data;
  var loading = props.loading;
  if (loading && !t) return h("div", { style: { fontSize: 12, color: "#98a2b3", padding: "18px 0" } }, "趋势加载中…");
  if (!t || !t.series || !t.series.length) return h("div", { style: { fontSize: 12, color: "#98a2b3", padding: "18px 0" } }, "暂无趋势数据，请先生成企业环境或选择时间范围。");
  var series = t.series;
  var sessions = series.map(function (s) { return s.sessions || 0; });
  var tasks = series.map(function (s) { return s.tasks || 0; });
  var tokens = series.map(function (s) { return s.tokens || 0; });
  var logins = series.map(function (s) { return s.logins || 0; });
  var wd = t.workday_avg || {};
  var we = t.weekend_avg || {};
  var growth = t.growth || {};
  var agents = (growth.agents || []).map(function (g) { return g.total; });
  var users = (growth.users || []).map(function (g) { return g.total; });
  var fmt = function (n) { return (n == null || isNaN(n)) ? 0 : n; };
  function mini(val, color, label) {
    return h("div", { style: { flex: 1, minWidth: 140, background: "#fbfcfe", border: "1px solid #eef1f6", borderRadius: 9, padding: "10px 12px" } },
      h("div", { style: { fontSize: 12, color: "#667085" } }, label),
      h("div", { style: { fontSize: 18, fontWeight: 750, color: color, marginTop: 3 } }, fmt(val))
    );
  }
  function curve(title, vals, color) {
    return h("div", { style: { padding: "10px 0", borderTop: "1px solid #eef1f6" } },
      h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 } },
        h("span", { style: { fontSize: 12, color: "#667085", fontWeight: 600 } }, title),
        h("span", { style: { fontSize: 12, color: "#98a2b3" } }, "近 " + series.length + " 个" + (t.granularity === "month" ? "月" : (t.granularity === "week" ? "周" : "日")))
      ),
      h(TrendSpark, { values: vals, height: 70 })
    );
  }
  return h("div", null,
    h("div", { style: { display: "flex", alignItems: "center", flexWrap: "wrap", gap: 8, marginBottom: 12 } },
      h("span", { style: { fontSize: 12, color: "#98a2b3" } }, (t.start_date || "-") + " ~ " + (t.end_date || "-") + " · " + (t.granularity === "month" ? "按月" : (t.granularity === "week" ? "按周" : "按日"))),
      h("span", { style: { marginLeft: "auto", fontSize: 12, color: "#98a2b3" } }, "会话 " + fmt(t.summary.sessions) + " · 任务 " + fmt(t.summary.tasks) + " · Token " + fmt(t.summary.tokens))
    ),
    h("div", { style: { display: "flex", flexWrap: "wrap", gap: 12, marginBottom: 8 } },
      mini(wd.sessions, "#2563eb", "工作日平均会话"),
      mini(we.sessions, "#7c9cf5", "周末平均会话"),
      mini(wd.tokens, "#0f766e", "工作日平均Token"),
      mini(we.tokens, "#5aa7a0", "周末平均Token")
    ),
    curve("会话活动", sessions, "#2563eb"),
    curve("任务调用", tasks, "#0f766e"),
    curve("Token 消耗", tokens, "#b45309"),
    curve("登录活跃", logins, "#7c3aed"),
    curve("智能体累计", agents, "#2563eb"),
    curve("用户累计", users, "#0f766e")
  );
}
function AgentFactoryPanel(props) {
  var toast = antd && antd.message ? antd.message : { success: function () {}, error: function () {}, warning: function () {} };

  var catState = React.useState(null);
  var cat = catState[0]; var setCat = catState[1];
  var tplState = React.useState({ templates: [], agents: {} });
  var tpl = tplState[0]; var setTpl = tplState[1];
  var bindState = React.useState(null);
  var bindings = bindState[0]; var setBindings = bindState[1];
  var selState = React.useState("manufacturing");
  var selValue = selState[0]; var setSelValue = selState[1];
  var loadState = React.useState(false);
  var loading = loadState[0]; var setLoading = loadState[1];
  var rcState = React.useState(false);
  var reconciling = rcState[0]; var setReconciling = rcState[1];
  var valState = React.useState(false);
  var validating = valState[0]; var setValidating = valState[1];
  var validateState = React.useState(null);
  var validate = validateState[0]; var setValidate = validateState[1];

  function envQuery() {
    var q = [];
    if (props.envId) q.push("env_id=" + encodeURIComponent(props.envId));
    if (props.mode) q.push("data_mode=" + encodeURIComponent(props.mode));
    return q.length ? ("?" + q.join("&")) : "";
  }

  function loadAll() {
    setLoading(true);
    var bindUrl = "/zhiyun-enterprise-seeder/agent-factory/bindings" + envQuery();
    return Promise.all([
      request("/zhiyun-enterprise-seeder/agent-factory/catalog"),
      request("/zhiyun-enterprise-seeder/agent-factory/templates"),
      request(bindUrl)
    ]).then(function (rs) {
      setCat(rs[0]);
      setTpl({ templates: rs[1].templates || [], agents: rs[1].agents || {} });
      setBindings(rs[2]);
      var tlist = rs[1].templates || [];
      if (tlist.length && tlist.indexOf(selValue) === -1) setSelValue(tlist[0]);
      setLoading(false);
    }).catch(function (e) { setLoading(false); toast.error(e.message || "加载智能体工厂失败"); });
  }

  function reconcile() {
    setReconciling(true);
    request("/zhiyun-enterprise-seeder/agent-factory/reconcile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ env_id: props.envId || "", data_mode: props.mode || "" })
    }).then(function (r) {
      toast.success("已回填 " + (r.reconciled || 0) + " 个智能体的绑定");
      if (props.pushAgentMessage) props.pushAgentMessage("assistant", "Agent Factory 已为 " + (r.reconciled || 0) + " 个智能体回填模型/工具/应用权限。", null);
      return loadAll();
    }).catch(function (e) { toast.error(e.message || "回填失败"); }).then(function () { setReconciling(false); });
  }

  function doValidate() {
    var agent = (tpl.agents[selValue] || [])[0];
    if (!agent) { toast.warning("暂无模板可校验"); return; }
    setValidating(true);
    var payload = {
      id: agent.agent_id || "business_analyst",
      name: agent.name || "",
      position: agent.position || "",
      department: agent.department || "",
      category: agent.category || "general",
      model_id: agent.model_id || "",
      max_tokens: agent.max_tokens || 8192,
      execution_freq: agent.execution_freq || 5,
      work_start: agent.work_start || "09:00",
      work_end: agent.work_end || "18:00",
      auto_tasks: agent.auto_tasks || 0,
      manual_tasks: agent.manual_tasks || 0,
      success_rate: agent.success_rate || 0.9,
      avg_response_ms: agent.avg_response_ms || 1800,
      kb_scope: agent.kb_scope || "enterprise",
      data_scope: agent.data_scope || "enterprise",
      skills: (agent.skills || []).map(function (s) { return [s.name, s.code]; }),
      tools: (agent.tools || []).map(function (t) { return t.tool_id || t; })
    };
    request("/zhiyun-enterprise-seeder/agent-factory/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (r) {
      setValidate(r);
      if (props.pushAgentMessage) props.pushAgentMessage("assistant", r.ok ? ("「" + ((r.config && r.config.name) || "智能体") + "」配置校验通过，模型/技能/工具/应用权限齐备。") : ("校验发现 " + (r.errors || []).length + " 个问题：\n" + (r.errors || []).map(function (e) { return "- " + e.message; }).join("\n")), null);
      toast.success(r.ok ? "配置校验通过" : ("配置校验有 " + (r.errors || []).length + " 个问题"));
      setValidating(false);
    }).catch(function (e) { toast.error(e.message || "校验失败"); setValidating(false); });
  }

  React.useEffect(function () { loadAll(); }, []);

  var agentList = (tpl.agents && tpl.agents[selValue]) || [];
  var cols = [
    { title: "智能体", dataIndex: "name", key: "name", width: 150, render: function (v, r) { return h("div", null, h("div", { style: { fontWeight: 650, color: "#1f2933" } }, v), h("div", { style: { fontSize: 11, color: "#98a2b3" } }, r.agent_id || "")); } },
    { title: "岗位", dataIndex: "position", key: "position", width: 90 },
    { title: "部门", dataIndex: "department", key: "department", width: 80 },
    { title: "模型", dataIndex: "model", key: "model", width: 120, render: function (v, r) { return (r.model && r.model.name) || v || ""; } },
    { title: "技能", dataIndex: "skills", key: "skills", render: function (v) { return h("div", { style: { display: "flex", flexWrap: "wrap", gap: 4 } }, (v || []).map(function (s) { return h("span", { key: s.skill_id, style: { background: "#eef4ff", color: "#2563eb", borderRadius: 6, padding: "1px 6px", fontSize: 11 } }, s.name); })); } },
    { title: "工具", dataIndex: "tools", key: "tools", render: function (v) { return h("div", { style: { display: "flex", flexWrap: "wrap", gap: 4 } }, (v || []).map(function (t) { return h("span", { key: t.tool_id, style: { background: "#fff7ed", color: "#c2410c", borderRadius: 6, padding: "1px 6px", fontSize: 11 } }, t.name); })); } },
    { title: "应用权限", dataIndex: "apps", key: "apps", render: function (v) { return h("div", { style: { display: "flex", flexWrap: "wrap", gap: 4 } }, (v || []).map(function (a) { return h("span", { key: a, style: { background: "#f0fdf4", color: "#15803d", borderRadius: 6, padding: "1px 6px", fontSize: 11 } }, a); })); } },
    { title: "成功率", dataIndex: "success_rate", key: "success_rate", width: 76, render: function (v) { return Math.round((v || 0) * 100) + "%"; } },
    { title: "响应", dataIndex: "avg_response_ms", key: "avg_response_ms", width: 74, render: function (v) { return (v || 0) + "ms"; } }
  ];

  var bindModels = (bindings && bindings.models) || [];
  var bindTools = (bindings && bindings.agent_tools) || [];
  var bindApps = (bindings && bindings.agent_app_access) || [];

  return h(antd.Card, { style: { borderRadius: 10, border: "1px solid #e8ecf1", boxShadow: "0 1px 3px rgba(16,24,40,0.04)", marginTop: 18 } },
    h("div", { style: { display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 } },
      h("div", { style: { display: "flex", alignItems: "center", gap: 10 } },
        h("span", { style: { fontSize: 15, fontWeight: 700, color: "#1f2933" } }, "智能体工厂"),
        h("span", { style: { background: "#eef4ff", color: "#2563eb", borderRadius: 6, padding: "3px 9px", fontSize: 12, fontWeight: 600 } }, "Epic 2")
      ),
      h("div", { style: { display: "flex", flexWrap: "wrap", gap: 8 } },
        h(antd.Button, { size: "small", loading: loading, onClick: loadAll }, "加载编目"),
        h(antd.Button, { size: "small", loading: reconciling, onClick: reconcile }, "回填绑定"),
        h(antd.Button, { size: "small", type: "primary", loading: validating, onClick: doValidate }, "校验配置")
      )
    ),
    h("div", { style: { display: "flex", flexWrap: "wrap", gap: 8, marginTop: 14 } },
      (tpl.templates || []).map(function (t) {
        var active = t === selValue;
        return h("button", { key: t, onClick: function () { setSelValue(t); }, style: { border: "1px solid " + (active ? "#2563eb" : "#e2e6ec"), background: active ? "#eef4ff" : "#fff", color: active ? "#2563eb" : "#475467", borderRadius: 8, padding: "4px 11px", fontSize: 12.5, fontWeight: active ? 650 : 500, cursor: "pointer" } }, templateLabel(t));
      })
    ),
    loading ? h("div", { style: { marginTop: 16 } }, h(antd.Skeleton, { active: true, title: false, paragraph: { rows: 4 } })) : null,
    (!loading && agentList.length) ? h(antd.Table, { rowKey: "agent_id", columns: cols, dataSource: agentList, size: "small", pagination: false, scroll: { x: "max-content" }, style: { marginTop: 16 } }) : null,
    h("div", { style: { display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 10, marginTop: 16 } },
      [["模型", bindModels.length], ["工具绑定", bindTools.length], ["应用权限", bindApps.length]].map(function (it) {
        return h("div", { key: it[0], style: { background: "#fbfcfe", border: "1px solid #eef1f6", borderRadius: 9, padding: "10px 12px" } },
          h("div", { style: { fontSize: 12, color: "#667085" } }, it[0]),
          h("div", { style: { fontSize: 20, fontWeight: 750, color: "#1f2933", marginTop: 2 } }, it[1])
        );
      })
    ),
    validate ? h("div", { style: { marginTop: 14, padding: "10px 12px", borderRadius: 8, background: validate.ok ? "#f6fef9" : "#fff5f5", border: "1px solid " + (validate.ok ? "#bbf7d0" : "#fecaca"), fontSize: 12.5, color: "#1f2933", lineHeight: 1.6 } },
      h("span", { style: { fontWeight: 650 } }, validate.ok ? "✓ 配置校验通过" : "✕ 配置校验不通过"),
      (validate.errors || []).length ? h("div", { style: { marginTop: 6 } }, validate.errors.map(function (e) { return h("div", { key: e.field + e.message }, "· " + e.message); })) : null
    ) : null
  );
}

function SimulationRuntimePanel(props) {
  var toast = antd && antd.message ? antd.message : { success: function () {}, error: function () {}, warning: function () {} };
  var statusState = React.useState(null);
  var status = statusState[0]; var setStatus = statusState[1];
  var selState = React.useState(null);
  var sel = selState[0]; var setSel = selState[1];
  var modeState = React.useState("demo");
  var mode = modeState[0]; var setMode = modeState[1];
  var rangeState = React.useState({ start: "", end: "" });
  var range = rangeState[0]; var setRange = rangeState[1];
  var forceState = React.useState(false);
  var force = forceState[0]; var setForce = forceState[1];
  var previewState = React.useState(null);
  var preview = previewState[0]; var setPreview = previewState[1];
  var runState = React.useState(null);
  var run = runState[0]; var setRun = runState[1];
  var eventsState = React.useState([]);
  var events = eventsState[0]; var setEvents = eventsState[1];
  var busyState = React.useState(false);
  var busy = busyState[0]; var setBusy = busyState[1];

  function loadStatus() {
    setBusy(true);
    return request("/zhiyun-enterprise-seeder/simulation/status").then(function (s) {
      setStatus(s);
      var list = (s.environments || []);
      if (list.length) {
        var first = list[0];
        setSel(first.env_id);
        setMode(first.data_mode || "demo");
        setRange({ start: first.start_date || "", end: first.end_date || "" });
      }
      setBusy(false);
    }).catch(function (e) {
      setBusy(false);
      toast.error(e.message || "加载 Simulation Runtime 失败");
    });
  }

  function pickEnv(envId) {
    setSel(envId);
    var it = (status.environments || []).find(function (x) { return x.env_id === envId; });
    if (it) {
      setMode(it.data_mode || "demo");
      setRange({ start: it.start_date || "", end: it.end_date || "" });
    }
  }

  function qs() {
    var q = [];
    if (sel) q.push("env_id=" + encodeURIComponent(sel));
    q.push("data_mode=" + encodeURIComponent(mode));
    if (range.start) q.push("start_date=" + encodeURIComponent(range.start));
    if (range.end) q.push("end_date=" + encodeURIComponent(range.end));
    return q.join("&");
  }

  function doPreview() {
    if (!sel) { toast.warning("请先选择环境"); return; }
    setBusy(true); setPreview(null);
    request("/zhiyun-enterprise-seeder/simulation/preview?" + qs()).then(function (r) {
      setPreview(r);
      var sum = r.summary || {};
      var line = "预览 " + (r.days || []).length + " 天：会话 " + (sum.sessions || 0) + " / 任务 " + (sum.calls || 0) + " / Token " + (sum.tokens || 0);
      if (props.pushAgentMessage) props.pushAgentMessage("assistant", "Simulation Runtime 预览完成：" + line, null);
      setBusy(false);
    }).catch(function (e) { setBusy(false); toast.error(e.message || "预览失败"); });
  }

  function doRun() {
    if (!sel) { toast.warning("请先选择环境"); return; }
    setBusy(true); setRun(null);
    var body = { env_id: sel, data_mode: mode, start_date: range.start, end_date: range.end, force: force, seed: 0 };
    if (props.pushAgentMessage) props.pushAgentMessage("user", "运行 Simulation Runtime：" + sel + " / " + (range.start || "-") + "~" + (range.end || "-"));
    request("/zhiyun-enterprise-seeder/simulation/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(function (r) {
      setRun(r);
      var msg = "已写入 " + (r.days_written || 0) + " 天（跳过 " + (r.days_skipped || 0) + " 天）· 会话 " + (r.summary && r.summary.sessions || 0) + " / 任务 " + (r.summary && r.summary.calls || 0);
      toast.success(msg);
      if (props.pushAgentMessage) props.pushAgentMessage("assistant", "Simulation Runtime 运行完成：" + msg, null);
      setBusy(false);
      return loadEvents();
    }).catch(function (e) { setBusy(false); toast.error(e.message || "运行失败"); if (props.pushAgentMessage) props.pushAgentMessage("assistant", "运行失败：" + (e.message || ""), null); });
  }

  function loadEvents() {
    var url = "/zhiyun-enterprise-seeder/simulation/events?limit=50";
    if (sel) url += "&env_id=" + encodeURIComponent(sel);
    url += "&data_mode=" + encodeURIComponent(mode);
    return request(url).then(function (r) { setEvents(r.events || []); }).catch(function () { setEvents([]); });
  }

  React.useEffect(function () { loadStatus(); }, []);

  var total = (status && status.totals) || {};
  var sum = (preview && preview.summary) || (run && run.summary) || null;
  var envs = (status && status.environments) || [];
  var evCols = [
    { title: "日期", dataIndex: "day", key: "day", width: 100, ellipsis: true },
    { title: "类型", dataIndex: "event_type", key: "event_type", width: 90, ellipsis: true },
    { title: "用户", dataIndex: "user_id", key: "user_id", ellipsis: true },
    { title: "智能体", dataIndex: "agent_id", key: "agent_id", ellipsis: true },
    { title: "应用", dataIndex: "app_id", key: "app_id", ellipsis: true },
    { title: "Token", dataIndex: "tokens", key: "tokens", width: 80 },
    { title: "成功", dataIndex: "success", key: "success", width: 60 }
  ];

  return h(antd.Card, { style: { borderRadius: 10, border: "1px solid #e8ecf1", boxShadow: "0 1px 3px rgba(16,24,40,0.04)" } },
    h("div", null,
      h("div", { style: { display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 } },
        h("div", { style: { display: "flex", alignItems: "center", gap: 8 } },
          h("span", { style: { fontSize: 15, fontWeight: 700, color: "#1f2933" } }, "演示运行容器"),
          h("span", { style: { background: "#eef4ff", color: "#2563eb", borderRadius: 6, padding: "3px 9px", fontSize: 12, fontWeight: 600 } }, "Epic 3 / Event Runtime")
        ),
        h(antd.Button, { size: "small", loading: busy, onClick: loadStatus }, "刷新环境")
      ),
      h("div", { style: { marginTop: 12, fontSize: 12, color: "#667085", lineHeight: 1.6 } },
        "对已有环境做「预览/运行」，业务事件会写进 business_events 审计并可回溯到会话/任务/文件/Token；同企业共享实例，demo 与 production 完全隔离。"
      ),
      h("div", { style: { display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10, marginTop: 14 } },
        [["环境", total.environments || 0], ["业务事件", total.business_events || 0], ["会话", total.sessions || 0], ["Token", total.tokens || 0]].map(function (it) {
          return h("div", { key: it[0], style: { background: "#fbfcfe", border: "1px solid #eef1f6", borderRadius: 9, padding: "10px 12px" } },
            h("div", { style: { fontSize: 12, color: "#667085" } }, it[0]),
            h("div", { style: { fontSize: 20, fontWeight: 750, color: "#1f2933", marginTop: 2 } }, it[1])
          );
        })
      ),
      h("div", { style: { display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginTop: 16 } },
        h("div", null,
          h("div", { style: { fontSize: 12, color: "#667085", marginBottom: 6 } }, "目标环境"),
          h(antd.Select, { style: { width: "100%" }, value: sel || undefined, placeholder: "选择环境", onChange: pickEnv, options: envs.map(function (e) { return { value: e.env_id, label: (e.enterprise || "企业") + " · " + (e.data_mode || "").toUpperCase() }; }) })
        ),
        h("div", null,
          h("div", { style: { fontSize: 12, color: "#667085", marginBottom: 6 } }, "数据环境"),
          h(antd.Select, { style: { width: "100%" }, value: mode, onChange: setMode, options: [{ value: "demo", label: "Demo 演示环境" }, { value: "production", label: "Live 生产环境" }] })
        ),
        h("div", null,
          h("div", { style: { fontSize: 12, color: "#667085", marginBottom: 6 } }, "强制覆盖"),
          h("div", { style: { display: "flex", alignItems: "center", gap: 8, height: 32 } },
            h(antd.Switch, { checked: force, onChange: setForce }),
            h("span", { style: { fontSize: 12, color: "#5b6472" } }, force ? "已有数据的日期也将重写" : "自动跳过已有业务数据")
          )
        )
      ),
      h("div", { style: { display: "grid", gridTemplateColumns: "1fr 1fr 150px 150px 120px", gap: 10, marginTop: 12 } },
        h(antd.Input, { type: "date", size: "small", value: range.start, onChange: function (e) { setRange(Object.assign({}, range, { start: e.target.value })); }, style: { width: "100%" } }),
        h("span", { style: { alignSelf: "center", textAlign: "center", color: "#98a2b3", fontSize: 12 } }, "至"),
        h(antd.Input, { type: "date", size: "small", value: range.end, onChange: function (e) { setRange(Object.assign({}, range, { end: e.target.value })); }, style: { width: "100%" } }),
        h(antd.Button, { size: "small", loading: busy, onClick: doPreview }, "预览"),
        h(antd.Button, { size: "small", type: "primary", loading: busy, onClick: doRun }, "运行")
      ),
      (sum ? h("div", { style: { display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 10, marginTop: 14 } },
        [["天数", run ? (run.days_written || 0) : ((preview && preview.days && preview.days.length) || 0)], ["会话/任务", (sum.sessions || 0) + " / " + (sum.calls || 0)], ["Token", sum.tokens || 0]].map(function (it) {
          return h("div", { key: it[0], style: { background: "#f6fef9", border: "1px solid #bbf7d0", borderRadius: 9, padding: "10px 12px" } },
            h("div", { style: { fontSize: 12, color: "#667085" } }, it[0]),
            h("div", { style: { fontSize: 20, fontWeight: 750, color: "#1f2933", marginTop: 2 } }, it[1])
          );
        })
      ) : null),
      h("div", { style: { display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 18 } },
        h("div", { style: { fontSize: 13, fontWeight: 650, color: "#1f2933" } }, "最近业务事件"),
        h(antd.Button, { size: "small", onClick: loadEvents }, "刷新事件")
      ),
      h(antd.Table, { rowKey: "event_id", columns: evCols, dataSource: events, size: "small", pagination: { pageSize: 8, size: "small", showSizeChanger: false }, scroll: { x: "max-content" }, style: { marginTop: 10 }, locale: { emptyText: "尚无业务事件，点击「运行」生成" } })
    )
  );
}

function EnterpriseSeeder() {
  var toast = antd && antd.message ? antd.message : { success: function () {}, error: function () {}, warning: function () {} };

  var cfgState = React.useState(null);
  var cfg = cfgState[0]; var setCfg = cfgState[1];
  var metaState = React.useState({ templates: [], departments: {}, agents: {}, apps: [] });
  var meta = metaState[0]; var setMeta = metaState[1];
  var loadingState = React.useState(true);
  var loading = loadingState[0]; var setLoading = loadingState[1];
  var generatingState = React.useState(false);
  var generating = generatingState[0]; var setGenerating = generatingState[1];
  var statsState = React.useState(null);
  var stats = statsState[0]; var setStats = statsState[1];
  var entityState = React.useState("org_users");
  var entity = entityState[0]; var setEntity = entityState[1];
  var rowsState = React.useState([]);
  var rows = rowsState[0]; var setRows = rowsState[1];
  var rowsLoadingState = React.useState(false);
  var rowsLoading = rowsLoadingState[0]; var setRowsLoading = rowsLoadingState[1];
  var rangeState = React.useState({ key: "all", start: "", end: "" });
  var range = rangeState[0]; var setRange = rangeState[1];
  var customStartState = React.useState("");
  var customStart = customStartState[0]; var setCustomStart = customStartState[1];
  var customEndState = React.useState("");
  var customEnd = customEndState[0]; var setCustomEnd = customEndState[1];
  var integrityState = React.useState(null);
  var integrity = integrityState[0]; var setIntegrity = integrityState[1];
  var integrityLoadingState = React.useState(false);
  var trendsState = React.useState(null);
  var trends = trendsState[0]; var setTrends = trendsState[1];
  var trendsLoadingState = React.useState(false);
  var trendsLoading = trendsLoadingState[0]; var setTrendsLoading = trendsLoadingState[1];
  var granularityState = React.useState("day");
  var granularity = granularityState[0]; var setGranularity = granularityState[1];
  var integrityLoading = integrityLoadingState[0]; var setIntegrityLoading = integrityLoadingState[1];
  var dailyIntegrityState = React.useState(null);
  var dailyIntegrity = dailyIntegrityState[0]; var setDailyIntegrity = dailyIntegrityState[1];
  var repairingState = React.useState(false);
  var repairing = repairingState[0]; var setRepairing = repairingState[1];

  var agentOpenState = React.useState(false);
  var agentOpen = agentOpenState[0]; var setAgentOpen = agentOpenState[1];
  var agentMessagesState = React.useState([]);
  var agentMessages = agentMessagesState[0]; var setAgentMessages = agentMessagesState[1];
  var agentDraftState = React.useState("");
  var agentDraft = agentDraftState[0]; var setAgentDraft = agentDraftState[1];

  function pushAgentMessage(role, text, card) {
    setAgentMessages(function (m) { return m.concat([{ role: role, text: text, card: card || null }]); });
  }

  function publishDataContext(envId, mode, rangeArg) {
    var r = rangeArg || range || {};
    var body = { data_mode: mode || "", start_date: r.start || "", end_date: r.end || "" };
    if (envId) body.env_id = envId;
    return request("/zhiyun-data-core/context", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).catch(function (e) {
      if (window.console && console.warn) console.warn("发布数据上下文失败", e && e.message);
    });
  }

  function fetchRows(name, envId, mode, rangeArg) {
    setRowsLoading(true);
    var url = "/zhiyun-enterprise-seeder/records/" + encodeURIComponent(name) + "?limit=100";
    if (envId) url += "&env_id=" + encodeURIComponent(envId);
    if (mode) url += "&data_mode=" + encodeURIComponent(mode);
    var r = rangeArg || range;
    if (r && r.start) url += "&start_date=" + encodeURIComponent(r.start);
    if (r && r.end) url += "&end_date=" + encodeURIComponent(r.end);
    return request(url).then(function (data) {
      setRows(data.rows || []);
      setRowsLoading(false);
    }).catch(function (e) {
      setRows([]);
      setRowsLoading(false);
      toast.error(e.message || "读取记录失败");
    });
  }

  function loadSummary(envId, mode, rangeArg) {
    var r = rangeArg || range;
    var url = "/zhiyun-enterprise-seeder/summary?limit=3";
    if (mode) url += "&data_mode=" + encodeURIComponent(mode);
    if (r && r.start) url += "&start_date=" + encodeURIComponent(r.start);
    if (r && r.end) url += "&end_date=" + encodeURIComponent(r.end);
    return request(url).then(function (s) {
      var list = s.summary || [];
      var it = list[0];
      if (it) setStats(it);
      if (it) publishDataContext(it.env_id, it.data_mode, r);
      return it;
    });
  }

  function applyRange(key) {
    var r = rangeFor(key, customStart, customEnd);
    setRange(r);
    var envId = stats && stats.env_id;
    var mode = stats && stats.data_mode;
    return loadSummary(envId, mode, r).then(function (it) {
      var tid = it && it.env_id ? it.env_id : envId;
      var tmode = it && it.data_mode ? it.data_mode : mode;
      loadTrends(tid, tmode, r, null);
      if (it && it.env_id) return fetchRows(entity, it.env_id, it.data_mode, r);
      return fetchRows(entity, envId, mode, r);
    });
  }

  function loadIntegrity() {
    setIntegrityLoading(true);
    var url = "/zhiyun-enterprise-seeder/integrity?";
    var envId = stats && stats.env_id;
    var mode = stats && stats.data_mode;
    if (envId) url += "env_id=" + encodeURIComponent(envId) + "&";
    if (mode) url += "data_mode=" + encodeURIComponent(mode);
    return request(url).then(function (d) {
      setIntegrity(d);
      setIntegrityLoading(false);
    }).catch(function (e) {
      setIntegrityLoading(false);
      setIntegrity(null);
      toast.error(e.message || "一致性检查失败");
    });
  }

  function loadDailyReport() {
    var url = "/zhiyun-enterprise-seeder/integrity/daily?";
    var envId = stats && stats.env_id;
    var mode = stats && stats.data_mode;
    if (envId) url += "env_id=" + encodeURIComponent(envId) + "&";
    if (mode) url += "data_mode=" + encodeURIComponent(mode);
    return request(url).then(function (d) {
      setDailyIntegrity(d);
      if (d && d.report) setIntegrity(d);
      return d;
    }).catch(function (e) {
      toast.error(e.message || "读取今日快照失败");
    });
  }

  function runRepair() {
    if (!stats || !stats.env_id) { toast.warning("尚未生成企业环境，无法执行修复"); return; }
    setRepairing(true);
    pushAgentMessage("user", "对 " + (stats.enterprise || "当前环境") + " 执行数据一致性自动修复");
    return request("/zhiyun-enterprise-seeder/integrity/repair", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ env_id: stats.env_id, data_mode: stats.data_mode || "demo" })
    }).then(function (res) {
      var a = res.report || {};
      setIntegrity(a);
      var fixed = (res.fixed_checks || []).length;
      var remain = (res.remaining_checks || []).length;
      toast.success("自动修复完成" + (fixed ? "：处理 " + fixed + " 项" : "") + (remain ? "，剩余 " + remain + " 项需人工" : "，全部通过"));
      pushAgentMessage("assistant", "自动修复完成，报告已刷新。", statusCard({ healthy: a.healthy, passed: a.passed, total: a.total, failed: a.failed, data_mode: a.data_mode }));
      return loadDailyReport();
    }).catch(function (e) {
      toast.error(e.message || "自动修复失败");
    }).then(function () { setRepairing(false); });
  }

  function loadTrends(envId, mode, rangeArg, gran) {
    var r = rangeArg || range;
    var g = gran || granularity;
    var url = "/zhiyun-enterprise-seeder/analytics/trends?granularity=" + encodeURIComponent(g);
    if (envId) url += "&env_id=" + encodeURIComponent(envId);
    if (mode) url += "&data_mode=" + encodeURIComponent(mode);
    if (r && r.start) url += "&start_date=" + encodeURIComponent(r.start);
    if (r && r.end) url += "&end_date=" + encodeURIComponent(r.end);
    setTrendsLoading(true);
    return request(url).then(function (d) {
      setTrends(d);
      setTrendsLoading(false);
    }).catch(function () {
      setTrends(null);
      setTrendsLoading(false);
    });
  }
  function switchEntity(name, rangeArg) {
    setEntity(name);
    fetchRows(name, stats && stats.env_id, stats && stats.data_mode, rangeArg);
  }

  function doGenerate(overrides) {
    if (!cfg) { toast.warning("配置尚未载入"); return; }
    var payload = Object.assign({}, cfg, overrides || {});
    payload.scale = Number(payload.scale) || 1;
    payload.departments = Number(payload.departments) || 1;
    payload.agents = Number(payload.agents) || 1;
    setGenerating(true);
    pushAgentMessage("user", "生成 " + payload.enterprise + "（" + (payload.scale || 0) + " 人）企业环境");
    zyPushAgent({ module: "企业环境初始化器", action: "seed", payload: payload });
    return request("/zhiyun-enterprise-seeder/seed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (res) {
      var sum = res.summary || {};
      setStats(sum);
      setRange({ key: "all", start: "", end: "" });
      publishDataContext(sum.env_id, sum.data_mode, { key: "all", start: "", end: "" });
      toast.success("企业环境已生成并运行：" + (sum.enterprise || payload.enterprise));
      pushAgentMessage("assistant", "已生成 " + payload.enterprise + " 环境。", statusCard(sum));
      zyPushAgent({ module: "企业环境初始化器", action: "seed.result", summary: sum });
      loadIntegrity();
      return fetchRows(entity, sum.env_id, sum.data_mode, { key: "all", start: "", end: "" });
    }).catch(function (err) {
      toast.error(err.message || "生成失败");
      pushAgentMessage("assistant", "生成失败：" + (err.message || "未知错误"));
    }).then(function () { setGenerating(false); });
  }

  function agentCommand(key) {
    if (key === "init") {
      if (cfg) doGenerate();
      else toast.warning("配置尚未载入");
    } else if (key === "status") {
      pushAgentMessage("user", "查询状态");
      request("/zhiyun-enterprise-seeder/summary?limit=1").then(function (s) {
        var it = (s.summary || [])[0];
        if (it) setStats(it);
        if (it) publishDataContext(it.env_id, it.data_mode, { key: "all", start: "", end: "" });
        pushAgentMessage("assistant", it ? ("当前企业环境：") : "尚未初始化企业环境。", statusCard(it));
        loadIntegrity();
      }).catch(function (e) { pushAgentMessage("assistant", "查询失败：" + (e.message || "")); });
    }
  }

  function agentSend(text) {
    setAgentDraft("");
    pushAgentMessage("user", text);
    var low = text.toLowerCase();
    var over = {};
    var m = text.match(/(\d+)\s*人/);
    if (m) over.scale = parseInt(m[1], 10);
    if (low.indexOf("生成") >= 0 || low.indexOf("初始化") >= 0 || low.indexOf("企业") >= 0 || low.indexOf("seed") >= 0) {
      doGenerate(over);
    } else if (low.indexOf("状态") >= 0 || low.indexOf("查询") >= 0) {
      agentCommand("status");
    } else {
      pushAgentMessage("assistant", "我可以帮你初始化企业环境或查询当前状态。点击上方快捷指令，或直接说“帮我生成一个50人的智能制造企业”。");
    }
  }

  function upd(k) {
    return function (e) {
      var v = e && e.target ? e.target.value : e;
      setCfg(function (c) { var n = Object.assign({}, c); n[k] = v; return n; });
    };
  }

  var loadedRef = React.useRef(false);
  function loadAll() {
    if (loadedRef.current) return;
    loadedRef.current = true;
    request("/zhiyun-enterprise-seeder/config").then(function (data) {
      setMeta({ templates: data.templates || [], departments: data.departments || {}, agents: data.agents || {}, apps: data.apps || [] });
      setCfg(Object.assign({}, data.defaults || {}));
      setLoading(false);
      return request("/zhiyun-enterprise-seeder/summary?limit=3");
    }).then(function (s) {
      var list = s.summary || [];
      var latest = list[0];
      if (latest) setStats(latest);
      if (latest) publishDataContext(latest.env_id, latest.data_mode, { key: "all", start: "", end: "" });
      if (latest) loadTrends(latest.env_id, latest.data_mode, { key: "all", start: "", end: "" }, null);
      loadIntegrity();
      return fetchRows("org_users", latest && latest.env_id, latest && latest.data_mode);
    }).catch(function (err) {
      setLoading(false);
      toast.error(err.message || "载入配置失败");
    });
  }
  React.useEffect(function () {
    if (readToken()) { loadAll(); return; }
    function onAuth() { loadAll(); }
    window.addEventListener("zhiyun:auth", onAuth);
    return function () { window.removeEventListener("zhiyun:auth", onAuth); };
  }, []);
  React.useEffect(function () {
    if (stats && stats.env_id) loadTrends(stats.env_id, stats.data_mode, range, granularity);
  }, [granularity]);

  if (loading || !cfg) {
    return h("div", { style: { padding: 40 } }, h(antd.Skeleton, { active: true, paragraph: { rows: 8 } }));
  }

  var header = { padding: "22px 26px", background: "#fff", borderBottom: "1px solid #e8ecf1", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap" };
  var sub = { color: "#667085", marginTop: 6, fontSize: 13, lineHeight: 1.6, maxWidth: 720 };
  var badge = { background: "#eef4ff", color: "#2563eb", borderRadius: 6, padding: "3px 9px", fontSize: 12, fontWeight: 600 };
  var label = { fontSize: 12, color: "#667085", marginBottom: 6, fontWeight: 600 };
  var field = { marginBottom: 14 };

  var statItems = [
    ["部门", "departments"], ["员工", "org_users"], ["智能体", "agents"], ["应用", "apps"],
    ["数据源", "data_sources"], ["会话", "sessions"], ["任务", "tasks"], ["Token", "token_total"],
    ["文件", "files"], ["下载", "downloads"], ["登录", "logins"]
  ];

  return h("div", { style: { minHeight: "100vh", background: "#f7f8fa", display: "flex", flexDirection: "column" } },
    h("div", { style: header },
      h("div", null,
        h("div", { style: { display: "flex", alignItems: "center", gap: 10 } },
          h("span", { style: { fontSize: 20, fontWeight: 750, color: "#1f2933" } }, "企业环境初始化器"),
          h("span", { style: badge }, "Epic 1")
        ),
h("div", { style: sub }, "一键生成企业组织、部门、员工、角色权限、智能体、应用、数据源、会话、任务、Token、文件工件、下载与登录活动，按 Demo / Live 数据环境隔离，员工自动绑定智能体。")
      ),
      h("div", { style: { display: "flex", gap: 10 } },
        h(antd.Button, { onClick: function () { setAgentOpen(true); } }, "✦ 智能体助手"),
        h(antd.Button, { type: "primary", loading: generating, onClick: function () { doGenerate(); } }, "生成并运行")
      )
    ),
    h("div", { style: { padding: 20, flex: 1 } },
      h("div", { style: { display: "grid", gridTemplateColumns: "minmax(320px,380px) 1fr", gap: 18, alignItems: "start" } },
        h(antd.Card, { style: { borderRadius: 10, border: "1px solid #e8ecf1", boxShadow: "0 1px 3px rgba(16,24,40,0.04)" } },
          h("div", { style: { fontSize: 15, fontWeight: 700, color: "#1f2933", marginBottom: 16 } }, "生成参数"),
          h("div", { style: field },
            h("div", { style: label }, "企业名称"),
            h(antd.Input, { value: cfg.enterprise, placeholder: "例如：智云智造", onChange: upd("enterprise") })
          ),
          h("div", { style: field },
            h("div", { style: label }, "行业模板"),
            h(antd.Select, { value: cfg.template, style: { width: "100%" }, onChange: upd("template"), options: (meta.templates || []).map(function (t) { return { value: t, label: templateLabel(t) }; }) })
          ),
          h("div", { style: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 } },
            h("div", null,
              h("div", { style: label }, "起始日期"),
              h(antd.Input, { type: "date", value: cfg.start_date, onChange: upd("start_date") })
            ),
            h("div", null,
              h("div", { style: label }, "结束日期"),
              h(antd.Input, { type: "date", value: cfg.end_date, onChange: upd("end_date") })
            )
          ),
          h("div", { style: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 } },
            h("div", null,
              h("div", { style: label }, "企业规模"),
              h(antd.Input, { type: "number", min: 1, value: cfg.scale, onChange: upd("scale") })
            ),
            h("div", null,
              h("div", { style: label }, "部门数"),
              h(antd.Input, { type: "number", min: 1, value: cfg.departments, onChange: upd("departments") })
            )
          ),
          h("div", { style: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 } },
            h("div", null,
              h("div", { style: label }, "智能体数"),
              h(antd.Input, { type: "number", min: 1, value: cfg.agents, onChange: upd("agents") })
            ),
            h("div", null,
              h("div", { style: label }, "活跃度"),
              h(antd.Select, { value: cfg.activity, style: { width: "100%" }, onChange: upd("activity"), options: [{ value: "low", label: "低频" }, { value: "medium", label: "中频" }, { value: "high", label: "高频" }] })
            )
          ),
          h("div", { style: field },
            h("div", { style: label }, "数据环境"),
            h(antd.Select, { value: cfg.data_mode, style: { width: "100%" }, onChange: upd("data_mode"), options: [{ value: "demo", label: "Demo 演示环境" }, { value: "production", label: "Live 生产环境" }] })
          ),
          h(antd.Button, { type: "primary", block: true, size: "large", loading: generating, onClick: function () { doGenerate(); } }, "生成并运行"),
          h("div", { style: { marginTop: 12, fontSize: 12, color: "#98a2b3", lineHeight: 1.6 } }, "不同数据环境与实例完全隔离；员工账号同步至登录系统并绑定对应智能体，同一企业共享运行实例。")
        ),
        h("div", { style: { display: "flex", flexDirection: "column", gap: 18, minWidth: 0 } },
          h(antd.Card, { style: { borderRadius: 10, border: "1px solid #e8ecf1", boxShadow: "0 1px 3px rgba(16,24,40,0.04)" } },
            h("div", { style: { display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 } },
              h("div", { style: { fontSize: 15, fontWeight: 700, color: "#1f2933" } }, "环境概览"),
              h("div", { style: { display: "flex", alignItems: "center", gap: 8 } },
                h("span", { style: { fontSize: 12, color: "#667085" } }, (stats && stats.enterprise ? stats.enterprise : "尚未生成") + (stats ? " · " + (stats.data_mode || "").toUpperCase() : "")),
                h(antd.Button, { size: "small", onClick: function () { switchEntity(entity); } }, "刷新")
              )
            ),
            h("div", { style: { display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 14, paddingBottom: 12, borderBottom: "1px solid #eef1f6" } },
              RANGE_PRESETS.map(function (p) {
                var a = range.key === p.key;
                return h("button", { key: p.key, onClick: function () { applyRange(p.key); }, style: { border: "1px solid " + (a ? "#2563eb" : "#e2e6ec"), background: a ? "#eef4ff" : "#fff", color: a ? "#2563eb" : "#475467", borderRadius: 8, padding: "4px 11px", fontSize: 12.5, fontWeight: a ? 650 : 500, cursor: "pointer" } }, p.label);
              }),
              (range.key === "custom" ? [
                h(antd.Input, { key: "cs", type: "date", size: "small", value: customStart, onChange: function (e) { setCustomStart(e.target.value); }, style: { width: 132 } }),
                h("span", { key: "sep", style: { color: "#98a2b3", fontSize: 12 } }, "至"),
                h(antd.Input, { key: "ce", type: "date", size: "small", value: customEnd, onChange: function (e) { setCustomEnd(e.target.value); }, style: { width: 132 } }),
                h(antd.Button, { key: "go", size: "small", type: "primary", onClick: function () { applyRange("custom"); } }, "应用")
              ] : null),
              h("span", { style: { marginLeft: "auto", fontSize: 12, color: "#98a2b3" } }, (range.key === "all" ? "全量数据" : (range.start + " ~ " + range.end)) + " · 会话/任务/Token 按该时间段统计")
            ),
            h(antd.Row, { gutter: [14, 14], style: { marginTop: 16 } },
              statItems.map(function (item) {
                return h(antd.Col, { xs: 12, sm: 8, lg: 6 },
                  h("div", { style: { background: "#fbfcfe", border: "1px solid #eef1f6", borderRadius: 9, padding: "12px 14px" } },
                    h("div", { style: { fontSize: 12, color: "#667085" } }, item[0]),
                    h("div", { style: { fontSize: 22, fontWeight: 750, color: "#1f2933", marginTop: 4 } }, stats ? (stats[item[1]] != null ? stats[item[1]] : 0) : 0)
                  )
                );
              })
            )
          ),
          h(antd.Card, { style: { borderRadius: 10, border: "1px solid #e8ecf1", boxShadow: "0 1px 3px rgba(16,24,40,0.04)" } },
            h("div", { style: { display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 } },
              h("div", { style: { fontSize: 15, fontWeight: 700, color: "#1f2933" } }, "趋势分析"),
              h("div", { style: { display: "flex", alignItems: "center", gap: 8 } },
                h("span", { style: { fontSize: 12, color: "#667085" } }, "粒度"),
                h("button", { key: "gd", onClick: function () { setGranularity("day"); }, style: { border: "1px solid " + (granularity === "day" ? "#2563eb" : "#e2e6ec"), background: granularity === "day" ? "#eef4ff" : "#fff", color: granularity === "day" ? "#2563eb" : "#475467", borderRadius: 8, padding: "3px 9px", fontSize: 12, fontWeight: granularity === "day" ? 650 : 500, cursor: "pointer" } }, "日"),
                h("button", { key: "gw", onClick: function () { setGranularity("week"); }, style: { border: "1px solid " + (granularity === "week" ? "#2563eb" : "#e2e6ec"), background: granularity === "week" ? "#eef4ff" : "#fff", color: granularity === "week" ? "#2563eb" : "#475467", borderRadius: 8, padding: "3px 9px", fontSize: 12, fontWeight: granularity === "week" ? 650 : 500, cursor: "pointer" } }, "周"),
                h("button", { key: "gm", onClick: function () { setGranularity("month"); }, style: { border: "1px solid " + (granularity === "month" ? "#2563eb" : "#e2e6ec"), background: granularity === "month" ? "#eef4ff" : "#fff", color: granularity === "month" ? "#2563eb" : "#475467", borderRadius: 8, padding: "3px 9px", fontSize: 12, fontWeight: granularity === "month" ? 650 : 500, cursor: "pointer" } }, "月")
              )
            ),
            h("div", { style: { marginTop: 12 } },
              h(TrendPanel, { data: trends, loading: trendsLoading })
            )
          ),
          h(antd.Card, { style: { borderRadius: 10, border: "1px solid #e8ecf1", boxShadow: "0 1px 3px rgba(16,24,40,0.04)" } },
            h("div", { style: { display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 } },
              h("div", { style: { fontSize: 15, fontWeight: 700, color: "#1f2933" } }, "数据一致性"),
              h("div", { style: { display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" } },
                h(antd.Button, { size: "small", loading: repairing, onClick: function () { runRepair(); } }, "自动修复"),
                h(antd.Button, { size: "small", loading: integrityLoading, onClick: function () { loadIntegrity(); } }, "运行检查"),
                h(antd.Button, { size: "small", onClick: function () { loadDailyReport(); } }, "今日快照")
              )

            ),
            h("div", { style: { marginTop: 12, fontSize: 12, color: "#98a2b3", lineHeight: 1.6 } }, integrity ? "" : "尚无一致性报告，点击「运行检查」或先生成企业环境。"),
(dailyIntegrity && dailyIntegrity.report_day) ? h("div", { key: "dailyIntegritySnap", style: { marginTop: 8, fontSize: 12, color: "#667085" } },
  h("span", {}, "今日快照 · " + dailyIntegrity.report_day + " · 通过 " + (dailyIntegrity.passed || 0) + " / " + (dailyIntegrity.total || 0) + " 项" + ((dailyIntegrity.failed || 0) ? " · 失败 " + dailyIntegrity.failed + " 项" : ""))
) : null,

            (integrity && integrity.report) ? h("div", { style: { marginTop: 12 } },
              h("div", { style: { display: "flex", alignItems: "center", gap: 10 } },
                h("span", { style: { width: 10, height: 10, borderRadius: 999, background: integrity.healthy ? "#16a34a" : "#ef4444" } }),
                h("span", { style: { fontSize: 13, fontWeight: 650, color: "#1f2933" } }, "通过 " + (integrity.passed || 0) + " / " + (integrity.total || 0) + " 项"),
                h("span", { style: { fontSize: 12, color: "#98a2b3" } }, "失败 " + (integrity.failed || 0) + " 项 · " + (integrity.data_mode || "").toUpperCase())
              ),
              h("div", { style: { display: "flex", flexDirection: "column", gap: 8, marginTop: 12 } },
                integrity.report.map(function (c) {
                  var okc = c.status === "pass";
                  return h("div", { key: c.id, style: { display: "flex", alignItems: "flex-start", gap: 10, padding: "10px 12px", borderRadius: 8, background: okc ? "#f6fef9" : "#fff5f5", border: "1px solid " + (okc ? "#bbf7d0" : "#fecaca") } },
                    h("span", { style: { fontSize: 15, lineHeight: 1, marginTop: 1 } }, okc ? "✓" : "✕"),
                    h("div", { style: { minWidth: 0 } },
                      h("div", { style: { fontSize: 12.5, fontWeight: 650, color: "#1f2933" } }, c.name),
                      h("div", { style: { fontSize: 12, color: "#667085", marginTop: 3, lineHeight: 1.5 } }, c.detail)
                    )
                  );
                })
              )
            ) : null
          ),
          h(antd.Card, { style: { borderRadius: 10, border: "1px solid #e8ecf1", boxShadow: "0 1px 3px rgba(16,24,40,0.04)" } },
            h("div", { style: { display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 } },
              h("div", { style: { fontSize: 15, fontWeight: 700, color: "#1f2933" } }, "企业数据明细"),
              h("div", { style: { fontSize: 12, color: "#98a2b3" } }, (rows.length || 0) + " 条")
            ),
            h("div", { style: { display: "flex", flexWrap: "wrap", gap: 8, marginTop: 14, marginBottom: 14 } },
              ENTITIES.map(function (it) {
                var active = it.key === entity;
                return h("button", { key: it.key, onClick: function () { switchEntity(it.key); }, style: { border: "1px solid " + (active ? "#2563eb" : "#e2e6ec"), background: active ? "#eef4ff" : "#fff", color: active ? "#2563eb" : "#475467", borderRadius: 8, padding: "5px 12px", fontSize: 12.5, fontWeight: active ? 650 : 500, cursor: "pointer" } }, it.label);
              })
            ),
            h(antd.Table, { rowKey: function (r, i) { return r.id != null ? r.id : i; }, columns: makeCols(rows), dataSource: rows, loading: rowsLoading, size: "small", pagination: { pageSize: 10, size: "small", showSizeChanger: false }, scroll: { x: "max-content" }, locale: { emptyText: "暂无数据，请先生成企业环境" } })
          )
        )
      )
    ),
    h(SimulationRuntimePanel, { key: "sim-" + ((stats && stats.env_id) || "x"), pushAgentMessage: pushAgentMessage }),
    h(AgentFactoryPanel, { key: (stats && stats.env_id) || "af", envId: (stats && stats.env_id) || "", mode: (stats && stats.data_mode) || "", pushAgentMessage: pushAgentMessage }),
    h(AgentDock, { open: agentOpen, onClose: function () { setAgentOpen(false); }, moduleLabel: "企业环境初始化器", chips: [{ key: "init", label: "初始化企业" }, { key: "status", label: "查询状态" }], messages: agentMessages, draft: agentDraft, setDraft: setAgentDraft, busy: generating || rowsLoading, onSend: agentSend, onCommand: agentCommand })
  );
}

Q.registerRoutes("zhiyun-enterprise-seeder", [{ path: "/apps/zhiyun-enterprise-seeder", component: EnterpriseSeeder, label: "企业环境初始化器", icon: "🏢", priority: 85 }]);
})();
