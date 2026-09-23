/* 管理协同中心入口（Hub 模式注入式，与销售分析/财务中枢同机制）
 * 侧边栏注册「管理协同中心」，路由 /apps/mcc 注入全屏 iframe（8310，免登录）
 */
(function () {
  function onMccPage() { return window.location.pathname === '/apps/mcc'; }

  function ensureFrame() {
    var main = document.querySelector('main');
    var wrap = document.getElementById('mcc-app-frame-wrap');
    if (onMccPage() && main && !wrap) {
      wrap = document.createElement('div');
      wrap.id = 'mcc-app-frame-wrap';
      wrap.style.cssText = 'position:absolute;inset:0;z-index:1;';
      var f = document.createElement('iframe');
      f.src = 'http://' + window.location.hostname + ':8310/';
      f.title = '管理协同中心';
      f.style.cssText = 'width:100%;height:100%;border:none;display:block;background:#f0f2f5';
      wrap.appendChild(f);
      if (getComputedStyle(main).position === 'static') main.style.position = 'relative';
      main.appendChild(wrap);
    } else if (!onMccPage() && wrap) {
      wrap.remove();
    }
  }

  ['pushState', 'replaceState'].forEach(function (m) {
    var orig = history[m];
    history[m] = function () { var r = orig.apply(this, arguments); setTimeout(ensureFrame, 60); return r; };
  });
  window.addEventListener('popstate', function () { setTimeout(ensureFrame, 60); });
  setInterval(ensureFrame, 1000);

  var tries = 0;
  (function boot() {
    var Q = window.QwenPaw;
    if (!Q || !Q.route || !Q.menu || !Q.host || !Q.host.React) {
      if (++tries > 100) return;
      return setTimeout(boot, 300);
    }
    if (Q.__mccAppRegistered) return;
    Q.__mccAppRegistered = true;
    try {
      Q.route.add('zhiyun-mcc-app', {
        id: 'zhiyun-mcc-app.open',
        path: '/apps/mcc',
        component: function () { return Q.host.React.createElement('div'); }
      });
      Q.menu.add('zhiyun-mcc-app', {
        id: 'zhiyun-mcc-app.menu',
        label: '管理协同中心',
        route: 'zhiyun-mcc-app.open',
        location: 'primary.agentScoped',
        order: 4,
        icon: 'file'
      });
      console.log('[zhiyun-mcc-app] menu registered');
    } catch (e) {
      console.warn('[zhiyun-mcc-app] register failed:', e && e.message);
    }
  })();
})();
