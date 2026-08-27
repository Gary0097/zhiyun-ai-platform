const fs = require('fs');
const f = 'apps/qwenpaw-embedded/runtime/qwenpaw/venv/Lib/site-packages/qwenpaw/console/assets/index-BgAgmp-n.js';
const c = fs.readFileSync(f, 'utf8');
for (const pat of ['currentAgent','agentSelect','agentSelector','current_agent','workspace.switch','agent-switch','workspaces','WorkspaceSwitcher','WorkspaceToggle','onToggleWorkspace']) {
  let idx = 0, n = 0;
  while ((idx = c.indexOf(pat, idx)) !== -1) {
    console.log('### ' + pat + ' occ ' + (++n) + ' @ ' + idx);
    console.log(c.slice(Math.max(0, idx-160), idx + pat.length + 160).replace(/\n/g, '\\n'));
    console.log();
    idx += pat.length;
    if (n >= 3) break;
  }
  if (n === 0) console.log('### ' + pat + ' : none');
}
