// -*- coding: utf-8 -*-
// 智能分析驾驶舱 — 独立应用页（数据来自 /api/zhiyun-enterprise-seeder/analytics/insights）
(function () {
  var Q = window.QwenPaw;
  if (!Q || !Q.slot || !Q.host || !Q.host.React) return;
  var React = Q.host.React;
  var h = React.createElement;
  var API = "/api/zhiyun-enterprise-seeder";  // 跨插件调用用绝对路径（getApiUrl 会解析到当前插件前缀）
  function authHeaders() {
    var headers = {};
    try {
      var t = window.localStorage.getItem("zhiyun_token");
      if (t) headers["Authorization"] = "Bearer " + t;
    } catch (e) { /* 忽略 */ }
    return headers;
  }
  function api(path) {
    return fetch(API + path, { headers: authHeaders() })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); });
  }
  var cardStyle = { background: "#fff", border: "1px solid #e3e8ef", borderRadius: 10, padding: 16, marginBottom: 16 };

  function InsightsPanel(props) {
    var st = React.useState(null); var data = st[0]; var setData = st[1];
    var est = React.useState(true); var loading = est[0]; var setLoading = est[1];
    var errst = React.useState(""); var err = errst[0]; var setErr = errst[1];
    function load() {
      setLoading(true);
      api("/analytics/insights")
        .then(function (d) { setData(d); setErr(""); })
        .catch(function (e) { setErr("加载失败：" + (e && e.message ? e.message : e)); })
        .finally(function () { setLoading(false); });
    }
    React.useEffect(load, []);
    if (loading) return h("div", { style: cardStyle }, "智能分析加载中…");
    if (err) return h("div", { style: cardStyle }, h("div", { style: { color: "#b42318" } }, err), h("button", { onClick: load, style: { marginTop: 8 } }, "重试"));
    if (!data) return null;
    function bar(n, max, color) {
      return h("div", { style: { background: "#eef2f6", borderRadius: 4, height: 8, width: "100%", marginTop: 4 } },
        h("div", { style: { width: Math.max(3, Math.round(n / (max || 1) * 100)) + "%", height: "100%", background: color || "#1f5ed6", borderRadius: 4 } }));
    }
    function rank(list, title) {
      var max = Math.max.apply(null, list.map(function (x) { return x.sessions; }).concat([1]));
      return h("div", { style: { flex: "1 1 200px" } }, h("div", { style: { fontWeight: 650, marginBottom: 6 } }, title),
        list.map(function (x, i) { return h("div", { key: i, style: { fontSize: 12.5, marginBottom: 6 } },
          h("span", null, (i + 1) + ". " + x.name + "（" + x.sessions + "）"), bar(x.sessions, max)); }));
    }
    return h("div", { style: cardStyle },
      h("div", { style: { fontWeight: 700, fontSize: 14, marginBottom: 6 } }, "🧠 智能分析驾驶舱",
        h("button", { onClick: load, style: { float: "right", fontSize: 12 } }, "刷新")),
      h("div", { style: { background: "#f0f7ff", border: "1px solid #cfe3ff", borderRadius: 8, padding: 10, fontSize: 13, lineHeight: 1.7, marginBottom: 10 } }, data.summary),
      h("div", { style: { display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 } },
        (data.trends || []).map(function (t, i) {
          var up = t.change_pct == null ? null : t.change_pct >= 0;
          return h("div", { key: i, style: { flex: "1 1 150px", border: "1px solid #e3e8ef", borderRadius: 8, padding: 10, fontSize: 12.5 } },
            h("div", { style: { color: "#5b6472" } }, t.metric),
            h("div", { style: { fontSize: 20, fontWeight: 700 } }, String(t.current)),
            t.change_pct == null ? null : h("div", { style: { color: up ? "#12b76a" : "#f04438" } }, (up ? "▲ +" : "▼ ") + t.change_pct + "% 环比"));
        })),
      h("div", { style: { display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 10 } },
        rank((data.top_agents || []).slice(0, 5), "最活跃智能体"),
        rank((data.top_users || []).slice(0, 5), "最活跃用户"),
        rank((data.top_apps || []).slice(0, 5), "应用贡献榜")),
      (data.anomalies || []).length ? h("div", { style: { border: "1px solid #fecdca", background: "#fff6f5", borderRadius: 8, padding: 10, fontSize: 12.5 } },
        h("b", null, "⚠ 异常日（|z|≥2）"),
        data.anomalies.slice(0, 5).map(function (a, i) { return h("div", { key: i }, a.date + " " + a.kind + "（" + a.sessions + " 次会话, z=" + a.z + "）" + a.context); })) : null,
      h("div", { style: { border: "1px solid #e3e8ef", borderRadius: 8, padding: 10, fontSize: 12.5, background: "#fafbfc" } },
        h("b", null, "🔄 数据流转"), h("div", { style: { marginTop: 4 } }, data.data_flow.summary))
    );
  }

  function InsightsPage() {
    return h("div", { style: { padding: 20, minHeight: "100vh", background: "#f7f8fa" } },
      h(InsightsPanel, null));
  }

  if (Q.registerRoutes) {
    Q.registerRoutes("zhiyun-data-insights", [{ path: "/apps/zhiyun-data-insights", component: InsightsPage, label: "智能分析驾驶舱", icon: "🧠", priority: 84 }]);
  }
})();
