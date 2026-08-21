(function () {
  var Q = window.QwenPaw;
  if (!Q || !Q.host || !Q.registerRoutes) return;
  var React = Q.host.React, antd = Q.host.antd, h = React.createElement;
  var Button = antd.Button, Table = antd.Table, Tag = antd.Tag, Card = antd.Card, Space = antd.Space, Alert = antd.Alert;

  function api(path) {
    var token = Q.host.getApiToken ? Q.host.getApiToken() : "";
    return fetch(Q.host.getApiUrl(path), { headers: token ? { Authorization: "Bearer " + token } : {} })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); });
  }
  function OrdersApp() {
    var state = React.useState({ loading: true, data: null, error: "" });
    var view = state[0], setView = state[1];
    function load() {
      setView({ loading: true, data: null, error: "" });
      api("/zhiyun-orders/orders").then(function (data) { setView({ loading: false, data: data, error: "" }); })
        .catch(function (e) { setView({ loading: false, data: null, error: e.message }); });
    }
    React.useEffect(load, []);
    var columns = [
      { title: "订单号", dataIndex: "order_no", width: 145 },
      { title: "客户", dataIndex: "customer" },
      { title: "产品", dataIndex: "product" },
      { title: "节点", dataIndex: "current_node", width: 90 },
      { title: "进度", dataIndex: "progress", width: 90, render: function (v) { return v + "%"; } },
      { title: "延期", dataIndex: "delay_hours", width: 90, render: function (v) { return v ? v + "h" : "-"; } },
      { title: "风险", dataIndex: "risk_level", width: 90, render: function (v) { return h(Tag, { color: v === "红色" ? "red" : v === "黄色" ? "gold" : "green" }, v); } },
      { title: "风险原因", dataIndex: "risk_reason" }
    ];
    var data = view.data || { summary: { total: 0, red: 0, yellow: 0, green: 0 }, orders: [] };
    return h("div", { style: { padding: 24 } },
      h(Space, { style: { width: "100%", justifyContent: "space-between", marginBottom: 16 } },
        h("div", null, h("h2", { style: { margin: 0 } }, "订单与交付风险"), h("div", { style: { color: "#64748b" } }, "数据直接来自当前 QwenPaw Workspace")),
        h(Button, { onClick: load, loading: view.loading }, "刷新")),
      view.error ? h(Alert, { type: "error", message: "加载失败", description: view.error, showIcon: true }) : null,
      h(Space, { size: 12, style: { marginBottom: 16 } },
        h(Card, { size: "small" }, "全部订单：" + data.summary.total),
        h(Card, { size: "small" }, h("span", { style: { color: "#dc2626" } }, "红色风险：" + data.summary.red)),
        h(Card, { size: "small" }, h("span", { style: { color: "#d97706" } }, "黄色风险：" + data.summary.yellow)),
        h(Card, { size: "small" }, h("span", { style: { color: "#16a34a" } }, "正常：" + data.summary.green))),
      h(Table, { rowKey: "order_no", loading: view.loading, columns: columns, dataSource: data.orders, pagination: false, scroll: { x: 1100 } }),
      view.data ? h("div", { style: { marginTop: 12, color: "#64748b", fontSize: 12 } }, "Trace ID：" + view.data.traceId) : null);
  }
  Q.registerRoutes([{ path: "/apps/zhiyun-orders", element: h(OrdersApp) }]);
})();
