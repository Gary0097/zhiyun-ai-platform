// 从五大模板 Studio 的 ui/index.js 模块定义生成演示导入样例（CSV/TXT）。
// 表头使用列 label 原文，导入时与「导入 Excel/CSV」的表头映射完全一致。
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..', '..');
const RUNTIME = path.join(ROOT, 'apps', 'qwenpaw-embedded', 'runtime', 'pawapps');
const OUT = path.join(ROOT, 'docs', 'qa', 'demo-data');

const STUDIOS = [
  'zhiyun-sales-studio',
  'zhiyun-finance-studio',
  'zhiyun-people-studio',
  'zhiyun-supply-studio',
  'zhiyun-service-studio',
];

// 提取 `var mods = [ ... ];` 的数组字面量（括号配平扫描，忽略字符串与注释）。
function extractModsArray(src) {
  const start = src.indexOf('var mods = [');
  if (start === -1) throw new Error('mods array not found');
  let i = src.indexOf('[', start);
  let depth = 0, quote = null, escape = false;
  for (; i < src.length; i++) {
    const c = src[i];
    if (escape) { escape = false; continue; }
    if (quote) {
      if (c === '\\') { escape = true; continue; }
      if (c === quote) quote = null;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') { quote = c; continue; }
    if (c === '[' || c === '{') depth++;
    if (c === ']' || c === '}') { depth--; if (depth === 0) return src.slice(src.indexOf('[', start), i + 1); }
  }
  throw new Error('unbalanced mods array');
}

// 模块字面量只包含数据与函数表达式；函数体在定义时不执行，占位符即可安全求值。
const SANDBOX = {
  request: () => ({}), getJson: () => ({}), pushAgentContext: () => {},
  h: () => null, Fragment: null, antd: {}, React: { createElement: () => null },
  T: {}, message: { success: () => {}, error: () => {}, warning: () => {} },
  fmt: (v) => String(v == null ? '' : v),
};

function csvCell(value) {
  const text = value == null ? '' : String(value);
  return /[",\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
}

function rowsToCsv(columns, rows) {
  const header = columns.map((c) => csvCell(c.label)).join(',');
  const body = rows.map((row) => columns.map((c) => {
    let v = row[c.key];
    if (Array.isArray(v)) v = v.join('、');
    return csvCell(v);
  }).join(',')).join('\n');
  return header + '\n' + body + '\n';
}

function collect(columns, sampleRows) {
  const rows = (sampleRows || []).map((r) => {
    const out = {};
    columns.forEach((c) => { out[c.key] = r ? r[c.key] : undefined; });
    return out;
  });
  return rowsToCsv(columns, rows);
}

function safeName(text) {
  return String(text).replace(/[\\/:*?"<>|\s]+/g, '-').slice(0, 40);
}

function main() {
  const manifest = [];
  STUDIOS.forEach((studio) => {
    const src = fs.readFileSync(path.join(RUNTIME, studio, 'ui', 'index.js'), 'utf8');
    const mods = vm.runInNewContext('(' + extractModsArray(src) + ')', SANDBOX);
    const dir = path.join(OUT, studio);
    fs.mkdirSync(dir, { recursive: true });
    mods.forEach((mod) => {
      const base = `${mod.key}-${safeName(mod.label)}`;
      if (mod.inputKind === 'table') {
        const file = path.join(dir, base + '.csv');
        fs.writeFileSync(file, '\ufeff' + collect(mod.columns, mod.sample), 'utf8');
        manifest.push({ studio, module: mod.key, label: mod.label, kind: 'table', file, rows: (mod.sample || []).length, columns: mod.columns.length });
      } else if (mod.inputKind === 'form') {
        (mod.fields || []).filter((f) => f && f.type === 'subtable').forEach((f) => {
          const rows = (mod.sample && mod.sample[f.key]) || f.sample || [];
          const file = path.join(dir, `${base}-${safeName(f.label)}.csv`);
          fs.writeFileSync(file, '\ufeff' + collect(f.columns, rows), 'utf8');
          manifest.push({ studio, module: mod.key, label: mod.label + ' / ' + f.label, kind: 'form-subtable', file, rows: rows.length, columns: f.columns.length });
        });
        if (mod.example) {
          const file = path.join(dir, base + '.txt');
          fs.writeFileSync(file, mod.example, 'utf8');
          manifest.push({ studio, module: mod.key, label: mod.label, kind: 'form-text', file });
        }
      } else if (mod.inputKind === 'text' && mod.example) {
        const file = path.join(dir, base + '.txt');
        fs.writeFileSync(file, mod.example, 'utf8');
        manifest.push({ studio, module: mod.key, label: mod.label, kind: 'text', file });
      }
    });
  });
  fs.writeFileSync(path.join(OUT, 'manifest.json'), JSON.stringify(manifest, null, 2), 'utf8');
  console.log('generated', manifest.length, 'demo files under', OUT);
  manifest.forEach((m) => console.log(`${m.studio} ${m.module} (${m.kind}) rows=${m.rows == null ? '-' : m.rows} -> ${path.relative(ROOT, m.file)}`));
}

main();
