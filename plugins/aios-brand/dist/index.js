/* 智造云AIOS 品牌层（前端扩展）
 * 全部通过 window.QwenPaw.* 官方扩展点实现，不触碰宿主构建产物，
 * 因此 QwenPaw 运行时升级不需要重建品牌层（issue #126）。
 * 能力：
 *   1) Q.slot.replace('header.logo')   —— 顶栏 Logo（含点击放大态）
 *   2) Q.route.add + Q.menu.add        —— 帮助中心页面与侧边栏入口
 *   3) 主题：CSS 变量级换肤 + Q.chat.theme.set 主色
 *   4) 观察者隐藏顶栏外链入口（GitHub / 文档资料——文档已由帮助中心取代）
 */
(function () {
  var Q = window.QwenPaw;
  var pluginId = 'aios-brand';
  if (!Q || !Q.slot || !Q.host || !Q.host.React) return;
  var React = Q.host.React;

  var LOGO = '/api/frontend_plugin/aios-brand/files/assets/brand-logo.png';
  var BRAND = { primary: '#0086AD', primaryHover: '#00A3C4', primaryActive: '#00688A', accent: '#0055A5' };

  /* ── 1) 顶栏 Logo 槽位替换 ─────────────────────────────── */
  try {
    Q.slot.replace(pluginId, 'header.logo', function () {
      return React.createElement('img', {
        src: LOGO,
        alt: '智造云AIOS',
        style: { height: 32, width: 'auto', maxWidth: 220, objectFit: 'contain' }
      });
    }, { id: 'aios-brand.header-logo' });
  } catch (e) { console.warn('[aios-brand] header.logo slot:', e && e.message); }

  /* ── 2) 帮助中心：路由 + 侧边栏菜单 ────────────────────── */
  try {
    Q.route.add(pluginId, {
      id: 'aios-brand.help',
      path: '/aios-brand-help',
      component: function () {
        return React.createElement('iframe', {
          src: '/aios-docs.html',
          title: '智造云AIOS 帮助中心',
          style: { width: '100%', height: '100%', border: 'none', display: 'block', background: '#fff' }
        });
      }
    });
    Q.menu.add(pluginId, {
      id: 'aios-brand.help-menu',
      label: '帮助中心',
      route: 'aios-brand.help',
      location: 'primary.settings',
      order: 5
    });
  } catch (e) { console.warn('[aios-brand] route/menu:', e && e.message); }

  /* ── 3) 主题：CSS 变量覆盖 + 聊天主色 ──────────────────── */
  function injectTheme() {
    if (document.getElementById('aios-brand-theme')) return;
    var p = BRAND.primary, h = BRAND.primaryHover, a = BRAND.primaryActive;
    var bg = '#E8F5F9', bgHover = '#CDEAF2', border = '#8FD1E0', borderHover = '#5FBBD0';
    var css = [
      ':root{--zy-brand:' + p + ';}',
      ':root,html .css-var-r0{',
      '--qwenpaw-color-primary:' + p + ';--qwenpaw-color-primary-hover:' + h + ';--qwenpaw-color-primary-active:' + a + ';',
      '--qwenpaw-color-primary-bg:' + bg + ';--qwenpaw-color-primary-bg-hover:' + bgHover + ';',
      '--qwenpaw-color-primary-border:' + border + ';--qwenpaw-color-primary-border-hover:' + borderHover + ';',
      '--qwenpaw-color-primary-text:' + p + ';--qwenpaw-color-primary-text-hover:' + h + ';--qwenpaw-color-primary-text-active:' + a + ';',
      '--qwenpaw-color-link:' + p + ';--qwenpaw-color-link-hover:' + h + ';--qwenpaw-color-link-active:' + a + ';',
      '--qwenpaw-input-active-border-color:' + p + ';--qwenpaw-input-hover-border-color:' + h + ';',
      '--qwenpaw-input-active-shadow:0 0 0 2px ' + p + '1a;--qwenpaw-control-outline:' + p + '1a;',
      '--qwenpaw-control-item-bg-active:' + bg + ';--qwenpaw-control-item-bg-active-hover:' + bgHover + ';',
      '--qwenpaw-button-group-border-color:' + p + ';}',
      'a{color:' + p + ';}'
    ].join('\n');
    var style = document.createElement('style');
    style.id = 'aios-brand-theme';
    style.textContent = css;
    document.head.appendChild(style);
  }
  injectTheme();
  try {
    Q.chat.theme.set(pluginId, { colorPrimary: BRAND.primary });
  } catch (e) { /* chat.theme 在旧版缺失时忽略 */ }

  /* ── 4) 隐藏顶栏外链入口（文本观察器，不依赖压缩类名） ── */
  var HIDE_TEXTS = ['GitHub', '文档资料'];
  function hideExternalButtons(root) {
    var scope = root || document;
    var buttons = scope.querySelectorAll ? scope.querySelectorAll('header button, [class*="header"] button') : [];
    for (var i = 0; i < buttons.length; i++) {
      var b = buttons[i];
      var text = (b.textContent || '').replace(/\s+/g, '');
      for (var t = 0; t < HIDE_TEXTS.length; t++) {
        if (text.indexOf(HIDE_TEXTS[t]) !== -1) {
          b.style.display = 'none';
          break;
        }
      }
    }
  }
  hideExternalButtons(document.body);
  try {
    var observer = new MutationObserver(function (records) {
      for (var i = 0; i < records.length; i++) hideExternalButtons(records[i].target);
    });
    observer.observe(document.body, { childList: true, subtree: true });
  } catch (e) { /* 老浏览器无 observer 时仅在加载时隐藏一次 */ }
})();
