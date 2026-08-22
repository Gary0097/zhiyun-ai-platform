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
    var createState = React.useState(false);
    var createOpen = createState[0];
    var setCreateOpen = createState[1];
    var schemaForm = antd.Form.useForm()[0];
    var message = antd.App.useApp().message;
    var importState = React.useState(null);
    var importData = importState[0];
    var setImportData = importState[1];
    var mappingState = React.useState({});
    var mapping = mappingState[0];
    var setMapping = mappingState[1];
    var previewState = React.useState(null);
    var preview = previewState[0];
    var setPreview = previewState[1];

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

    function createDataset() {
      schemaForm.validateFields().then(function (values) {
        return request("/zhiyun-data-core/schemas", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(values)
        });
      }).then(function (created) {
        message.success("数据表已创建"); setCreateOpen(false); schemaForm.resetFields(); setSelected(created.entity); return loadEntities();
      }).catch(function (reason) { if (reason instanceof Error) message.error(reason.message); });
    }

    function upload(file) {
      var form = new FormData(); form.append("file", file);
      request("/zhiyun-data-core/parse", { method: "POST", body: form }).then(function (data) {
        var next = {};
        (data.headers || []).forEach(function (header) {
          var match = (schema.fields || []).find(function (field) { return field.active && (field.name === header || field.label === header); });
          if (match) next[header] = match.name;
        });
        setImportData(data); setMapping(next); setPreview(null);
      }).catch(function (reason) { message.error(reason.message || "文件解析失败"); });
      return false;
    }

    function previewImport() {
      request("/zhiyun-data-core/imports/" + encodeURIComponent(selected) + "/preview", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rows: importData.rows, mapping: mapping, source_name: importData.filename })
      }).then(setPreview).catch(function (reason) { message.error(reason.message); });
    }

    function commitImport() {
      request("/zhiyun-data-core/imports/" + encodeURIComponent(selected) + "/commit", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rows: importData.rows, mapping: mapping, source_name: importData.filename })
      }).then(function (result) {
        message.success("已导入 " + result.row_count + " 条真实数据"); setImportData(null); setPreview(null); return loadDataset(selected, source);
      }).catch(function (reason) { message.error(reason.message); });
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
            h(antd.Button, { onClick: function () { setCreateOpen(true); } }, "新建数据表"),
            h(antd.Upload, { accept: ".xlsx,.csv", showUploadList: false, beforeUpload: upload }, h(antd.Button, { type: selected === "orders" ? "default" : "primary" }, "导入 Excel/CSV")),
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
        ] }),
        h(antd.Modal, { title: "新建部门数据表", width: 760, open: createOpen, onOk: createDataset, onCancel: function () { setCreateOpen(false); } },
          h(antd.Form, { form: schemaForm, layout: "vertical", initialValues: { fields: [{ name: "record_date", label: "日期", field_type: "date", required: true }] } },
            h(antd.Row, { gutter: 12 },
              h(antd.Col, { span: 12 }, h(antd.Form.Item, { name: "label", label: "数据表名称", rules: [{ required: true }] }, h(antd.Input, { placeholder: "例如：生产日报" }))),
              h(antd.Col, { span: 12 }, h(antd.Form.Item, { name: "entity", label: "数据表标识", rules: [{ required: true, pattern: /^[a-z][a-z0-9_]{0,62}$/, message: "使用小写英文、数字和下划线" }] }, h(antd.Input, { placeholder: "例如：production" })))
            ),
            h(antd.Form.List, { name: "fields" }, function (fields, actions) {
              return h(React.Fragment, null,
                fields.map(function (field) { return h(antd.Space, { key: field.key, align: "baseline", style: { display: "flex", marginBottom: 8 } },
                  h(antd.Form.Item, { name: [field.name, "label"], rules: [{ required: true }] }, h(antd.Input, { placeholder: "显示名称" })),
                  h(antd.Form.Item, { name: [field.name, "name"], rules: [{ required: true, pattern: /^[a-z][a-z0-9_]{0,62}$/ }] }, h(antd.Input, { placeholder: "field_name" })),
                  h(antd.Form.Item, { name: [field.name, "field_type"], initialValue: "text" }, h(antd.Select, { style: { width: 120 }, options: ["text", "integer", "number", "boolean", "date", "datetime"].map(function (value) { return { value: value, label: value }; }) })),
                  h(antd.Form.Item, { name: [field.name, "required"], valuePropName: "checked" }, h(antd.Checkbox, null, "必填")),
                  fields.length > 1 ? h(antd.Button, { danger: true, size: "small", onClick: function () { actions.remove(field.name); } }, "删除") : null
                ); }),
                h(antd.Button, { type: "dashed", onClick: function () { actions.add({ field_type: "text", required: false }); } }, "添加字段")
              );
            })
          )
        ),
        h(antd.Modal, { title: importData ? ("导入 " + importData.filename + " → " + (schema ? schema.label : selected)) : "导入数据", width: 820, open: !!importData, okText: "确认写入", okButtonProps: { disabled: !preview || preview.error_count > 0 }, onOk: commitImport, onCancel: function () { setImportData(null); setPreview(null); }, footer: function (_, buttons) { return h(React.Fragment, null, h(antd.Button, { onClick: previewImport }, "预览校验"), buttons.OkBtn ? h(buttons.OkBtn) : null, buttons.CancelBtn ? h(buttons.CancelBtn) : null); } },
          importData ? h(React.Fragment, null,
            h(antd.Alert, { type: "info", showIcon: true, message: "共 " + importData.row_count + " 行，请确认源字段和数据库字段的对应关系。", style: { marginBottom: 14 } }),
            h("div", { style: { display: "grid", gridTemplateColumns: "repeat(2,minmax(280px,1fr))", gap: 10 } }, (importData.headers || []).map(function (header) {
              return h("div", { key: header, style: { display: "flex", gap: 8, alignItems: "center" } },
                h("span", { style: { width: 120, overflow: "hidden", textOverflow: "ellipsis" } }, header),
                h(antd.Select, { allowClear: true, value: mapping[header], placeholder: "选择目标字段", style: { flex: 1 }, options: (schema ? schema.fields : []).filter(function (field) { return field.active; }).map(function (field) { return { value: field.name, label: field.label + " (" + field.name + ")" }; }), onChange: function (value) { var next = Object.assign({}, mapping); if (value) next[header] = value; else delete next[header]; setMapping(next); setPreview(null); } })
              );
            })),
            preview ? h(antd.Alert, { style: { marginTop: 14 }, type: preview.error_count ? "error" : "success", showIcon: true, message: preview.error_count ? ("发现 " + preview.error_count + " 行错误") : (preview.valid_count + " 行校验通过"), description: (preview.errors || []).slice(0, 5).map(function (item) { return "第" + item.row + "行：" + item.errors.join("，"); }).join("；") }) : null
          ) : null
        )
      )
    );
  }

  Q.registerRoutes("zhiyun-data-core", [{ path: "/apps/data-core", component: DataBrowser, label: "统一数据中心", icon: "🗄️", priority: 75 }]);
})();
