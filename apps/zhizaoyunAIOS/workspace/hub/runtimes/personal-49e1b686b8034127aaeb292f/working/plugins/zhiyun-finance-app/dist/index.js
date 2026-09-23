/* 财务智能化中枢入口（Hub 模式注入式，与合同管理同机制）
 * 1) Q.menu.add 在侧边栏注册「财务智能化中枢」，Q.route.add 占位路由 /apps/finance
 * 2) 轮询 + history 钩子：进入 /apps/finance 时向 main 注入全屏 iframe
 * 3) iframe 地址按当前主机名拼 8301，应用本身免登录直接打开
 */
(function () {
  function onFinancePage() { return window.location.pathname === '/apps/finance'; }

  function ensureFrame() {
    var main = document.querySelector('main');
    var wrap = document.getElementById('finance-app-frame-wrap');
    if (onFinancePage() && main && !wrap) {
      wrap = document.createElement('div');
      wrap.id = 'finance-app-frame-wrap';
      wrap.style.cssText = 'position:absolute;inset:0;z-index:1;';
      var f = document.createElement('iframe');
      f.src = 'http://' + window.location.hostname + ':8301/';
      f.title = '财务智能化中枢';
      f.style.cssText = 'width:100%;height:100%;border:none;display:block;background:#f0f2f5';
      wrap.appendChild(f);
      if (getComputedStyle(main).position === 'static') main.style.position = 'relative';
      main.appendChild(wrap);
    } else if (!onFinancePage() && wrap) {
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
    if (Q.__financeAppRegistered) return;
    Q.__financeAppRegistered = true;
    try {
      Q.route.add('zhiyun-finance-app', {
        id: 'zhiyun-finance-app.open',
        path: '/apps/finance',
        component: function () { return Q.host.React.createElement('div'); }
      });
      Q.menu.add('zhiyun-finance-app', {
        id: 'zhiyun-finance-app.menu',
        label: '财务智能化中枢',
        route: 'zhiyun-finance-app.open',
        location: 'primary.agentScoped',
        order: 1,
        icon: 'file'
      });
      console.log('[zhiyun-finance-app] menu registered');
    } catch (e) {
      console.warn('[zhiyun-finance-app] register failed:', e && e.message);
    }
  })();
})();
