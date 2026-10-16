/* 智能客服与客户运营 入口（按合同可见性差异化 v20261008）
 * 企业账号按合同模块决定是否注册菜单；运营方账号不受限 */
(function () {
  var KEY = 'cservice';
  var ENT_SEE = ["hongjia", "jietaike", "datie", "jinhaolong", "ruibote", "haomingda", "gaoyimei"];
  function onPage() { return window.location.pathname === '/apps/cservice'; }
  function ensureFrame() {
    if (!window.__APP_OK_KEY) return;
    var main = document.querySelector('main');
    var wrap = document.getElementById('cservice-app-frame-wrap');
    if (onPage() && main && !wrap) {
      wrap = document.createElement('div');
      wrap.id = 'cservice-app-frame-wrap';
      wrap.style.cssText = 'position:absolute;inset:0;z-index:1;';
      var f = document.createElement('iframe');
      var ent = '';
      try { var mt = localStorage.getItem('qwenpaw_user'); if (mt) ent = JSON.parse(mt).username || ''; } catch (e) {}
      if (!ent) { try { ent = localStorage.getItem('qwenpaw_username') || ''; } catch (e) {} }
      f.src = 'http://' + window.location.hostname + ':8001/autologin' + (ent ? '?ent=' + ent : '');
      f.title = '智能客服与客户运营';
      f.style.cssText = 'width:100%;height:100%;border:none;display:block;background:#fff';
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
        Q.route.add('zhiyun-cservice-app', { id: 'zhiyun-cservice-app.open', path: '/apps/cservice',
          component: function () { return Q.host.React.createElement('div'); } });
        Q.menu.add('zhiyun-cservice-app', { id: 'zhiyun-cservice-app.menu', label: '智能客服与客户运营', route: 'zhiyun-cservice-app.open',
          location: 'primary.agentScoped', order: 3, icon: 'file' });
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
