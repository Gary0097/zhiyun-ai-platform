(function () {
  var Q = window.QwenPaw;
  if (!Q || !Q.host || !Q.host.React || !Q.registerRoutes) return;
  var React = Q.host.React;
  var antd = Q.host.antd;
  var h = React.createElement;

  function request(path, options) {
    return Q.host.fetch(path, options).then(function (response) {
      if (!response.ok) return response.json().catch(function () { return {}; }).then(function (body) {
        throw new Error(body.detail || ("HTTP " + response.status));
      });
      return response.json();
    });
  }

  function DataBrowser() {
    var entitiesState = React.useState([]);
    var entities = entitiesState[0];
    var setEntities = entitiesState[1];
    var selectedState = React.useState("orders");
    var selected = selectedState[0];
    var setSelected = selectedState[1];
    var schemaState = React.useState(null);
    var schema = schemaState[0];
    var setSchema = schemaState[1];
    var recordsState = React.useState([]);
    var records = recordsState[0];
    var setRecords = recordsState[1];
    var sourceState = React.useState("");
    var source = sourceState[0];
    var setSource = sourceState[1];
    var loadingState = React.useState(false);
    var loading = loadingState[0];
    var setLoading = loadingState[1];
    var errorState = React.useState("");
    var error = errorState[0];
    var setError = errorState[1];

    function loadEntities() {
      return request("/zhiyun-data-core/entities").then(function (data) { setEntities(data.entities || []); });
    }

    function loadDataset(entity, sourceType) {
      setLoading(true); setError("");
      var suffix = sourceType ? "?limit=100&source_type=" + encodeURIComponent(sourceType) : "?limit=100";
      Promise.all([
        request("/zhiyun-data-core/schemas/" + encodeURIComponent(entity)),
        request("/zhiyun-data-core/records/" + encodeURIComponent(entity) + suffix),
        loadEntities()
      ]).then(function (values) {
        setSchema(values[0]); setRecords(values[1].records || []);
      }).catch(function (reason) { setError(reason.message || "数据加载失败"); })
        .finally(function () { setLoading(false); });
    }

    React.useEffect(function () { loadDataset(selected, source); }, [selected, source]);

    function simulate() {
      setLoading(true); setError("");
      request("/zhiyun-data-core/simulate/orders", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ count: 20 })
      }).then(function () { loadDataset("orders", source); })
        .catch(function (reason) { setError(reason.message || "模拟数据生成失败"); setLoading(false); });
    }

    var activeFields = schema ? schema.fields.filter(function (field) { return field.active; }) : [];
    var columns = activeFields.map(function (field) {
      return { title: field.label, dataIndex: ["data", field.name], key: field.name, width: 150, ellipsis: true };
    });
    columns.push({ title: "数据来源", dataIndex: "source_type", key: "source_type", fixed: "right", width: 100,
      render: function (value) { return h(antd.Tag, { color: value === "real" ? "green" : "blue" }, value === "real" ? "真实" : "模拟"); }
    });
    var current = entities.find(function (item) { return item.entity === selected; }) || {};

    return h("div", { style: { padding: 28, height: "100%", overflow: "auto", background: "#f7f8fa" } },
      h("div", { style: { maxWidth: 1400, margin: "0 auto" } },
        h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 } },
          h("div", null, h("h2", { style: { marginBottom: 4 } }, "统一数据中心"),
            h("p", { style: { color: "#667085", marginTop: 0 } }, "查看各 PawApp 共享数据库中的表结构、真实数据与模拟数据。")),
          h("div", { style: { display: "flex", gap: 8 } },
            h(antd.Button, { onClick: function () { loadDataset(selected, source); } }, "刷新"),
            selected === "orders" ? h(antd.Button, { type: "primary", onClick: simulate, loading: loading }, "生成 20 条模拟订单") : null)
        ),
        error ? h(antd.Alert, { type: "error", showIcon: true, message: error, style: { marginBottom: 16 } }) : null,
        h(antd.Row, { gutter: [12, 12], style: { marginBottom: 16 } },
          [["数据表", entities.length], ["当前记录", current.record_count || 0], ["真实数据", current.real_count || 0], ["模拟数据", current.simulated_count || 0]].map(function (item) {
            return h(antd.Col, { xs: 12, md: 6, key: item[0] }, h(antd.Card, { size: "small" }, h(antd.Statistic, { title: item[0], value: item[1] })));
          })
        ),
        h(antd.Card, { size: "small", style: { marginBottom: 16 } },
          h("div", { style: { display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" } },
            h("span", null, "数据表"),
            h(antd.Select, { value: selected, style: { width: 180 }, onChange: setSelected,
              options: entities.map(function (item) { return { value: item.entity, label: item.label + " (" + item.entity + ")" }; }) }),
            h("span", null, "来源"),
            h(antd.Select, { value: source, style: { width: 140 }, onChange: setSource,
              options: [{ value: "", label: "全部" }, { value: "real", label: "真实数据" }, { value: "simulated", label: "模拟数据" }] })
          )
        ),
        h(antd.Tabs, { items: [
          { key: "records", label: "数据预览（最多 100 条）", children: h(antd.Table, { rowKey: "record_id", size: "small", loading: loading, columns: columns, dataSource: records, scroll: { x: Math.max(900, columns.length * 150) }, pagination: { pageSize: 20 } }) },
          { key: "schema", label: "字段结构", children: h(antd.Table, { rowKey: "name", size: "small", loading: loading, pagination: false, dataSource: schema ? schema.fields : [], columns: [
            { title: "字段名", dataIndex: "name" }, { title: "显示名称", dataIndex: "label" }, { title: "类型", dataIndex: "type" },
            { title: "必填", dataIndex: "required", render: function (value) { return value ? "是" : "否"; } },
            { title: "状态", dataIndex: "active", render: function (value) { return h(antd.Tag, { color: value ? "green" : "default" }, value ? "启用" : "停用"); } },
            { title: "内置字段", dataIndex: "built_in", render: function (value) { return value ? "是" : "否"; } }
          ] }) }
        ] })
      )
    );
  }

  Q.registerRoutes("zhiyun-data-core", [{ path: "/apps/data-core", component: DataBrowser, label: "统一数据中心", icon: "🗄️", priority: 75 }]);
})();
