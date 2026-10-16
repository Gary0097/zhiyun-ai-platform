/* 销售智能分析 入口（按合同可见性差异化 v20261008）
 * 企业账号按合同模块决定是否注册菜单；运营方账号不受限 */
(function () {
  var KEY = 'sales';
  var ENT_SEE = [];
  function onPage() { return window.location.pathname === '/apps/sales'; }
  function ensureFrame() {
    if (!window.__APP_OK_KEY) return;
    var main = document.querySelector('main');
    var wrap = document.getElementById('sales-app-frame-wrap');
    if (onPage() && main && !wrap) {
      wrap = document.createElement('div');
      wrap.id = 'sales-app-frame-wrap';
      wrap.style.cssText = 'position:absolute;inset:0;z-index:1;';
      var f = document.createElement('iframe');
      f.src = 'http://' + window.location.hostname + ':8302/';
      f.title = '销售智能分析';
      f.style.cssText = 'width:100%;height:100%;border:none;display:block;background:#f0f2f5';
      wrap.appendChild(f);
      if (getComputedStyle(main).position === 'static') main.style.position = 'relative';
      main.appendChild(wrap);
    } else if (!onPage() && wrap) wrap.remove();
  }
  ['pushState','replaceState'].forEach(function (m) {
    var orig = history[m];
    history[m] = function () { var r = orig.apply(this, arguments); setTimeout(ensureFrame, 60); return r; };
  });
  window.addEventListener('popstate', function () { setTimeout(ensureFrame, 60); });
  setInterval(ensureFrame, 1000);
  function boot() {
    var tries = 0;
    (function start() {
      var Q = window.QwenPaw;
      if (!Q || !Q.route || !Q.menu || !Q.host || !Q.host.React) {
        if (++tries > 120) return;
        return setTimeout(start, 250);
      }
      try {
        Q.route.add('zhiyun-sales-app', { id: 'zhiyun-sales-app.open', path: '/apps/sales',
          component: function () { return Q.host.React.createElement('div'); } });
        Q.menu.add('zhiyun-sales-app', { id: 'zhiyun-sales-app.menu', label: '销售智能分析', route: 'zhiyun-sales-app.open',
          location: 'primary.agentScoped', order: 2, icon: 'file' });
      } catch (e) {}
    })();
  }
  var t = null; try { t = localStorage.getItem('qwenpaw_auth_token'); } catch (e) {}
  fetch('/api/hub/me', { headers: { Authorization: 'Bearer ' + (t || '') } })
    .then(function (r) { return r.ok ? r.json() : {}; })
    .then(function (d) {
      var u = (d && d.username) || '';
      var blocked = ENT_SEE.length > 0 || ENT_SEE.indexOf(u) >= 0 ? false : true;
      if (u && ENT_SEE.indexOf(u) < 0 && true) blocked = true;
      window.__APP_OK_KEY = !blocked;
      if (!blocked) boot();
    })
    .catch(function () { window.__APP_OK_KEY = true; boot(); });
})();
