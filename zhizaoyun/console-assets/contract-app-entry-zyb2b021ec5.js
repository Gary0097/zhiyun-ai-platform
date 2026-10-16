var ENT_ERP_PORT={"hongjia": 18901, "jietaike": 18902, "yangcheng": 18903, "datie": 18904, "ruibote": 18907, "chengxu": 18908, "nafeng": 18910, "fengyuan": 18911, "kashite": 18912};
/* 合同管理系统入口（前端扩展）
 * Q.route.add 内嵌 iframe 打开 contract-ui（8299），iframe 内自动走 /sso-token 免密登录。
 * src 使用当前访问的主机名动态拼接，localhost 与局域网 IP 访问都能命中隧道端口。
 */
(function () {
  var Q = window.QwenPaw;
  var pluginId = 'zhiyun-contract-app';
  if (!Q || !Q.route || !Q.menu || !Q.host || !Q.host.React) return;
  var React = Q.host.React;

  function contractSrc() {
    return 'http://' + window.location.hostname + ':8299/';
  }

  try {
    Q.route.add(pluginId, {
      id: 'zhiyun-contract-app.open',
      path: '/apps/contract',
      component: function () {
        return React.createElement('iframe', {
          src: contractSrc(),
          title: '合同管理系统',
          style: { width: '100%', height: '100%', border: 'none', display: 'block', background: '#fff' }
        });
      }
    });
    Q.menu.add(pluginId, {
      id: 'zhiyun-contract-app.menu',
      label: '合同管理',
      route: 'zhiyun-contract-app.open',
      location: 'primary.agentScoped',
      order: 1,
      icon: 'file'
    });
  } catch (e) {
    console.warn('[zhiyun-contract-app] route/menu:', e && e.message);
  }
})();
