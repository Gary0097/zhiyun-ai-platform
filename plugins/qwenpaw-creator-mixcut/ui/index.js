// -*- coding: utf-8 -*-
// QwenPaw Creator · 智能混剪 — 前端（React，宿主注入）
(function () {
  var Q = window.QwenPaw;
  var pluginId = "qwenpaw-creator-mixcut";
  if (!Q || !Q.slot || !Q.host || !Q.host.React) return;
  var React = Q.host.React;
  var h = React.createElement;
  var BASE = "/" + pluginId;
  var RAW_BASE = "/api/" + pluginId;

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
  function fmtBytes(n) {
    if (!n) return "0 B";
    var units = ["B", "KB", "MB", "GB"];
    var i = Math.min(units.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
    return (n / Math.pow(1024, i)).toFixed(i ? 1 : 0) + " " + units[i];
  }
  function fmtDur(s) {
    if (!s) return "-";
    s = Math.round(s);
    return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
  }

  function MixcutPage() {
    var capsState = React.useState(null);
    var caps = capsState[0], setCaps = capsState[1];
    var clipsState = React.useState([]);
    var clips = clipsState[0], setClips = clipsState[1];
    var jobsState = React.useState([]);
    var jobs = jobsState[0], setJobs = jobsState[1];
    var errState = React.useState("");
    var err = errState[0], setErr = errState[1];
    var busyState = React.useState(false);
    var busy = busyState[0], setBusy = busyState[1];

    // 工程编辑状态
    var projNameState = React.useState("我的混剪");
    var projName = projNameState[0], setProjName = projNameState[1];
    var resState = React.useState("1080p 横屏");
    var resolution = resState[0], setResolution = resState[1];
    var timelineState = React.useState([]);
    var timeline = timelineState[0], setTimeline = timelineState[1];
    var bgmVolState = React.useState(0.3);
    var bgmVol = bgmVolState[0], setBgmVol = bgmVolState[1];
    var subtitleState = React.useState("");
    var subtitle = subtitleState[0], setSubtitle = subtitleState[1];
    var wmState = React.useState("");
    var watermark = wmState[0], setWatermark = wmState[1];

    function refresh() {
      api("/clips").then(function (d) { setClips(d.clips || []); }).catch(function () {});
      api("/jobs").then(function (d) { setJobs(d.jobs || []); }).catch(function () {});
    }

    React.useEffect(function () {
      api("/capabilities").then(setCaps).catch(function (e) { setErr("能力探测失败：" + e.message); });
      refresh();
    }, []);
    React.useEffect(function () {
      var t = setInterval(refresh, 1500);
      return function () { clearInterval(t); };
    }, []);

    function onUpload(ev) {
      var f = ev.target.files && ev.target.files[0];
      if (!f) return;
      setBusy(true); setErr("");
      var fd = new FormData();
      fd.append("file", f);
      fetch(getApiUrl(BASE + "/clips"), { method: "POST", body: fd, headers: authHeaders() })
        .then(function (r) { if (!r.ok) return r.text().then(function (t) { throw new Error(t); }); return r.json(); })
        .then(refresh)
        .catch(function (e) { setErr("上传失败：" + e.message); })
        .finally(function () { setBusy(false); ev.target.value = ""; });
    }
    function onBgm(ev) {
      var f = ev.target.files && ev.target.files[0];
      if (!f) return;
      setBusy(true);
      var fd = new FormData();
      fd.append("file", f);
      fetch(getApiUrl(BASE + "/bgm"), { method: "POST", body: fd, headers: authHeaders() })
        .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); })
        .then(function () { setErr(""); })
        .catch(function (e) { setErr("BGM 上传失败：" + e.message); })
        .finally(function () { setBusy(false); ev.target.value = ""; });
    }
    function addToTimeline(clip) {
      setTimeline(timeline.concat([{
        clip_id: clip.clip_id, name: clip.name, duration: clip.duration || 0,
        trim_start: 0, trim_end: 0, transition: "交叉溶解", transition_duration: 0.5
      }]));
    }
    function updateItem(i, patch) {
      setTimeline(timeline.map(function (item, idx) { return idx === i ? Object.assign({}, item, patch) : item; }));
    }
    function removeItem(i) { setTimeline(timeline.filter(function (_, idx) { return idx !== i; })); }
    function move(i, dir) {
      var j = i + dir;
      if (j < 0 || j >= timeline.length) return;
      var next = timeline.slice();
      var tmp = next[i]; next[i] = next[j]; next[j] = tmp;
      setTimeline(next);
    }
    function submitProject() {
      setErr("");
      if (!timeline.length) { setErr("请先把片段加入时间线"); return; }
      api("/projects", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: projName, resolution: resolution,
          timeline: timeline.map(function (t) {
            return { clip_id: t.clip_id, trim_start: t.trim_start, trim_end: t.trim_end,
                     transition: t.transition, transition_duration: t.transition_duration };
          }),
          bgm_volume: bgmVol, subtitle_text: subtitle, watermark: watermark
        })
      }).then(function (p) {
        return api("/projects/" + p.project_id + "/render", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ project_id: p.project_id }) });
      }).then(refresh).catch(function (e) { setErr(e.message); });
    }
    function cancel(jobId) {
      api("/jobs/" + jobId + "/cancel", { method: "POST" }).then(refresh).catch(function (e) { setErr(e.message); });
    }
    function downloadJob(jobId, name) {
      fetch(getApiUrl(BASE + "/jobs/" + jobId + "/download"), { headers: authHeaders() })
        .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.blob(); })
        .then(function (blob) {
          var url = URL.createObjectURL(blob);
          var a = document.createElement("a");
          a.href = url; a.download = name || "mixcut.mp4";
          document.body.appendChild(a); a.click(); a.remove();
          URL.revokeObjectURL(url);
        }).catch(function (e) { setErr("下载失败：" + e.message); });
    }

    var labelStyle = { display: "block", fontSize: 12, color: "#5b6472", margin: "10px 0 4px" };
    var inputStyle = { width: "100%", padding: "7px 9px", border: "1px solid #d0d5dd", borderRadius: 6, fontSize: 13, boxSizing: "border-box" };
    var running = (jobs || []).some(function (j) { return j.status === "running"; });

    return h("div", { style: { padding: 24, height: "100%", overflow: "auto", background: "#f7f8fa" } },
      h("div", { style: { maxWidth: 1100, margin: "0 auto" } },
        h("h2", { style: { margin: "0 0 4px" } }, "🎞️ QwenPaw Creator · 智能混剪"),
        h("p", { style: { color: "#667085", margin: "0 0 16px" } },
          "上传片段 → 拖入时间线（裁剪/转场）→ 配 BGM、字幕、水印 → 一键渲染。"),
        err ? h("div", { style: { background: "#fef3f2", border: "1px solid #fecdca", color: "#b42318", borderRadius: 8, padding: "8px 12px", marginBottom: 12, fontSize: 13 } }, err) : null,

        // 素材库
        h("div", { style: { background: "#fff", border: "1px solid #e3e8ef", borderRadius: 10, padding: 16, marginBottom: 16 } },
          h("div", { style: { display: "flex", gap: 8, marginBottom: 10, alignItems: "center" } },
            h("b", null, "素材片段"),
            h("label", { style: { padding: "6px 12px", background: "#1f5ed6", color: "#fff", borderRadius: 6, fontSize: 13, cursor: "pointer" } },
              busy ? "处理中…" : "⬆ 上传片段", h("input", { type: "file", accept: "video/*", style: { display: "none" }, onChange: onUpload })),
            h("label", { style: { padding: "6px 12px", border: "1px solid #d0d5dd", borderRadius: 6, fontSize: 13, cursor: "pointer" } },
              "🎵 上传 BGM", h("input", { type: "file", accept: "audio/*", style: { display: "none" }, onChange: onBgm }))),
          clips.length === 0 ? h("div", { style: { color: "#98a2b3", fontSize: 13 } }, "暂无片段") :
          h("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(210px, 1fr))", gap: 8 } },
            clips.map(function (c) {
              return h("div", { key: c.clip_id, style: { border: "1px solid #e3e8ef", borderRadius: 8, padding: 10, fontSize: 12 } },
                h("div", { style: { fontWeight: 600, marginBottom: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } }, c.name),
                h("div", { style: { color: "#667085" } },
                  (c.width || "?") + "×" + (c.height || "?") + " · " + fmtDur(c.duration) + " · " + fmtBytes(c.size)),
                h("button", { onClick: function () { addToTimeline(c); }, style: { marginTop: 6, padding: "4px 10px", border: "none", background: "#12b76a", color: "#fff", borderRadius: 5, cursor: "pointer" } }, "＋ 时间线"));
            }))),

        // 时间线
        h("div", { style: { background: "#fff", border: "1px solid #e3e8ef", borderRadius: 10, padding: 16, marginBottom: 16 } },
          h("b", null, "时间线"),
          timeline.length === 0 ? h("div", { style: { color: "#98a2b3", fontSize: 13, marginTop: 8 } }, "从上方素材库添加片段") :
          timeline.map(function (t, i) {
            return h("div", { key: i, style: { display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap", padding: "8px 0", borderBottom: "1px solid #f0f2f5", fontSize: 13 } },
              h("span", { style: { background: "#eef4ff", borderRadius: 5, padding: "2px 8px", color: "#1f5ed6", fontWeight: 600 } }, (i + 1)),
              h("span", { style: { minWidth: 130, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } }, t.name),
              h("label", { style: { fontSize: 11, color: "#667085" } }, "入点",
                h("input", { type: "number", min: 0, step: 0.5, value: t.trim_start, style: { width: 62, marginLeft: 4 }, onChange: function (e) { updateItem(i, { trim_start: parseFloat(e.target.value) || 0 }); } })),
              h("label", { style: { fontSize: 11, color: "#667085" } }, "出点(0=片尾)",
                h("input", { type: "number", min: 0, step: 0.5, value: t.trim_end, style: { width: 62, marginLeft: 4 }, onChange: function (e) { updateItem(i, { trim_end: parseFloat(e.target.value) || 0 }); } })),
              caps ? h("select", { value: t.transition, style: { fontSize: 12 }, onChange: function (e) { updateItem(i, { transition: e.target.value }); } },
                caps.transitions.map(function (tr) { return h("option", { key: tr, value: tr }, tr); })) : null,
              h("button", { onClick: function () { move(i, -1); }, style: { fontSize: 12 } }, "↑"),
              h("button", { onClick: function () { move(i, 1); }, style: { fontSize: 12 } }, "↓"),
              h("button", { onClick: function () { removeItem(i); }, style: { fontSize: 12, color: "#b42318" } }, "✕"));
          }),

          // 工程参数
          h("div", { style: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 10, marginTop: 12 } },
            h("div", null, h("label", { style: labelStyle }, "工程名称"),
              h("input", { style: inputStyle, value: projName, onChange: function (e) { setProjName(e.target.value); } })),
            caps ? h("div", null, h("label", { style: labelStyle }, "输出分辨率"),
              h("select", { style: inputStyle, value: resolution, onChange: function (e) { setResolution(e.target.value); } },
                caps.resolutions.map(function (r) { return h("option", { key: r, value: r }, r); }))) : null,
            h("div", null, h("label", { style: labelStyle }, "BGM 音量：" + Math.round(bgmVol * 100) + "%"),
              h("input", { type: "range", min: 0, max: 1, step: 0.05, value: bgmVol, style: { width: "100%" }, onChange: function (e) { setBgmVol(parseFloat(e.target.value)); } })),
            h("div", null, h("label", { style: labelStyle }, "片头字幕（前 6 秒）"),
              h("input", { style: inputStyle, value: subtitle, onChange: function (e) { setSubtitle(e.target.value); }, placeholder: "如：灵泽万川智造云 企业宣传片" })),
            h("div", null, h("label", { style: labelStyle }, "水印文字"),
              h("input", { style: inputStyle, value: watermark, onChange: function (e) { setWatermark(e.target.value); }, placeholder: "如：灵泽万川" }))),
          h("button", { onClick: submitProject, disabled: running, style: { marginTop: 14, padding: "8px 22px", border: "none", background: running ? "#cbd5e1" : "#1f5ed6", color: "#fff", borderRadius: 6, fontSize: 14, cursor: running ? "default" : "pointer" } },
            running ? "渲染中…" : "🎬 一键渲染")),

        // 任务
        h("div", { style: { background: "#fff", border: "1px solid #e3e8ef", borderRadius: 10, padding: 16 } },
          h("b", null, "渲染任务"),
          jobs.length === 0 ? h("div", { style: { color: "#98a2b3", fontSize: 13, marginTop: 8 } }, "暂无任务") :
          jobs.map(function (j) {
            var pct = Math.round((j.progress || 0) * 100);
            return h("div", { key: j.job_id, style: { padding: "10px 0", borderBottom: "1px solid #f0f2f5", fontSize: 13 } },
              h("div", { style: { display: "flex", justifyContent: "space-between", marginBottom: 6 } },
                h("span", null, (j.output_name || "") + (j.output_size ? " · " + fmtBytes(j.output_size) : "")),
                h("span", { style: { color: j.status === "failed" ? "#b42318" : "#5b6472" } },
                  j.status === "running" ? "渲染中 " + pct + "%" : j.status === "done" ? "完成" :
                  j.status === "failed" ? "失败：" + (j.error || "").slice(0, 120) : j.status)),
              h("div", { style: { background: "#eef2f6", borderRadius: 5, height: 8, overflow: "hidden", marginBottom: 6 } },
                h("div", { style: { width: (j.status === "done" ? 100 : pct) + "%", height: "100%", background: j.status === "failed" ? "#f04438" : j.status === "done" ? "#12b76a" : "#1f5ed6" } })),
              j.status === "running" ? h("button", { onClick: function () { cancel(j.job_id); }, style: { padding: "2px 10px", fontSize: 12 } }, "取消") : null,
              j.status === "done" ? h("button", { onClick: function () { downloadJob(j.job_id, j.output_name); }, style: { padding: "2px 10px", fontSize: 12, background: "#12b76a", color: "#fff", border: "none", borderRadius: 5, cursor: "pointer" } }, "⬇ 下载") : null);
          }))));
  }

  if (Q.registerRoutes) {
    Q.registerRoutes("qwenpaw-creator-mixcut", [{ path: "/apps/qwenpaw-creator-mixcut", component: MixcutPage, label: "智能混剪", icon: "🎞️", priority: 79 }]);
  }
})();
