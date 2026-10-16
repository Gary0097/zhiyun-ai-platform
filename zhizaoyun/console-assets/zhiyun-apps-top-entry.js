/* 智造云七大功能前端统一排序置顶（只改前端显示）
 * 1) 注册「AI智能数据中枢」入口（内嵌经营看板 /datahub-dashboard.html）
 * 2) 侧边栏（展开/收起两种形态）用 CSS order 将七大功能按钮按固定顺序置顶：
 *    AI智能数据中枢 → 智能订单处理中心 → 智能客服与客户运营 → 智能采购管理
 *    → 销售智能分析 → 财务智能化中枢 → 管理协同中心
 * 仅设置 style.order（flex 布局），不移动 React 管理的 DOM 节点，重渲染后由轮询自动补齐。
 */
function __init() {
  var APP_ORDER = [
    'AI智能数据中枢',
    '智能订单处理中心',
    '智能客服与客户运营',
    '智能采购管理',
    '销售智能分析',
    '财务智能化中枢',
    '管理协同中心'
  ];

  /* ---------- AI智能数据中枢：路由 + 占位页（建设中） ---------- */
  function onDatahubPage() { return window.location.pathname === '/apps/datahub'; }

  function ensureDatahubView() {
    var main = document.querySelector('main');
    var wrap = document.getElementById('zhiyun-datahub-placeholder');
    if (onDatahubPage() && main && !wrap) {
      wrap = document.createElement('div');
      wrap.id = 'zhiyun-datahub-placeholder';
      wrap.style.cssText = 'position:absolute;inset:0;z-index:1;background:#f5f7fa;';
      var ifr = document.createElement('iframe');
      ifr.src = '/datahub-dashboard.html';
      ifr.title = 'AI智能数据中枢 · 经营看板';
      ifr.style.cssText = 'width:100%;height:100%;border:0;background:#fff;display:block;';
      var bar = document.createElement('div');
      bar.style.cssText = 'position:absolute;top:10px;right:16px;z-index:3;display:flex;gap:10px;align-items:center;font:12px/1.6 "PingFang SC","Microsoft YaHei",system-ui,sans-serif;color:rgba(255,255,255,.92);';
      bar.innerHTML = '<span style="opacity:.85">数据快照 2026-09-18 08:00 · 与问数同源</span>'
        + '<a href="/datahub-dashboard.html" target="_blank" style="color:#fff;background:rgba(0,0,0,.18);border-radius:6px;padding:2px 10px;text-decoration:none;">新窗口打开</a>'
        + '<a href="http://127.0.0.1:18790/sql.html" target="_blank" style="color:#fff;background:rgba(0,0,0,.18);border-radius:6px;padding:2px 10px;text-decoration:none;">SQL 查询台</a>'
        + '<a href="http://192.168.2.10:18790/" target="_blank" style="color:#fff;background:rgba(0,0,0,.18);border-radius:6px;padding:2px 10px;text-decoration:none;">内网直连</a>';
      wrap.appendChild(ifr);
      wrap.appendChild(bar);
      if (getComputedStyle(main).position === 'static') main.style.position = 'relative';
      main.appendChild(wrap);
    } else if (!onDatahubPage() && wrap) {
      wrap.remove();
    }
  }

  ['pushState', 'replaceState'].forEach(function (m) {
    var orig = history[m];
    history[m] = function () { var r = orig.apply(this, arguments); setTimeout(ensureDatahubView, 60); return r; };
  });
  window.addEventListener('popstate', function () { setTimeout(ensureDatahubView, 60); });
  setInterval(ensureDatahubView, 1000);

  var tries = 0;
  (function bootRegister() {
    var Q = window.QwenPaw;
    if (!Q || !Q.route || !Q.menu || !Q.host || !Q.host.React) {
      if (++tries > 100) return;
      return setTimeout(bootRegister, 300);
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
        label: 'AI智能数据中枢',
        route: 'zhiyun-datahub-app.open',
        location: 'primary.agentScoped',
        order: 1,
      });
      console.log('[zhiyun-datahub-app] menu registered');
    } catch (e) {
      console.warn('[zhiyun-datahub-app] register failed:', e && e.message);
    }
  })();

  /* ---------- 侧边栏置顶排序（CSS order，兼容展开/收起） ---------- */
  function findAppBtn(label) {
    var btns = document.querySelectorAll('button');
    for (var i = 0; i < btns.length; i++) {
      var b = btns[i];
      var t = ((b.textContent || '') + ' ' + (b.getAttribute('aria-label') || '')).replace(/\s+/g, '');
      if (t.indexOf(label) >= 0) return b;
    }
    return null;
  }

  function applyOrder() {
    // 仅处理 flex 容器内的按钮；置顶顺序 = 负 order（其余内置项默认 0）
    for (var i = 0; i < APP_ORDER.length; i++) {
      var btn = findAppBtn(APP_ORDER[i]);
      if (!btn || !btn.parentElement) continue;
      var c = btn.parentElement;
      var disp = getComputedStyle(c).display;
      if (disp !== 'flex' && disp !== 'grid') continue;
      var want = String(i - APP_ORDER.length); // -7 .. -1
      if (btn.style.order !== want) btn.style.order = want;
    }
  }
  setInterval(applyOrder, 800);
  applyOrder();
}
var __ENT_BLOCK_TOP=null;(function(){var t=null;try{t=localStorage.getItem('qwenpaw_auth_token');}catch(e){}
fetch('/api/hub/me',{headers:{Authorization:'Bearer '+(t||'')}}).then(function(r){return r.ok?r.json():{};}).then(function(d){
var u=(d&&d.username)||'';__ENT_BLOCK_TOP=(u&&__ENT_ALL.indexOf(u)>=0);if(!__ENT_BLOCK_TOP)__init();}).catch(function(){__ENT_BLOCK_TOP=false;__init();});})();
var __ENT_ALL=["hongjia", "jietaike", "yangcheng", "datie", "dajian", "jinhaolong", "ruibote", "chengxu", "haomingda", "nafeng", "fengyuan", "kashite", "gaoyimei"];
