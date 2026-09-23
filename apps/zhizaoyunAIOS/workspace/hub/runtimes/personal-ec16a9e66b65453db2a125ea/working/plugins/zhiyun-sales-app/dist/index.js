/* 销售分析平台入口（Hub 模式注入式，与合同管理/财务中枢同机制）
 * 侧边栏注册「销售分析平台」，路由 /apps/sales 注入全屏 iframe（8302，免登录）
 */
(function () {
  function onSalesPage() { return window.location.pathname === '/apps/sales'; }

  function ensureFrame() {
    var main = document.querySelector('main');
    var wrap = document.getElementById('sales-app-frame-wrap');
    if (onSalesPage() && main && !wrap) {
      wrap = document.createElement('div');
      wrap.id = 'sales-app-frame-wrap';
      wrap.style.cssText = 'position:absolute;inset:0;z-index:1;';
      var f = document.createElement('iframe');
      f.src = 'http://' + window.location.hostname + ':8302/';
      f.title = '销售分析平台';
      f.style.cssText = 'width:100%;height:100%;border:none;display:block;background:#f0f2f5';
      wrap.appendChild(f);
      if (getComputedStyle(main).position === 'static') main.style.position = 'relative';
      main.appendChild(wrap);
    } else if (!onSalesPage() && wrap) {
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
    if (Q.__salesAppRegistered) return;
    Q.__salesAppRegistered = true;
    try {
      Q.route.add('zhiyun-sales-app', {
        id: 'zhiyun-sales-app.open',
        path: '/apps/sales',
        component: function () { return Q.host.React.createElement('div'); }
      });
      Q.menu.add('zhiyun-sales-app', {
        id: 'zhiyun-sales-app.menu',
        label: '智能销售分析',
        route: 'zhiyun-sales-app.open',
        location: 'primary.agentScoped',
        order: 2,
        icon: 'file'
      });
      console.log('[zhiyun-sales-app] menu registered');
    } catch (e) {
      console.warn('[zhiyun-sales-app] register failed:', e && e.message);
    }
  })();
})();
