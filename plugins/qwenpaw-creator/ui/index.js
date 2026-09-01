// -*- coding: utf-8 -*-
// QwenPaw Creator · 视频压缩 — 前端（React，宿主注入）
(function () {
  var Q = window.QwenPaw;
  var pluginId = "qwenpaw-creator";
  if (!Q || !Q.slot || !Q.host || !Q.host.React) return;
  var React = Q.host.React;
  var antd = Q.host.antd || { Card: "div", Alert: "div", Button: "button", Select: "select", Progress: "div", Input: "input" };
  var h = React.createElement;
  var BASE = "/" + pluginId;            // 插件相对路径，经 getApiUrl 补 /api 前缀
  var RAW_BASE = "/api/" + pluginId;    // <a href> 用的绝对路径

  function fmtBytes(n) {
    if (!n) return "0 B";
    var units = ["B", "KB", "MB", "GB", "TB"];
    var i = Math.min(units.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
    return (n / Math.pow(1024, i)).toFixed(i ? 1 : 0) + " " + units[i];
  }
  function fmtDur(s) {
    if (!s) return "-";
    s = Math.round(s);
    return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
  }
  // 注意：Q.host.fetch 内部会再补一次 /api 前缀，这里必须用原生 fetch + getApiUrl
  // （与官方 Agent Kanban 前端一致），否则会请求 /api/api/... 导致 404。
  function getApiUrl(path) { return Q.host.getApiUrl ? Q.host.getApiUrl(path) : path; }
  function authHeaders(extra) {
    var headers = Object.assign({}, extra || {});
    try {
      var t = window.localStorage.getItem("zhiyun_token");
      if (t) headers["Authorization"] = "Bearer " + t;
    } catch (e) { /* 忽略 */ }
    return headers;
  }
  function api(path, opts) {
    var o = opts || {};
    return fetch(getApiUrl(BASE + path), Object.assign({}, o, { headers: authHeaders(o.headers) }))
      .then(function (r) {
        if (!r.ok) return r.text().then(function (t) { throw new Error(t || ("HTTP " + r.status)); });
        return r.json();
      });
  }

  function CreatorPage() {
    var capsState = React.useState(null);
    var caps = capsState[0], setCaps = capsState[1];
    var filesState = React.useState([]);
    var files = filesState[0], setFiles = filesState[1];
    var jobsState = React.useState([]);
    var jobs = jobsState[0], setJobs = jobsState[1];
    var errState = React.useState("");
    var err = errState[0], setErr = errState[1];
    var busyState = React.useState(false);
    var busy = busyState[0], setBusy = busyState[1];
    var localPathState = React.useState("");
    var localPath = localPathState[0], setLocalPath = localPathState[1];

    var encState = React.useState("CPU H.264 / AVC (libx264)");
    var encoderKey = encState[0], setEncoderKey = encState[1];
    var presetState = React.useState("均衡");
    var preset = presetState[0], setPreset = presetState[1];
    var resState = React.useState("保持原分辨率");
    var resolution = resState[0], setResolution = resState[1];
    var cqState = React.useState(28);
    var cq = cqState[0], setCq = cqState[1];
    var audioState = React.useState("复制音频流");
    var audioMode = audioState[0], setAudioMode = audioState[1];

    function refresh() {
      api("/files").then(function (d) { setFiles(d.files || []); }).catch(function () {});
      api("/jobs").then(function (d) { setJobs(d.jobs || []); }).catch(function () {});
    }

    React.useEffect(function () {
      api("/capabilities").then(function (d) {
        setCaps(d);
        var env = d.environment || {};
        var pref = null;
        ((env.encoders) || []).forEach(function (e) {
          if (!e.available || pref) return;
          if (e.label.indexOf("nvenc") >= 0 && e.label.indexOf("H.265") >= 0) pref = e.label;
        });
        if (pref) setEncoderKey(pref);
      }).catch(function (e) { setErr("能力探测失败：" + e.message); });
      refresh();
    }, []);

    React.useEffect(function () {
      var timer = setInterval(refresh, 1500);
      return function () { clearInterval(timer); };
    }, []);

    function onUpload(ev) {
      var f = ev.target.files && ev.target.files[0];
      if (!f) return;
      setBusy(true); setErr("");
      var fd = new FormData();
      fd.append("file", f);
      fetch(getApiUrl(BASE + "/files"), { method: "POST", body: fd, headers: authHeaders() })
        .then(function (r) { if (!r.ok) return r.text().then(function (t) { throw new Error(t); }); return r.json(); })
        .then(function () { refresh(); })
        .catch(function (e) { setErr("上传失败：" + e.message); })
        .finally(function () { setBusy(false); ev.target.value = ""; });
    }

    function addLocal() {
      if (!localPath.trim()) return;
      setBusy(true); setErr("");
      api("/files/local", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: localPath.trim() }) })
        .then(function () { setLocalPath(""); refresh(); })
        .catch(function (e) { setErr("登记失败：" + e.message); })
        .finally(function () { setBusy(false); });
    }

    function startCompress(fileId) {
      setErr("");
      api("/compress", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          file_id: fileId, encoder_key: encoderKey, preset_name: preset,
          resolution_name: resolution, cq_value: cq, audio_mode: audioMode,
          overwrite: false
        })
      }).then(refresh).catch(function (e) { setErr(e.message); });
    }

    function downloadJob(jobId, name) {
    fetch(getApiUrl(BASE + "/jobs/" + jobId + "/download"), { headers: authHeaders() })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.blob();
      })
      .then(function (blob) {
        var url = URL.createObjectURL(blob);
        var a = document.createElement("a");
        a.href = url;
        a.download = name || "output.mp4";
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      })
      .catch(function (e) { setErr("下载失败：" + e.message); });
  }

  function cancel(jobId) {
      api("/jobs/" + jobId + "/cancel", { method: "POST" }).then(refresh).catch(function (e) { setErr(e.message); });
    }

    var labelStyle = { display: "block", fontSize: 12, color: "#5b6472", margin: "10px 0 4px" };
    var inputStyle = { width: "100%", padding: "7px 9px", border: "1px solid #d0d5dd", borderRadius: 6, fontSize: 13, boxSizing: "border-box" };
    var running = (jobs || []).some(function (j) { return j.status === "running"; });

    return h("div", { style: { padding: 24, height: "100%", overflow: "auto", background: "#f7f8fa", fontFamily: "inherit" } },
      h("div", { style: { maxWidth: 1080, margin: "0 auto" } },
        h("h2", { style: { margin: "0 0 4px" } }, "🎬 QwenPaw Creator · 视频压缩"),
        h("p", { style: { color: "#667085", margin: "0 0 16px" } },
          caps && caps.environment && !caps.environment.ready
            ? "未检测到 ffmpeg：请在运行环境安装 ffmpeg 或 imageio-ffmpeg 后重启服务。"
            : "上传或登记视频 → 选择编码器与预设 → 压缩并下载。GPU 编码器自动探测可用性。"),
        err ? h("div", { style: { background: "#fef3f2", border: "1px solid #fecdca", color: "#b42318", borderRadius: 8, padding: "8px 12px", marginBottom: 12, fontSize: 13 } }, err) : null,

        h("div", { style: { background: "#fff", border: "1px solid #e3e8ef", borderRadius: 10, padding: 16, marginBottom: 16 } },
          h("div", { style: { fontWeight: 650, marginBottom: 8 } }, "输入视频"),
          h("div", { style: { display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" } },
            h("label", { style: { padding: "7px 14px", background: "#1f5ed6", color: "#fff", borderRadius: 6, fontSize: 13, cursor: busy ? "wait" : "pointer" } },
              busy ? "处理中…" : "⬆ 上传视频", h("input", { type: "file", accept: "video/*", style: { display: "none" }, onChange: onUpload })),
            h("input", { style: Object.assign({}, inputStyle, { flex: 1, minWidth: 260 }), placeholder: "或输入服务器本地视频绝对路径，如 D:\\videos\\demo.mp4", value: localPath, onChange: function (e) { setLocalPath(e.target.value); } }),
            h("button", { onClick: addLocal, disabled: busy || !localPath.trim(), style: { padding: "7px 12px", borderRadius: 6, border: "1px solid #d0d5dd", background: "#fff", cursor: "pointer", fontSize: 13 } }, "登记本地路径")),

          (files || []).length === 0 ? h("div", { style: { color: "#98a2b3", fontSize: 13, marginTop: 12 } }, "暂无输入视频") :
          h("table", { style: { width: "100%", borderCollapse: "collapse", marginTop: 12, fontSize: 13 } },
            h("thead", null, h("tr", null, ["文件", "分辨率/时长", "大小", "来源", ""].map(function (t) { return h("th", { style: { textAlign: "left", color: "#667085", fontWeight: 500, padding: "6px 8px", borderBottom: "1px solid #e3e8ef" } }, t); }))),
            h("tbody", null, files.map(function (f) {
              return h("tr", { key: f.file_id },
                h("td", { style: { padding: "6px 8px" } }, f.name),
                h("td", { style: { padding: "6px 8px", color: "#5b6472" } }, (f.width || "?") + "×" + (f.height || "?") + " · " + fmtDur(f.duration)),
                h("td", { style: { padding: "6px 8px", color: "#5b6472" } }, fmtBytes(f.size)),
                h("td", { style: { padding: "6px 8px", color: "#5b6472" } }, f.source === "upload" ? "上传" : "本地"),
                h("td", { style: { padding: "6px 8px", textAlign: "right" } },
                  h("button", { onClick: function () { startCompress(f.file_id); }, disabled: running, style: { padding: "5px 12px", borderRadius: 6, border: "none", background: running ? "#cbd5e1" : "#12b76a", color: "#fff", cursor: running ? "default" : "pointer", fontSize: 13 } }, "压缩")));
            })))),
        caps ? h("div", { style: { background: "#fff", border: "1px solid #e3e8ef", borderRadius: 10, padding: 16, marginBottom: 16 } },
          h("div", { style: { fontWeight: 650, marginBottom: 4 } }, "压缩参数"),
          h("label", { style: labelStyle }, "编码器"),
          h("select", { style: inputStyle, value: encoderKey, onChange: function (e) { setEncoderKey(e.target.value); } },
            (caps.environment.encoders || []).map(function (e) {
              return h("option", { key: e.label, value: e.label, disabled: !e.available }, e.label + (e.available ? "" : "（不可用）"));
            })),
          h("label", { style: labelStyle }, "速度/画质预设"),
          h("select", { style: inputStyle, value: preset, onChange: function (e) { setPreset(e.target.value); } }, caps.presets.map(function (p) { return h("option", { key: p, value: p }, p); })),
          h("label", { style: labelStyle }, "输出分辨率"),
          h("select", { style: inputStyle, value: resolution, onChange: function (e) { setResolution(e.target.value); } }, caps.resolutions.map(function (r) { return h("option", { key: r, value: r }, r); })),
          h("label", { style: labelStyle }, "质量（CRF，越小画质越高）：" + cq),
          h("input", { type: "range", min: 16, max: 40, value: cq, style: { width: "100%" }, onChange: function (e) { setCq(parseInt(e.target.value, 10)); } }),
          h("label", { style: labelStyle }, "音频"),
          h("select", { style: inputStyle, value: audioMode, onChange: function (e) { setAudioMode(e.target.value); } }, caps.audio_modes.map(function (m) { return h("option", { key: m, value: m }, m); }))
        ) : null,

        h("div", { style: { background: "#fff", border: "1px solid #e3e8ef", borderRadius: 10, padding: 16 } },
          h("div", { style: { fontWeight: 650, marginBottom: 8 } }, "压缩任务"),
          (jobs || []).length === 0 ? h("div", { style: { color: "#98a2b3", fontSize: 13 } }, "暂无任务") :
          jobs.map(function (j) {
            var pct = Math.round((j.progress || 0) * 100);
            var ratio = j.source_size ? Math.round(100 * (j.output_size || 0) / j.source_size) : null;
            return h("div", { key: j.job_id, style: { padding: "10px 0", borderBottom: "1px solid #f0f2f5", fontSize: 13 } },
              h("div", { style: { display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 6 } },
                h("span", null, j.file_name + " → " + (j.output_name || "")),
                h("span", { style: { color: "#5b6472", whiteSpace: "nowrap" } },
                  fmtBytes(j.source_size) + (j.output_size ? " → " + fmtBytes(j.output_size) + (ratio !== null ? "（" + ratio + "%）" : "") : ""))),
              h("div", { style: { background: "#eef2f6", borderRadius: 5, height: 8, overflow: "hidden", marginBottom: 6 } },
                h("div", { style: { width: (j.status === "done" ? 100 : pct) + "%", height: "100%", background: j.status === "failed" ? "#f04438" : j.status === "done" ? "#12b76a" : "#1f5ed6", transition: "width .4s" } })),
              h("div", { style: { display: "flex", gap: 8, alignItems: "center" } },
                h("span", { style: { color: j.status === "failed" ? "#b42318" : "#5b6472" } },
                  j.status === "running" ? "压缩中 " + pct + "%" : j.status === "done" ? "完成" : j.status === "failed" ? "失败：" + (j.error || "").slice(0, 120) : j.status),
                j.status === "running" ? h("button", { onClick: function () { cancel(j.job_id); }, style: { padding: "2px 10px", fontSize: 12, borderRadius: 5, border: "1px solid #d0d5dd", background: "#fff", cursor: "pointer" } }, "取消") : null,
                j.status === "done" ? h("button", { onClick: function () { downloadJob(j.job_id, j.output_name); }, style: { padding: "2px 10px", fontSize: 12, borderRadius: 5, background: "#12b76a", color: "#fff", border: "none", cursor: "pointer" } }, "⬇ 下载") : null));
          }))));
  }

  if (Q.registerRoutes) {
    Q.registerRoutes("qwenpaw-creator", [{ path: "/apps/qwenpaw-creator", component: CreatorPage, label: "视频压缩", icon: "🎬", priority: 80 }]);
  }
})();
