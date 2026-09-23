/* AI数据中枢入口（Hub 模式注入式，与销售分析/财务中枢同机制）
 * 侧边栏注册「AI数据中枢」，路由 /apps/datahub 注入全屏 iframe（18790，免登录）
 */
(function () {
  function onDhPage() { return window.location.pathname === '/apps/datahub'; }

  function ensureFrame() {
    var main = document.querySelector('main');
    var wrap = document.getElementById('datahub-app-frame-wrap');
    if (onDhPage() && main && !wrap) {
      wrap = document.createElement('div');
      wrap.id = 'datahub-app-frame-wrap';
      wrap.style.cssText = 'position:absolute;inset:0;z-index:1;';
      var f = document.createElement('iframe');
      f.src = '/datahub-dashboard.html';  // 同源控制台页(全量内嵌数据, 任何能开 Hub 的网络都可见; 原 18790 直连在外网隧道下空白)
      f.title = 'AI数据中枢';
      f.style.cssText = 'width:100%;height:100%;border:none;display:block;background:#f7f8fa';
      wrap.appendChild(f);
      if (getComputedStyle(main).position === 'static') main.style.position = 'relative';
      main.appendChild(wrap);
    } else if (!onDhPage() && wrap) {
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
    if (Q.__datahubAppRegistered) return;
    Q.__datahubAppRegistered = true;
    try {
      Q.route.add('zhiyun-datahub-app', {
        id: 'zhiyun-datahub-app.open',
        path: '/apps/datahub',
        component: function () { return Q.host.React.createElement('div'); }
      });
      Q.menu.add('zhiyun-datahub-app', {
        id: 'zhiyun-datahub-app.menu',
        label: 'AI数据中枢',
        route: 'zhiyun-datahub-app.open',
        location: 'primary.agentScoped',
        order: 0,
        icon: 'file'
      });
      console.log('[zhiyun-datahub-app] menu registered');
    } catch (e) {
      console.warn('[zhiyun-datahub-app] register failed:', e && e.message);
    }
  })();
})();
