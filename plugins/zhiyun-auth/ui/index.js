(function () {
  var Q = window.QwenPaw;
  if (!Q || !Q.host || !Q.host.React || !Q.host.ReactDOM) return;
  var React = Q.host.React;
  var ReactDOM = Q.host.ReactDOM;
  var h = React.createElement;
  // Q.host.getApiUrl already prefixes "/api", so keep the plugin-relative path here.
  var apiRoot = "/zhiyun-auth";
  var BLUE = "#1f5ed6";        // 金蝶星空主蓝
  var BLUE_DARK = "#1749a8";
  var FONT = "system-ui, -apple-system, 'Segoe UI', 'Microsoft YaHei', sans-serif";

  function readToken() {
    try { return window.localStorage.getItem("zhiyun_token") || ""; } catch (e) { return ""; }
  }
  function writeToken(token) {
    try {
      if (token) window.localStorage.setItem("zhiyun_token", token);
      else window.localStorage.removeItem("zhiyun_token");
    } catch (e) { /* ignore */ }
  }
  function request(path, options) {
    var token = readToken();
    return window.fetch(Q.host.getApiUrl(apiRoot + path), Object.assign({}, options || {}, {
      headers: Object.assign({}, (options && options.headers) || {}, token ? { Authorization: "Bearer " + token } : {})
    })).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (body) {
        if (!response.ok) throw new Error(body.detail || ("HTTP " + response.status));
        return body;
      });
    });
  }
  function logoRequest(path, options) {
    var token = readToken();
    return window.fetch(Q.host.getApiUrl(path), Object.assign({}, options || {}, {
      headers: Object.assign({}, (options && options.headers) || {}, token ? { Authorization: "Bearer " + token } : {})
    })).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (body) {
        if (!response.ok) throw new Error(body.detail || ("HTTP " + response.status));
        return body;
      });
    });
  }
  function readFileAsDataUrl(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () { resolve(String(reader.result || "")); };
      reader.onerror = function () { reject(new Error("无法读取文件")); };
      reader.readAsDataURL(file);
    });
  }
  var inputStyle = {
    width: "100%", padding: "9px 11px", fontSize: 13.5, border: "1px solid #d6dee8", borderRadius: 6,
    outline: "none", boxSizing: "border-box", fontFamily: "inherit", background: "#ffffff", color: "#1f2933"
  };
  var modalMask = { position: "fixed", inset: 0, zIndex: 2300, background: "rgba(15,23,42,0.45)", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: FONT };
  var modalCard = { width: "min(860px, 94vw)", maxHeight: "88vh", overflow: "auto", background: "#ffffff", borderRadius: 10, boxShadow: "0 24px 64px rgba(0,0,0,0.28)" };
  var btn = function (extra, text, onClick, disabled) {
    return h("button", Object.assign({ onClick: onClick, disabled: !!disabled, style: Object.assign({
      border: "none", borderRadius: 6, padding: "7px 14px", fontSize: 12.5, cursor: disabled ? "default" : "pointer",
      background: BLUE, color: "#ffffff", fontWeight: 600
    }, extra || {}) }, disabled ? { disabled: true } : {}), text);
  };

  // ==== 系统设置（封面 / Logo / 登录企业名称） ====
  function BrandingModal(props) {
    var cfg = props.config || {};
    var nameState = React.useState(cfg.brand_name || ""); var brandName = nameState[0]; var setBrandName = nameState[1];
    var entState = React.useState(cfg.enterprise || ""); var enterprise = entState[0]; var setEnterprise = entState[1];
    var coverState = React.useState(""); var cover = coverState[0]; var setCover = coverState[1];
    var logoState = React.useState(""); var logo = logoState[0]; var setLogo = logoState[1];
    var msgState = React.useState(""); var msg = msgState[0]; var setMsg = msgState[1];
    var busyState = React.useState(false); var busy = busyState[0]; var setBusy = busyState[1];

    function pickCover(e) {
      var file = e.target.files && e.target.files[0];
      if (!file) return;
      readFileAsDataUrl(file).then(function (data) { setCover(data); setMsg(""); }).catch(function (err) { setMsg(err.message); });
    }
    function pickLogo(e) {
      var file = e.target.files && e.target.files[0];
      if (!file) return;
      if (!/image\/(png|jpeg|svg\+xml|webp)/.test(file.type)) { setMsg("Logo 仅支持 PNG / JPG / SVG / WEBP"); return; }
      readFileAsDataUrl(file).then(function (data) { setLogo(data); setMsg(""); }).catch(function (err) { setMsg(err.message); });
    }
    function save() {
      setBusy(true); setMsg("");
      var jobs = [];
      jobs.push(request("/branding", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        brand_name: brandName, enterprise: enterprise, background_data_url: cover
      }) }));
      if (logo) jobs.push(logoRequest("/zhiyun-logo/config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ logo: logo }) }));
      Promise.all(jobs).then(function () {
        setMsg("已保存，刷新登录页即可生效");
        setCover(""); setLogo("");
        if (props.onSaved) props.onSaved();
      }).catch(function (err) { setMsg("保存失败：" + (err.message || "未知错误")); })
        .finally(function () { setBusy(false); });
    }
    var section = { padding: "16px 22px", borderBottom: "1px solid #eef2f7" };
    return h("div", { style: modalMask, onClick: function (e) { if (e.target === e.currentTarget) props.onClose(); } },
      h("div", { style: modalCard },
        h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 22px", borderBottom: "1px solid #eef2f7" } },
          h("strong", { style: { fontSize: 15 } }, "系统设置 · 登录页与企业品牌"),
          h("button", { onClick: props.onClose, style: { border: "none", background: "transparent", fontSize: 17, color: "#98a2b3", cursor: "pointer" } }, "✕")
        ),
        h("div", { style: section },
          h("div", { style: { fontWeight: 650, marginBottom: 6 } }, "登录企业名称 / 品牌名称"),
          h("div", { style: { display: "flex", gap: 10 } },
            h("input", { value: enterprise, onChange: function (e) { setEnterprise(e.target.value); }, placeholder: "企业名称（如：制造云）", style: inputStyle }),
            h("input", { value: brandName, onChange: function (e) { setBrandName(e.target.value); }, placeholder: "品牌名称（如：制造云 AI-OS）", style: inputStyle })
          )
        ),
        h("div", { style: section },
          h("div", { style: { fontWeight: 650, marginBottom: 6 } }, "登录封面图片"),
          h("div", { style: { fontSize: 12, color: "#667085", marginBottom: 8 } }, "显示在登录页左侧（建议 1600×900 以上，PNG/JPG，≤2MB）"),
          h("div", { style: { display: "flex", gap: 12, alignItems: "flex-start" } },
            h("label", { style: { display: "inline-flex", alignItems: "center", gap: 6, border: "1px solid #d6dee8", borderRadius: 6, padding: "7px 12px", fontSize: 12.5, cursor: "pointer", background: "#fff" } },
              "选择封面图片", h("input", { type: "file", accept: "image/*", style: { display: "none" }, onChange: pickCover })
            ),
            cover ? h("div", { style: { width: 200, height: 112, borderRadius: 8, border: "1px solid #e3e8ef", background: "url(" + cover + ") center/cover no-repeat" } }) :
              h("div", { style: { width: 200, height: 112, borderRadius: 8, border: "1px dashed #d6dee8", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11.5, color: "#98a2b3" } },
                cfg.background_data_url ? "当前已有封面（不改则保留）" : "未设置（默认蓝色渐变）")
          )
        ),
        h("div", { style: section },
          h("div", { style: { fontWeight: 650, marginBottom: 6 } }, "系统 Logo"),
          h("div", { style: { fontSize: 12, color: "#667085", marginBottom: 8 } }, "用于登录页与顶栏（PNG/JPG/SVG/WEBP，≤2MB）"),
          h("div", { style: { display: "flex", gap: 12, alignItems: "center" } },
            h("label", { style: { display: "inline-flex", alignItems: "center", gap: 6, border: "1px solid #d6dee8", borderRadius: 6, padding: "7px 12px", fontSize: 12.5, cursor: "pointer", background: "#fff" } },
              "选择 Logo", h("input", { type: "file", accept: ".png,.jpg,.jpeg,.svg,.webp", style: { display: "none" }, onChange: pickLogo })
            ),
            logo ? h("img", { src: logo, style: { height: 34 } }) :
              h("span", { style: { fontSize: 11.5, color: "#98a2b3" } }, "不改则保留当前 Logo")
          )
        ),
        h("div", { style: { display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 10, padding: "14px 22px" } },
          msg ? h("span", { style: { fontSize: 12, color: msg.indexOf("失败") >= 0 ? "#d92d20" : "#12b76a", marginRight: "auto" } }, msg) : null,
          h("button", { onClick: props.onClose, style: { border: "1px solid #d6dee8", borderRadius: 6, padding: "7px 14px", fontSize: 12.5, background: "#fff", cursor: "pointer" } }, "关闭"),
          btn({ opacity: busy ? 0.7 : 1 }, busy ? "保存中…" : "保存设置", save, busy)
        )
      )
    );
  }

  // ==== 账号权限管理 ====
  function UsersModal(props) {
    var usersState = React.useState(null); var users = usersState[0]; var setUsers = usersState[1];
    var agentsState = React.useState([]); var agents = agentsState[0]; var setAgents = agentsState[1];
    var editingState = React.useState(null); var editing = editingState[0]; var setEditing = editingState[1];
    var msgState = React.useState(""); var msg = msgState[0]; var setMsg = msgState[1];
    var busyState = React.useState(false); var busy = busyState[0]; var setBusy = busyState[1];

    function load() {
      request("/users").then(function (body) { setUsers(body.users || []); }).catch(function (err) { setMsg(err.message); setUsers([]); });
      request("/config").then(function (cfg) { setAgents((cfg.agents || []).map(function (a) { return a.id; })); }).catch(function () {});
    }
    React.useEffect(load, []);

    function save() {
      if (!editing) return;
      if (!editing.username) { setMsg("请填写账号"); return; }
      if (editing.isNew && (!editing.password || editing.password.length < 6)) { setMsg("新账号需要至少 6 位密码"); return; }
      setBusy(true); setMsg("");
      request("/users", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        username: editing.username, password: editing.password || "", display_name: editing.display_name || editing.username,
        role: editing.role || "member", agent_id: editing.agent_id || "default",
        data_scope: editing.data_scope || "enterprise", kb_scope: editing.kb_scope || "", active: editing.active !== false
      }) }).then(function () {
        setMsg("已保存：" + editing.username);
        setEditing(null);
        load();
      }).catch(function (err) { setMsg("保存失败：" + err.message); }).finally(function () { setBusy(false); });
    }
    function field(label, node) {
      return h("label", { style: { display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "#344054", fontWeight: 600 } }, label, node);
    }
    var td = { padding: "8px 10px", fontSize: 12.5, borderBottom: "1px solid #f0f4f8", textAlign: "left", color: "#1f2933" };
    return h("div", { style: modalMask, onClick: function (e) { if (e.target === e.currentTarget) props.onClose(); } },
      h("div", { style: modalCard },
        h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 22px", borderBottom: "1px solid #eef2f7" } },
          h("strong", { style: { fontSize: 15 } }, "账号与权限管理"),
          h("button", { onClick: props.onClose, style: { border: "none", background: "transparent", fontSize: 17, color: "#98a2b3", cursor: "pointer" } }, "✕")
        ),
        h("div", { style: { padding: "12px 22px 0", fontSize: 12, color: "#667085", lineHeight: 1.6 } },
          "每个账号绑定一个智能体：登录后自动切换到该智能体，其会话、定时任务、收件箱与知识文件随智能体隔离；数据范围与知识库范围在业务应用接口层强制生效。"),
        h("div", { style: { padding: "12px 22px 0", display: "flex", justifyContent: "flex-end" } },
          btn({ background: "#fff", color: BLUE, border: "1px solid " + BLUE }, "+ 新建账号", function () {
            setEditing({ isNew: true, username: "", display_name: "", password: "", role: "member", agent_id: (agents[0] || "default"), data_scope: "enterprise", kb_scope: "", active: true });
          })
        ),
        editing ? h("div", { style: { margin: "12px 22px", border: "1px solid #d6e2f0", borderRadius: 8, padding: 14, background: "#f8fbff" } },
          h("div", { style: { fontWeight: 650, marginBottom: 10, fontSize: 13 } }, (editing.isNew ? "新建账号" : "编辑账号：" + editing.username)),
          h("div", { style: { display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 } },
            field("账号", h("input", { value: editing.username, disabled: !editing.isNew, onChange: function (e) { setEditing(Object.assign({}, editing, { username: e.target.value })); }, placeholder: "如 sales_01", style: Object.assign({}, inputStyle, editing.isNew ? {} : { background: "#eef2f7" }) })),
            field("姓名", h("input", { value: editing.display_name, onChange: function (e) { setEditing(Object.assign({}, editing, { display_name: e.target.value })); }, placeholder: "如 张三", style: inputStyle })),
            field(editing.isNew ? "密码（≥6位）" : "重置密码（留空不改）", h("input", { type: "password", value: editing.password || "", onChange: function (e) { setEditing(Object.assign({}, editing, { password: e.target.value })); }, style: inputStyle })),
            field("角色", h("select", { value: editing.role, onChange: function (e) { setEditing(Object.assign({}, editing, { role: e.target.value })); }, style: inputStyle },
              h("option", { value: "member" }, "普通成员"),
              h("option", { value: "admin" }, "管理员"))),
            field("绑定智能体（会话/任务/收件箱/知识）", h("select", { value: editing.agent_id, onChange: function (e) { setEditing(Object.assign({}, editing, { agent_id: e.target.value })); }, style: inputStyle },
              h("option", { value: "default" }, "default（默认）"),
              agents.map(function (id) { return h("option", { key: id, value: id }, id); }))),
            field("数据范围", h("select", { value: editing.data_scope, onChange: function (e) { setEditing(Object.assign({}, editing, { data_scope: e.target.value })); }, style: inputStyle },
              h("option", { value: "enterprise" }, "全企业"),
              h("option", { value: "department" }, "本部门"),
              h("option", { value: "agent" }, "仅绑定智能体"))),
            field("知识库范围（逗号分隔的目录/文件，留空=跟随智能体）", h("input", { value: editing.kb_scope, onChange: function (e) { setEditing(Object.assign({}, editing, { kb_scope: e.target.value })); }, placeholder: "如 knowledge/sales, docs", style: inputStyle })),
            field("启用状态", h("select", { value: editing.active === false ? "0" : "1", onChange: function (e) { setEditing(Object.assign({}, editing, { active: e.target.value === "1" })); }, style: inputStyle },
              h("option", { value: "1" }, "启用"),
              h("option", { value: "0" }, "停用")))
          ),
          h("div", { style: { display: "flex", gap: 8, marginTop: 12, alignItems: "center" } },
            btn({ opacity: busy ? 0.7 : 1 }, busy ? "保存中…" : "保存", save, busy),
            h("button", { onClick: function () { setEditing(null); }, style: { border: "1px solid #d6dee8", borderRadius: 6, padding: "7px 14px", fontSize: 12.5, background: "#fff", cursor: "pointer" } }, "取消")
          )
        ) : null,
        h("div", { style: { padding: "10px 22px 20px", overflowX: "auto" } },
          h("table", { style: { width: "100%", borderCollapse: "collapse" } },
            h("thead", null, h("tr", null, ["账号", "姓名", "角色", "绑定智能体", "数据范围", "知识库", "状态", "操作"].map(function (t) {
              return h("th", { key: t, style: Object.assign({}, td, { background: "#f4f8fd", fontWeight: 650, color: "#35405a" }) }, t);
            }))),
            h("tbody", null, (users || []).map(function (u) {
              return h("tr", { key: u.username },
                h("td", { style: td }, u.username),
                h("td", { style: td }, u.display_name || "—"),
                h("td", { style: td }, u.role === "admin" ? "管理员" : "成员"),
                h("td", { style: td }, u.agent_id || "default"),
                h("td", { style: td }, { enterprise: "全企业", department: "本部门", agent: "仅智能体" }[u.data_scope] || u.data_scope || "全企业"),
                h("td", { style: td }, u.kb_scope || "—"),
                h("td", { style: td }, h("span", { style: { color: u.active === false ? "#d92d20" : "#12b76a", fontWeight: 600 } }, u.active === false ? "停用" : "启用")),
                h("td", { style: td }, h("a", { href: "javascript:void 0", onClick: function () { setEditing(Object.assign({ isNew: false, password: "" }, u)); window.scrollTo({ top: 0, behavior: "smooth" }); }, style: { color: BLUE, fontSize: 12.5 } }, "编辑"))
              );
            }))
          ),
          users && !users.length ? h("div", { style: { padding: 24, textAlign: "center", color: "#98a2b3", fontSize: 13 } }, "暂无账号") : null,
          msg ? h("div", { style: { fontSize: 12, color: msg.indexOf("失败") >= 0 || msg.indexOf("请") === 0 ? "#d92d20" : "#12b76a", marginTop: 8 } }, msg) : null
        )
      )
    );
  }

  // ==== 主组件 ====
  function AuthGate() {
    var state = React.useState("loading");
    var status = state[0]; var setStatus = state[1];
    var cfgState = React.useState(null); var cfg = cfgState[0]; var setCfg = cfgState[1];
    var logoState = React.useState(""); var logo = logoState[0]; var setLogo = logoState[1];
    var userState = React.useState(null); var user = userState[0]; var setUser = userState[1];
    var usernameState = React.useState(""); var username = usernameState[0]; var setUsername = usernameState[1];
    var passwordState = React.useState(""); var password = passwordState[0]; var setPassword = passwordState[1];
    var errState = React.useState(""); var err = errState[0]; var setErr = errState[1];
    var busyState = React.useState(false); var busy = busyState[0]; var setBusy = busyState[1];
    var settingsState = React.useState(false); var settingsOpen = settingsState[0]; var setSettingsOpen = settingsState[1];
    var usersState = React.useState(false); var usersOpen = usersState[0]; var setUsersOpen = usersState[1];

    function loadConfig() {
      request("/config").then(setCfg).catch(function () { setCfg({ brand_name: "制造云 AI-OS", enterprise: "制造云", background_data_url: "" }); });
      logoRequest("/zhiyun-logo/config").then(function (body) { if (body && body.logo) setLogo(body.logo); }).catch(function () {});
    }
    React.useEffect(function () {
      loadConfig();
      request("/me").then(function (body) {
        window.dispatchEvent(new CustomEvent("zhiyun:auth", { detail: body.user }));
        setUser(body.user); setStatus("ready");
      }).catch(function () { setStatus("locked"); });
    }, []);

    function login() {
      if (!username.trim() || !password) { setErr("请输入账号和密码"); return; }
      setBusy(true); setErr("");
      request("/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: username.trim(), password: password }) })
        .then(function (body) {
          writeToken(body.token);
          window.dispatchEvent(new CustomEvent("zhiyun:auth", { detail: body.user }));
          // 普通成员登录后自动切换到绑定的智能体：会话/定时任务/收件箱/知识文件随智能体隔离
          if (body.user && body.user.agent_id && body.user.role !== "admin") {
            request("/agents/activate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ agent_id: body.user.agent_id }) }).catch(function () {});
          }
          setUser(body.user); setStatus("ready");
        })
        .catch(function (error) { setErr(error.message || "登录失败"); })
        .finally(function () { setBusy(false); });
    }
    function logout() {
      writeToken("");
      setUser(null); setPassword(""); setStatus("locked");
    }

    var brand = (cfg && cfg.brand_name) || "制造云 AI-OS";
    var enterprise = (cfg && cfg.enterprise) || "制造云";
    var bg = (cfg && cfg.background_data_url) || "";

    if (status === "loading") return null;
    if (status === "ready" && user) {
      return h("div", { style: { fontFamily: FONT } },
        h("div", { style: {
          position: "fixed", right: 16, bottom: 16, zIndex: 2100, display: "flex", gap: 10, alignItems: "center",
          padding: "9px 12px", background: "#ffffff", border: "1px solid #e3e8ef", borderRadius: 10,
          boxShadow: "0 4px 18px rgba(16,24,40,0.12)", fontSize: 12, color: "#1f2933"
        } },
          logo ? h("img", { src: logo, style: { height: 30, borderRadius: 4 } }) : null,
          h("div", { style: { display: "flex", flexDirection: "column", gap: 2, lineHeight: 1.4 } },
            h("span", { style: { fontWeight: 650 } }, (user.display_name || user.username) + " · " + (user.role === "admin" ? "系统管理员" : "成员")),
            h("span", { style: { color: "#5b6472" } }, enterprise + " · 智能体：" + (user.agent_id || "default"))
          ),
          user.role === "admin" ? h("div", { style: { display: "flex", gap: 6 } },
            btn({ padding: "5px 10px", fontSize: 12 }, "系统设置", function () { setSettingsOpen(true); }),
            btn({ padding: "5px 10px", fontSize: 12 }, "账号管理", function () { setUsersOpen(true); })
          ) : null,
          h("button", { onClick: logout, style: {
            border: "1px solid #d0d5dd", background: "#ffffff", color: "#475467", borderRadius: 6,
            padding: "5px 10px", fontSize: 12, cursor: "pointer"
          } }, "退出")
        ),
        settingsOpen ? h(BrandingModal, { config: cfg, onClose: function () { setSettingsOpen(false); }, onSaved: loadConfig }) : null,
        usersOpen ? h(UsersModal, { onClose: function () { setUsersOpen(false); } }) : null
      );
    }

    // ==== 金蝶云星空风格登录页：左侧企业封面 + 右侧登录表单 ====
    return h("div", { style: { position: "fixed", inset: 0, zIndex: 2000, display: "flex", fontFamily: FONT, background: "#f2f5f9" } },
      h("div", { style: {
        flex: "1 1 58%", position: "relative", overflow: "hidden",
        background: bg ? ("url(" + bg + ") center/cover no-repeat") : "linear-gradient(148deg, #123c8c 0%, #1f5ed6 48%, #3d7ce4 100%)"
      } },
        !bg ? h("div", { style: {
          position: "absolute", inset: 0, opacity: 0.16,
          backgroundImage: "linear-gradient(rgba(255,255,255,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.5) 1px, transparent 1px)",
          backgroundSize: "44px 44px"
        } }) : null,
        h("div", { style: { position: "absolute", inset: 0, background: bg ? "linear-gradient(180deg, rgba(10,26,64,0.30) 0%, rgba(10,26,64,0.58) 100%)" : "none" } }),
        h("div", { style: { position: "relative", height: "100%", display: "flex", flexDirection: "column", justifyContent: "flex-end", padding: "56px 58px", color: "#ffffff" } },
          h("div", { style: { display: "flex", alignItems: "center", gap: 12, marginBottom: 16 } },
            logo ? h("img", { src: logo, style: { height: 42, borderRadius: 6, background: "rgba(255,255,255,0.9)", padding: 3 } }) : null,
            h("span", { style: { fontSize: 30, fontWeight: 800, letterSpacing: 1 } }, enterprise)
          ),
          h("div", { style: { fontSize: 16.5, fontWeight: 600, opacity: 0.96, marginBottom: 8 } }, brand),
          h("div", { style: { fontSize: 13, opacity: 0.78, lineHeight: 1.7, maxWidth: 520 } },
            "导入数据即可分析 · 应用内真实智能体对话 · 可审阅可导出 · 会话、任务与知识按账号隔离")
        )
      ),
      h("div", { style: { flex: "1 1 42%", display: "flex", alignItems: "center", justifyContent: "center", background: "#ffffff" } },
        h("div", { style: { width: "min(360px, 84%)", position: "relative" } },
          h("div", { style: { position: "absolute", top: -34, left: 0, right: 0, height: 4, borderRadius: 4, background: "linear-gradient(90deg, " + BLUE_DARK + ", " + BLUE + ")" } }),
          h("div", { style: { marginBottom: 26 } },
            h("div", { style: { fontSize: 22, fontWeight: 800, color: "#182640" } }, "欢迎登录"),
            h("div", { style: { fontSize: 13, color: "#667085", marginTop: 6 } }, enterprise + " · 员工统一身份认证")
          ),
          h("div", { style: { display: "flex", flexDirection: "column", gap: 14 } },
            h("label", { style: { display: "flex", flexDirection: "column", gap: 6, fontSize: 12.5, color: "#344054", fontWeight: 600 } },
              "账号",
              h("input", { value: username, onChange: function (e) { setUsername(e.target.value); }, placeholder: "请输入员工账号", style: Object.assign({}, inputStyle, { padding: "10px 12px", fontSize: 14 }) })
            ),
            h("label", { style: { display: "flex", flexDirection: "column", gap: 6, fontSize: 12.5, color: "#344054", fontWeight: 600 } },
              "密码",
              h("input", { type: "password", value: password, onChange: function (e) { setPassword(e.target.value); }, onKeyDown: function (e) { if (e.key === "Enter") login(); }, placeholder: "请输入登录密码", style: Object.assign({}, inputStyle, { padding: "10px 12px", fontSize: 14 }) })
            ),
            err ? h("div", { style: { color: "#d92d20", fontSize: 12, lineHeight: 1.4 } }, err) : null,
            h("button", { onClick: login, disabled: busy, style: {
              width: "100%", padding: "11px 0", fontSize: 14, fontWeight: 650, color: "#ffffff",
              background: busy ? "#98a2b3" : BLUE, border: "none", borderRadius: 7, cursor: busy ? "default" : "pointer",
              opacity: busy ? 0.85 : 1, boxShadow: "0 6px 16px rgba(31,94,214,0.28)"
            } }, busy ? "登录中…" : "登 录"),
            h("div", { style: { marginTop: 10, fontSize: 11.5, color: "#98a2b3", textAlign: "center" } },
              "账号由企业管理员分配；忘记密码请联系系统管理员重置")
          ),
          h("div", { style: { marginTop: 34, fontSize: 11.5, color: "#b3bdcc", textAlign: "center" } },
            "© 2026 " + enterprise + " · 制造云 AI-OS")
        )
      )
    );
  }

  function mount() {
    // 宿主在不同加载路径下可能把本脚本执行两次；重复挂载会产生两个登录层，
    // 上层按钮没有事件处理器，真实用户将无法登录。这里做幂等保护。
    if (document.getElementById("zhiyun-auth-root")) return;
    var container = document.createElement("div");
    container.id = "zhiyun-auth-root";
    document.body.appendChild(container);
    ReactDOM.createRoot(container).render(h(AuthGate));
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount);
  else mount();
})();
