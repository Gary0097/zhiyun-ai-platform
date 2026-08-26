(function () {
  var Q = window.QwenPaw;
  if (!Q || !Q.host || !Q.host.React || !Q.host.ReactDOM) return;
  var React = Q.host.React;
  var ReactDOM = Q.host.ReactDOM;
  var h = React.createElement;
  // Q.host.getApiUrl already prefixes "/api", so keep the plugin-relative path here.
  var apiRoot = "/zhiyun-auth";

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

  function AuthGate() {
    var state = React.useState("loading");
    var status = state[0]; var setStatus = state[1];
    var cfgState = React.useState(null); var cfg = cfgState[0]; var setCfg = cfgState[1];
    var userState = React.useState(null); var user = userState[0]; var setUser = userState[1];
    var usernameState = React.useState(""); var username = usernameState[0]; var setUsername = usernameState[1];
    var passwordState = React.useState(""); var password = passwordState[0]; var setPassword = passwordState[1];
    var errState = React.useState(""); var err = errState[0]; var setErr = errState[1];
    var busyState = React.useState(false); var busy = busyState[0]; var setBusy = busyState[1];

    React.useEffect(function () {
      request("/config").then(setCfg).catch(function () { setCfg({ brand_name: "制造云 AI-Agent OS", enterprise: "制造云", background_data_url: "" }); });
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
          setUser(body.user); setStatus("ready");
        })
        .catch(function (error) { setErr(error.message || "登录失败"); })
        .finally(function () { setBusy(false); });
    }
    function logout() {
      writeToken("");
      setUser(null); setPassword(""); setStatus("locked");
    }

    var brand = (cfg && cfg.brand_name) || "制造云 AI-Agent OS";
    var enterprise = (cfg && cfg.enterprise) || "制造云";
    var bg = (cfg && cfg.background_data_url) || "";

    if (status === "loading") return null;
    if (status === "ready" && user) {
      return h("div", { style: {
        position: "fixed", right: 16, bottom: 16, zIndex: 2100, display: "flex", gap: 8, alignItems: "center",
        padding: "8px 12px", background: "#ffffff", border: "1px solid #e3e8ef", borderRadius: 10,
        boxShadow: "0 4px 18px rgba(16,24,40,0.12)", fontSize: 12, color: "#1f2933", fontFamily: "system-ui, -apple-system, sans-serif"
      } },
        h("div", { style: { display: "flex", flexDirection: "column", gap: 2, lineHeight: 1.4 } },
          h("span", { style: { fontWeight: 650 } }, user.display_name + " · " + user.role),
          h("span", { style: { color: "#5b6472" } }, enterprise + " · Agent: " + (user.agent_id === "default" ? "默认" : user.agent_id))
        ),
        h("button", { onClick: logout, style: {
          border: "1px solid #d0d5dd", background: "#ffffff", color: "#475467", borderRadius: 6,
          padding: "4px 10px", fontSize: 12, cursor: "pointer"
        } }, "退出")
      );
    }

    return h("div", { style: {
      position: "fixed", inset: 0, zIndex: 2000, display: "flex", alignItems: "center", justifyContent: "center",
      background: bg ? ("url(" + bg + ") center/cover no-repeat") : "linear-gradient(135deg, #0b1220 0%, #16243a 55%, #1c3153 100%)",
      fontFamily: "system-ui, -apple-system, sans-serif"
    } },
      h("div", { style: { position: "absolute", inset: 0, background: "rgba(9,14,24,0.55)", backdropFilter: "blur(2px)" } }),
      h("div", { style: { position: "relative", width: "min(400px, 90vw)", background: "#ffffff", borderRadius: 16, boxShadow: "0 24px 64px rgba(0,0,0,0.32)", padding: "34px 34px 28px" } },
        h("div", { style: { textAlign: "center", marginBottom: 24 } },
          h("div", { style: { fontSize: 26, fontWeight: 800, color: "#1f2933", letterSpacing: 0 } }, brand),
          h("div", { style: { fontSize: 13, color: "#667085", marginTop: 6 } }, enterprise + " · 员工统一登录")
        ),
        h("div", { style: { display: "flex", flexDirection: "column", gap: 14 } },
          h("label", { style: { display: "flex", flexDirection: "column", gap: 6, fontSize: 12, color: "#344054", fontWeight: 600 } },
            "账号",
            h("input", { value: username, onChange: function (e) { setUsername(e.target.value); }, placeholder: "请输入员工账号", style: {
              width: "100%", padding: "10px 12px", fontSize: 14, border: "1px solid #d0d5dd", borderRadius: 8,
              outline: "none", boxSizing: "border-box", fontFamily: "inherit"
            } })
          ),
          h("label", { style: { display: "flex", flexDirection: "column", gap: 6, fontSize: 12, color: "#344054", fontWeight: 600 } },
            "密码",
            h("input", { type: "password", value: password, onChange: function (e) { setPassword(e.target.value); }, onKeyDown: function (e) { if (e.key === "Enter") login(); }, placeholder: "请输入登录密码", style: {
              width: "100%", padding: "10px 12px", fontSize: 14, border: "1px solid #d0d5dd", borderRadius: 8,
              outline: "none", boxSizing: "border-box", fontFamily: "inherit"
            } })
          ),
          err ? h("div", { style: { color: "#d92d20", fontSize: 12, lineHeight: 1.4 } }, err) : null,
          h("button", { onClick: login, disabled: busy, style: {
            width: "100%", padding: "11px 0", fontSize: 14, fontWeight: 650, color: "#ffffff",
            background: busy ? "#98a2b3" : "#2563eb", border: "none", borderRadius: 9, cursor: busy ? "default" : "pointer",
            opacity: busy ? 0.8 : 1
          } }, busy ? "登录中…" : "登录"),
          h("div", { style: { marginTop: 8, fontSize: 11.5, color: "#98a2b3", textAlign: "center" } },
            "默认管理员：admin / ZhizaoYun@2026（可在登录插件配置中修改品牌与账号）")
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
