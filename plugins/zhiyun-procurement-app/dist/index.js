/* 智能采购管理入口（Hub 模式注入式，与销售分析/财务中枢同机制）
 * 侧边栏注册「智能采购管理」，路由 /apps/procurement 注入全屏 iframe（8002，免登录）
 */
(function () {
  function onProcurementPage() { return window.location.pathname === '/apps/procurement'; }

  function ensureFrame() {
    var main = document.querySelector('main');
    var wrap = document.getElementById('procurement-app-frame-wrap');
    if (onProcurementPage() && main && !wrap) {
      wrap = document.createElement('div');
      wrap.id = 'procurement-app-frame-wrap';
      wrap.style.cssText = 'position:absolute;inset:0;z-index:1;';
      var f = document.createElement('iframe');
      f.src = 'http://' + window.location.hostname + ':8002/';
      f.title = '智能采购管理';
      f.style.cssText = 'width:100%;height:100%;border:none;display:block;background:#f0f2f5';
      wrap.appendChild(f);
      if (getComputedStyle(main).position === 'static') main.style.position = 'relative';
      main.appendChild(wrap);
    } else if (!onProcurementPage() && wrap) {
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
    if (Q.__procurementAppRegistered) return;
    Q.__procurementAppRegistered = true;
    try {
      Q.route.add('zhiyun-procurement-app', {
        id: 'zhiyun-procurement-app.open',
        path: '/apps/procurement',
        component: function () { return Q.host.React.createElement('div'); }
      });
      Q.menu.add('zhiyun-procurement-app', {
        id: 'zhiyun-procurement-app.menu',
        label: '智能采购管理',
        route: 'zhiyun-procurement-app.open',
        location: 'primary.agentScoped',
        order: 5,
        icon: 'file'
      });
      console.log('[zhiyun-procurement-app] menu registered');
    } catch (e) {
      console.warn('[zhiyun-procurement-app] register failed:', e && e.message);
    }
  })();
})();
