(function () {
  var Q = window.QwenPaw;
  if (!Q || !Q.host || !Q.host.React || !Q.registerRoutes) return;
  var React = Q.host.React;
  var antd = Q.host.antd;
  var h = React.createElement;

  function request(path, options) {
    var opts = Object.assign({}, options || {});
    try {
      var t = window.localStorage.getItem("zhiyun_token");
      if (t) opts.headers = Object.assign({}, (options && options.headers) || {}, { Authorization: "Bearer " + t });
    } catch (e) {}
    return Q.host.fetch(path, opts).then(function (response) {
      if (!response.ok) return response.json().catch(function () { return {}; }).then(function (body) {
        throw new Error(body.detail || ("HTTP " + response.status));
      });
      return response.json();
    });
  }

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
            h(antd.Input, { value: props.draft, placeholder: props.placeholder || "例如：帮我汇总当前数据", onChange: function (e) { props.setDraft(e.target.value); }, onPressEnter: function (e) { if (props.draft.trim()) { props.onSend(props.draft); e.preventDefault(); } } }),
            h(antd.Button, { type: "primary", style: { marginTop: 10, width: "100%" }, loading: props.busy, onClick: function () { if (props.draft.trim()) props.onSend(props.draft); } }, "发送")
          )
        )
      )
    );
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
    var addFieldOpenState = React.useState(false); var addFieldOpen = addFieldOpenState[0]; var setAddFieldOpen = addFieldOpenState[1];
    var newFieldState = React.useState({ field_name: "", field_label: "", field_type: "text", field_required: false });
    var newField = newFieldState[0]; var setNewField = newFieldState[1];
    var sourceState = React.useState("");
    var source = sourceState[0];
    var setSource = sourceState[1];
    var dataModeState = React.useState("");
    var dataMode = dataModeState[0];
    var setDataMode = dataModeState[1];
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
    var healthState = React.useState(null);
    var health = healthState[0];
    var setHealth = healthState[1];
    var backupsState = React.useState([]);
    var backups = backupsState[0];
    var setBackups = backupsState[1];
    var agentOpenState = React.useState(false), agentOpen = agentOpenState[0], setAgentOpen = agentOpenState[1];
    var agentDraftState = React.useState(""), agentDraft = agentDraftState[0], setAgentDraft = agentDraftState[1];
    var agentMsgState = React.useState([]), agentMessages = agentMsgState[0], setAgentMessages = agentMsgState[1];
    var agentBusyState = React.useState(false), agentBusy = agentBusyState[0], setAgentBusy = agentBusyState[1];
    var agentSessionRef = React.useRef("data-core-" + Date.now().toString(36));
    function agentAdd(role, text, card) { setAgentMessages(function (prev) { return prev.concat([{ role: role, text: text, card: card }]); }); }
    function agentCommand(key, label) {
      var prompt = key === "preview" ? "帮我汇总当前数据概览，哪些实体可用？"
        : key === "health" ? "当前数据中心健康状态和备份情况如何？"
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
      zyPushAgent({ app_id: "zhiyun-data-core", kind: "chat", label: text, summary: { entities: entities, records: records, health: health }, source_type: "real" });
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
      var full = "";
      Q.host.fetch("/zhiyun-data-core/agent/chat", {
        method: "POST",
        headers: agentHeaders,
        body: JSON.stringify({ text: text, session_id: agentSessionRef.current, user_id: "default", app_id: "zhiyun-data-core", history: history })
      })
      .then(function (response) {
        if (!response.ok || !response.body) {
          return response.text().then(function (t) { throw new Error("HTTP " + response.status + (t && t.trim() ? ": " + t.trim() : "")); });
        }
        var reader = response.body.getReader();
        var decoder = new TextDecoder();
        var buffer = "";
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

    function loadEntities() {
      var suffix = dataMode ? "?data_mode=" + encodeURIComponent(dataMode) : "";
      return request("/zhiyun-data-core/entities" + suffix).then(function (data) { setEntities(data.entities || []); });
    }

    function loadOperations() {
      return Promise.all([request("/zhiyun-data-core/health"), request("/zhiyun-data-core/backups").catch(function () { return { backups: [] }; })]).then(function (values) {
        setHealth(values[0]); setBackups(values[1].backups || []);
      });
    }

    function loadDataset(entity, sourceType) {
      setLoading(true); setError("");
      var suffix = "?limit=100";
      if (sourceType) suffix += "&source_type=" + encodeURIComponent(sourceType);
      if (dataMode) suffix += "&data_mode=" + encodeURIComponent(dataMode);
      Promise.all([
        request("/zhiyun-data-core/schemas/" + encodeURIComponent(entity)),
        request("/zhiyun-data-core/records/" + encodeURIComponent(entity) + suffix),
        loadEntities()
      ]).then(function (values) {
        setSchema(values[0]); setRecords(values[1].records || []);
      }).catch(function (reason) { setError(reason.message || "数据加载失败"); })
        .finally(function () { setLoading(false); });
      }

      function submitAddField(values) {
        if (!selected) return Promise.reject(new Error("请先选择数据表"));
        return request("/zhiyun-data-core/schemas/" + encodeURIComponent(selected) + "/fields", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: values.field_name, label: values.field_label || values.field_name, field_type: values.field_type || "text", required: !!values.field_required })
        }).then(function () {
          message.success("字段已添加：" + values.field_name);
          loadDataset(selected, source);
        }).catch(function (e) { message.error(e.message || "添加字段失败"); throw e; });
      }
      function patchField(fieldName, patch) {
        return request("/zhiyun-data-core/schemas/" + encodeURIComponent(selected) + "/fields/" + encodeURIComponent(fieldName), {
          method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch)
        }).then(function () { loadDataset(selected, source); }).catch(function (e) { message.error(e.message || "字段更新失败"); });
      }

    React.useEffect(function () { loadDataset(selected, source); loadOperations(); }, [selected, source, dataMode]);
    React.useEffect(function () {
      // 未登录时首次加载会 401；登录成功事件后自动重载（配合端点强制鉴权）
      function onAuth() { loadDataset(selected, source); loadOperations(); }
      window.addEventListener("zhiyun:auth", onAuth);
      return function () { window.removeEventListener("zhiyun:auth", onAuth); };
    }, [selected, source, dataMode]);

    function createBackup() {
      request("/zhiyun-data-core/backups", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) })
        .then(function (result) { message.success("备份已创建并校验：" + result.name); return loadOperations(); })
        .catch(function (reason) { message.error(reason.message || "备份失败"); });
    }

    function restoreBackup(name) {
      antd.Modal.confirm({ title: "确认恢复 Data Core？", content: "恢复前会自动创建安全备份；现有 Workspace 文件不会删除。", okText: "确认恢复", okButtonProps: { danger: true }, onOk: function () {
        return request("/zhiyun-data-core/backups/" + encodeURIComponent(name) + "/restore", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirmed: true }) })
          .then(function (result) { message.success("恢复完成；安全备份：" + result.safety_backup); loadDataset(selected, source); return loadOperations(); })
          .catch(function (reason) { message.error(reason.message || "恢复失败"); });
      } });
    }

    function simulate(entity) {
      setLoading(true); setError("");
      var q = dataMode ? "?data_mode=" + encodeURIComponent(dataMode) : "";
      request("/zhiyun-data-core/simulate/" + encodeURIComponent(entity) + q, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ count: 20 })
      }).then(function () { message.success("已生成 20 条可撤销的演示数据"); loadDataset(entity, source); })
        .catch(function (reason) { setError(reason.message || "演示数据生成失败"); setLoading(false); });
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
      var q = dataMode ? "?data_mode=" + encodeURIComponent(dataMode) : "";
      request("/zhiyun-data-core/imports/" + encodeURIComponent(selected) + "/commit" + q, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rows: importData.rows, mapping: mapping, source_name: importData.filename })
      }).then(function (result) {
        message.success("已导入 " + result.row_count + " 条正式数据"); setImportData(null); setPreview(null); return loadDataset(selected, source);
      }).catch(function (reason) { message.error(reason.message); });
    }

    var activeFields = schema ? schema.fields.filter(function (field) { return field.active; }) : [];
    var columns = activeFields.map(function (field) {
      return { title: field.label, dataIndex: ["data", field.name], key: field.name, width: 150, ellipsis: true };
    });
    columns.push({ title: "数据环境", dataIndex: "data_mode", key: "data_mode", fixed: "right", width: 110,
      render: function (value) { return h(antd.Tag, { color: value === "production" ? "green" : "blue" }, value === "production" ? "正式 Live" : "演示 Demo"); }
    });
    columns.push({ title: "来源", dataIndex: "source_type", key: "source_type", fixed: "right", width: 100,
      render: function (value) { return h(antd.Tag, { color: value === "real" ? "geekblue" : "purple" }, value === "real" ? "已导入" : "系统生成"); }
    });
    var current = entities.find(function (item) { return item.entity === selected; }) || {};

    return h("div", { style: { padding: 28, height: "100%", overflow: "auto", background: "#f7f8fa" } },
      h("div", { style: { maxWidth: 1400, margin: "0 auto" } },
        h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 } },
          h("div", null, h("h2", { style: { marginBottom: 4 } }, "统一数据中心"),
            h("p", { style: { color: "#667085", marginTop: 0 } }, "查看各 PawApp 共享数据库中的表结构、演示数据与正式数据。")),
          h("div", { style: { display: "flex", gap: 8 } },
            h(antd.Button, { type: "primary", onClick: function () { setAgentOpen(true); } }, zySpark(), " 问 Agent"),
            h(antd.Button, { onClick: function () { loadDataset(selected, source); } }, "刷新"),
            h(antd.Button, { onClick: createBackup }, "创建校验备份"),
            h(antd.Button, { onClick: function () { setCreateOpen(true); } }, "新建数据表"),
            h(antd.Upload, { accept: ".xlsx,.csv", showUploadList: false, beforeUpload: upload }, h(antd.Button, { type: selected === "orders" ? "default" : "primary" }, "导入 Excel/CSV")),
            selected === "orders" || selected === "production" ? h(antd.Button, { type: "primary", onClick: function () { simulate(selected); }, loading: loading }, selected === "orders" ? "生成 20 条演示订单" : "生成 20 条演示生产数据") : null)
        ),
        h(antd.Collapse, { style: { marginBottom: 16 }, items: [{ key: "guide", label: "功能引导与使用说明", children: h("div", null, h("p", null, "功能介绍：集中管理所有智造云应用共享的数据、字段、导入批次、演示数据、健康检查和安全备份。"), h("ol", null, h("li", null, "用“导入 Excel/CSV”导入正式业务数据并核对字段。"), h("li", null, "可在“数据环境”中切换演示/正式；生成的演示数据可按批次撤销。"), h("li", null, "新增或调整字段请在字段管理中完成，核心字段受保护。"), h("li", null, "恢复备份前必须确认，系统会先创建安全备份。"))) }] }),
        error ? h(antd.Alert, { type: "error", showIcon: true, message: error, style: { marginBottom: 16 } }) : null,
        h(antd.Row, { gutter: [12, 12], style: { marginBottom: 16 } },
          [["数据表", entities.length], ["当前记录", current.record_count || 0], ["演示数据", current.demo_count || 0], ["正式数据", current.production_count || 0]].map(function (item) {
            return h(antd.Col, { xs: 12, md: 6, key: item[0] }, h(antd.Card, { size: "small" }, h(antd.Statistic, { title: item[0], value: item[1] })));
          })
        ),
        h(antd.Card, { size: "small", style: { marginBottom: 16 } },
          h("div", { style: { display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" } },
            h("span", null, "数据表"),
            h(antd.Select, { value: selected, style: { width: 180 }, onChange: setSelected,
              options: entities.map(function (item) { return { value: item.entity, label: item.label + " (" + item.entity + ")" }; }) }),
            h("span", null, "数据环境"),
            h(antd.Select, { value: dataMode, style: { width: 150 }, onChange: setDataMode,
              options: [{ value: "", label: "全部" }, { value: "demo", label: "演示 Demo" }, { value: "production", label: "正式 Live" }] }),
            h("span", null, "来源"),
            h(antd.Select, { value: source, style: { width: 140 }, onChange: setSource,
              options: [{ value: "", label: "全部" }, { value: "real", label: "已导入" }, { value: "simulated", label: "系统生成" }] })
          )
        ),
        h(antd.Tabs, { items: [
          { key: "records", label: "数据预览（最多 100 条）", children: h(antd.Table, { rowKey: "record_id", size: "small", loading: loading, columns: columns, dataSource: records, scroll: { x: Math.max(900, columns.length * 150) }, pagination: { pageSize: 20 } }) },
          { key: "schema", label: "字段结构", children: h("div", null,
            h("div", { style: { display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 12 } },
              h(antd.Input, { size: "small", style: { width: 170 }, placeholder: "字段名（小写字母/数字/_）", value: newField.field_name, onChange: function (e) { setNewField(Object.assign({}, newField, { field_name: e.target.value })); } }),
              h(antd.Input, { size: "small", style: { width: 150 }, placeholder: "显示名称", value: newField.field_label, onChange: function (e) { setNewField(Object.assign({}, newField, { field_label: e.target.value })); } }),
              h(antd.Select, { size: "small", style: { width: 110 }, value: newField.field_type, options: ["text", "number", "date"].map(function (v) { return { value: v, label: v }; }), onChange: function (v) { setNewField(Object.assign({}, newField, { field_type: v })); } }),
              h(antd.Checkbox, { checked: newField.field_required, onChange: function (e) { setNewField(Object.assign({}, newField, { field_required: e.target.checked })); } }, "必填"),
              h(antd.Button, { size: "small", type: "primary", onClick: function () {
                  if (!/^[a-z][a-z0-9_]{0,63}$/.test(newField.field_name)) { message.warning("字段名需为小写字母/数字/下划线"); return; }
                  submitAddField(newField).then(function () { setNewField({ field_name: "", field_label: "", field_type: "text", field_required: false }); });
                } }, "新增字段"),
              h("span", { style: { fontSize: 11, color: "#98a2b3" } }, "新增字段即时生效，导入映射与数据预览自动包含；改显示名/停用需管理员")
            ),
            h(antd.Table, { rowKey: "name", size: "small", loading: loading, pagination: false, dataSource: schema ? schema.fields : [], columns: [
            { title: "字段名", dataIndex: "name" }, { title: "显示名称", dataIndex: "label" }, { title: "类型", dataIndex: "type" },
            { title: "必填", dataIndex: "required", render: function (value) { return value ? "是" : "否"; } },
            { title: "状态", dataIndex: "active", render: function (value) { return h(antd.Tag, { color: value ? "green" : "default" }, value ? "启用" : "停用"); } },
            { title: "内置字段", dataIndex: "built_in", render: function (value) { return value ? "是" : "否"; } },
            { title: "操作", key: "_op", width: 130, render: function (_, field) { return field.built_in ? null : h("div", { style: { display: "flex", gap: 6 } },
              h(antd.Button, { size: "small", onClick: function () { var label = window.prompt("新的显示名称", field.label); if (label && label.trim()) patchField(field.name, { label: label.trim() }); } }, "改名"),
              h(antd.Button, { size: "small", danger: true, onClick: function () { patchField(field.name, { active: !field.active }); } }, field.active ? "停用" : "启用")
            ); } }
          ] })
          ) },
          { key: "operations", label: "健康与备份", children: h(React.Fragment, null,
            h(antd.Alert, { type: health && health.status === "available" ? "success" : "error", showIcon: true,
              message: health ? ("数据库完整性：" + health.integrity + "；Schema v" + health.schema_version + "；备份 " + health.backup_count + " 个") : "正在读取健康状态",
              description: health && health.reason ? (health.reason + "；影响：" + health.impact) : "恢复操作会校验 SHA-256 并先创建安全备份。AES-GCM 加密备份可通过 API 指定密钥环境变量。", style: { marginBottom: 12 } }),
            h(antd.Table, { rowKey: "name", size: "small", pagination: false, dataSource: backups, columns: [
              { title: "备份", dataIndex: "name" }, { title: "时间", dataIndex: "created_at" },
              { title: "加密", dataIndex: "encrypted", render: function (value) { return value ? "AES-GCM" : "否"; } },
              { title: "校验", dataIndex: "verified", render: function (value) { return h(antd.Tag, { color: value ? "green" : "red" }, value ? "通过" : "失败"); } },
              { title: "操作", key: "action", render: function (_, item) { return h(antd.Button, { danger: true, disabled: !item.verified || item.encrypted, onClick: function () { restoreBackup(item.name); } }, item.encrypted ? "通过 API 提供密钥恢复" : "恢复"); } }
            ] })
          ) }
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
        ),
        h(AgentDock, { open: agentOpen, onClose: function () { setAgentOpen(false); }, moduleLabel: "统一数据中心", chips: [{ key: "preview", label: "预览数据" }, { key: "health", label: "健康与备份" }], messages: agentMessages, draft: agentDraft, setDraft: setAgentDraft, busy: agentBusy, onSend: agentSend, onCommand: agentCommand })
      )
    );
  }

  Q.registerRoutes("zhiyun-data-core", [{ path: "/apps/zhiyun-data-core", component: DataBrowser, label: "统一数据中心", icon: "🗄️", priority: 75 }]);
})();
