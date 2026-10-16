/* 财务智能化中枢 入口（按合同可见性差异化 v20261008）
 * 企业账号按合同模块决定是否注册菜单；运营方账号不受限 */
(function () {
  var KEY = 'finance';
  var ENT_SEE = ["hongjia", "jietaike", "yangcheng", "datie", "dajian", "jinhaolong", "ruibote", "chengxu", "haomingda", "nafeng", "fengyuan", "kashite", "gaoyimei"];
  function onPage() { return window.location.pathname === '/apps/finance'; }
  function ensureFrame() {
    if (!window.__APP_OK_KEY) return;
    var main = document.querySelector('main');
    var wrap = document.getElementById('finance-app-frame-wrap');
    if (onPage() && main && !wrap) {
      wrap = document.createElement('div');
      wrap.id = 'finance-app-frame-wrap';
      wrap.style.cssText = 'position:absolute;inset:0;z-index:1;';
      var f = document.createElement('iframe');
      // 企业账号路由到专属财务实例(8311+), 运营方走共享8301
      var ENT_FIN = {"hongjia":8311,"jietaike":8312,"yangcheng":8313,"datie":8314,"dajian":8315,
        "jinhaolong":8316,"ruibote":8317,"chengxu":8318,"haomingda":8319,"nafeng":8320,
        "fengyuan":8321,"kashite":8322,"gaoyimei":8323};
      var u1 = ''; try { u1 = localStorage.getItem('qwenpaw_username') || ''; } catch (e) {}
      var port1 = ENT_FIN[u1] || 8301;
      f.src = 'http://' + window.location.hostname + ':' + port1 + '/';
      f.title = '财务智能化中枢';
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
        Q.route.add('zhiyun-finance-app', { id: 'zhiyun-finance-app.open', path: '/apps/finance',
          component: function () { return Q.host.React.createElement('div'); } });
        Q.menu.add('zhiyun-finance-app', { id: 'zhiyun-finance-app.menu', label: '财务智能化中枢', route: 'zhiyun-finance-app.open',
          location: 'primary.agentScoped', order: 1, icon: 'file' });
      } catch (e) {}
    })();
  }
  var t = null; try { t = localStorage.getItem('qwenpaw_auth_token'); } catch (e) {}
  fetch('/api/hub/me', { headers: { Authorization: 'Bearer ' + (t || '') } })
    .then(function (r) { return r.ok ? r.json() : {}; })
    .then(function (d) {
      var u = (d && d.username) || '';
      if (u) { try { localStorage.setItem('qwenpaw_username', u); } catch (e) {} }
      var blocked = ENT_SEE.length > 0 || ENT_SEE.indexOf(u) >= 0 ? false : true;
      if (u && ENT_SEE.indexOf(u) < 0 && true) blocked = true;
      window.__APP_OK_KEY = !blocked;
      if (!blocked) boot();
    })
    .catch(function () { window.__APP_OK_KEY = true; boot(); });
})();
