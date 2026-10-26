// A small, lazy native-provider workflow. Credentials stay in memory and are
// submitted only through the host's authenticated, same-origin fetch API.
export function normalizeBaseUrl(value) {
  let url
  try { url = new URL(value.trim()) } catch { throw new Error('请填写完整服务地址，例如 http://127.0.0.1:8888/v1') }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error('服务地址只支持 HTTP/HTTPS，请勿在地址中包含密钥、查询参数或账号密码。')
  }
  url.pathname = url.pathname.replace(/\/(?:chat\/completions|responses|models)\/?$/, '').replace(/\/+$/, '')
  return url.toString().replace(/\/$/, '')
}

export function providerConfig({ name, url, key, protocol }, editing = false) {
  if (!name.trim()) throw new Error('请填写服务名称，便于以后查找。')
  const result = { name: name.trim(), base_url: normalizeBaseUrl(url), chat_model: protocol, auto_discover: false }
  if (!editing || key.trim()) result.api_key = key.trim()
  return result
}

export function mergeModels(provider) {
  const models = new Map()
  for (const item of [...(provider.models || []), ...(provider.extra_models || []), ...(provider.discovered_models || [])]) {
    if (item.id) models.set(item.id, { id: item.id, name: item.name || item.id })
  }
  return [...models.values()].sort((a, b) => a.id.localeCompare(b.id))
}

export function newProviderId() {
  // getRandomValues also works on ordinary LAN HTTP pages, unlike randomUUID.
  return 'aios-' + [...crypto.getRandomValues(new Uint8Array(10))].map(x => x.toString(16).padStart(2, '0')).join('')
}

export function requestMessage(status) {
  if (status === 401) return '登录已失效，请重新登录后再操作。'
  if (status === 403) return '当前账号没有此项配置权限，请联系管理员。'
  if (status === 409) return '服务记录发生冲突，请刷新列表后重试。'
  if (status === 429) return '服务请求过于频繁，请稍后重试。'
  return '请求未完成，请检查服务地址、密钥和服务运行状态，也可打开高级模型设置。'
}

export function discoveryMessage(kind) {
  return ({
    authentication: '服务拒绝了密钥，请确认密钥是否正确或已过期。',
    authorization: '此密钥没有读取模型列表的权限，可手填模型 ID。',
    timeout: '服务响应超时，请稍后重试，或手填模型 ID。',
    network: '无法连接服务，请检查地址、端口，以及本地模型服务是否启动。',
    invalid_response: '服务返回的不是有效模型列表，请确认基础地址和接口协议。',
    unsupported: '此服务不支持自动获取列表，可直接手填模型 ID。',
    configuration: '服务配置不完整，请检查地址和接口协议。',
  })[kind] || '未能获取实时模型列表。请检查连接，或直接填写模型 ID。'
}

const PRESETS = {
  compatible: { name: '', url: '', protocol: 'OpenAIChatModel' },
  ollama: { name: '本地 Ollama', url: 'http://127.0.0.1:11434/v1', protocol: 'OpenAIChatModel' },
  lmstudio: { name: '本地 LM Studio', url: 'http://127.0.0.1:1234/v1', protocol: 'OpenAIChatModel' },
}

export function createModelSetupPage(Q) {
  const R = Q.host.React, h = R.createElement
  const css = '.aios-model-setup{max-width:880px;margin:auto;padding:24px;color:var(--fg);font:inherit}.aios-model-setup *{box-sizing:border-box}.aios-model-setup h1{font-size:24px;margin:0 0 8px}.aios-model-setup h2{font-size:17px;margin:0 0 16px}.aios-model-setup p{line-height:1.7}.aios-model-setup section{border:1px solid var(--line);background:var(--bg);border-radius:14px;padding:20px;margin:18px 0}.aios-model-setup label{display:block;font-weight:600;margin:14px 0 6px}.aios-model-setup input,.aios-model-setup select{width:100%;min-height:40px;border:1px solid var(--line);border-radius:8px;padding:9px 11px;font:inherit;background:var(--bg);color:var(--fg)}.aios-model-setup select[size]{height:155px}.aios-model-setup button{border:1px solid var(--line);border-radius:8px;padding:10px 15px;font:inherit;cursor:pointer;background:var(--bg);color:var(--fg)}.aios-model-setup button:disabled{opacity:.5;cursor:wait}.aios-model-setup .primary{background:#0086ad;color:white;border-color:#0086ad}.aios-model-setup .actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}.aios-model-setup .muted{font-size:13px;color:var(--muted)}.aios-model-setup .notice{padding:12px;border-radius:8px;background:var(--notice);line-height:1.7}.aios-model-setup a{color:var(--link)}.aios-model-setup input:focus,.aios-model-setup select:focus,.aios-model-setup button:focus-visible{outline:2px solid #0086ad;outline-offset:2px}.aios-model-setup .check{display:flex;gap:8px;align-items:center}.aios-model-setup .check input{width:auto;min-height:0}@media(max-width:600px){.aios-model-setup{padding:16px}.aios-model-setup section{padding:16px}}'
  return function ModelSetup() {
    const dark = Q.host.useTheme?.() === 'dark'
    const [providers, setProviders] = R.useState([]), [selected, setSelected] = R.useState('')
    const [form, setForm] = R.useState({ ...PRESETS.compatible, key: '' })
    const [preset, setPreset] = R.useState('compatible'), [models, setModels] = R.useState([])
    const [model, setModel] = R.useState(''), [search, setSearch] = R.useState('')
    const [remotePool, setRemotePool] = R.useState(false), [poolTotal, setPoolTotal] = R.useState(0)
    const [scope, setScope] = R.useState('global'), [busy, setBusy] = R.useState(true)
    const [message, setMessage] = R.useState('正在读取已有模型服务…')
    const [loaded, setLoaded] = R.useState(false), [managed, setManaged] = R.useState(false)
    const [dirty, setDirty] = R.useState(false)
    const abort = R.useRef(null)
    const advanced = './models'

    async function api(path, method = 'GET', body, signal) {
      const response = await Q.host.fetch(path, {
        method, signal,
        headers: { 'Content-Type': 'application/json' },
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      })
      if (!response.ok) {
        const error = new Error(requestMessage(response.status)); error.status = response.status
        if (response.status === 400) {
          try { const detail = (await response.json()).detail; if (typeof detail === 'string') error.nativeDetail = detail } catch { /* Non-JSON gateway error. */ }
        }
        throw error
      }
      return response.json()
    }
    async function load(signal) {
      const list = await api('/models', 'GET', undefined, signal)
      if (!Array.isArray(list)) throw new Error('模型列表格式异常，请打开高级模型设置。')
      const isManaged = list.some(p => p.id === 'hub-managed')
      setManaged(isManaged)
      // Do not retain returned keys in component state or echo them into a field.
      // Free/OAuth providers can be active without an API key. Do not hide
      // them merely because the native vault does not expose a masked key.
      const safe = list.filter(p => p.is_custom || p.is_local || p.enabled !== false).map(p => ({
        id: p.id, name: p.name, base_url: p.base_url, chat_model: p.chat_model,
        is_custom: p.is_custom, models: mergeModels(p),
      }))
      setProviders(safe); setLoaded(true)
      return safe
    }
    R.useEffect(() => {
      const controller = new AbortController(); abort.current = controller
      load(controller.signal).then(() => setMessage('已有服务可直接编辑；添加新服务无需填写提供商 ID。'))
        .catch(error => { if (!controller.signal.aborted) setMessage(error.message) })
        .finally(() => { if (!controller.signal.aborted) setBusy(false) })
      return () => { controller.abort(); abort.current?.abort() }
    }, [])

    R.useEffect(() => {
      if (!remotePool || !selected) return
      const controller = new AbortController()
      const timer = setTimeout(() => {
        api('/models/' + encodeURIComponent(selected) + '/pool?limit=100&search=' + encodeURIComponent(search), 'GET', undefined, controller.signal)
          .then(page => { if (!controller.signal.aborted) { setModels(mergeModels(page)); setPoolTotal(page.total || 0) } })
          .catch(() => { if (!controller.signal.aborted) setMessage('已有模型列表暂时无法读取，可手填模型 ID，或重新获取列表。') })
      }, 200)
      return () => { clearTimeout(timer); controller.abort() }
    }, [selected, search, remotePool])

    function change(name, value) { setDirty(true); setForm(previous => ({ ...previous, [name]: value })) }
    function choose(id) {
      setSelected(id); setModel(''); setSearch(''); setDirty(false)
      const provider = providers.find(p => p.id === id)
      setForm(provider ? { name: provider.name, url: provider.base_url, protocol: provider.chat_model, key: '' } : { ...PRESETS.compatible, key: '' })
      setModels(provider?.models || [])
      setRemotePool(Boolean(id)); setPoolTotal(0)
      setMessage(provider ? '密钥留空将保留原密钥。仅修改本次填写的连接设置。' : '填写服务地址和密钥，即可获取模型列表。')
    }
    async function perform(action) {
      if (!loaded || managed || busy) return
      const controller = new AbortController(); abort.current = controller
      const timer = setTimeout(() => controller.abort(), 60000)
      setBusy(true)
      try { await action(controller.signal) }
      catch (error) { if (controller.signal.aborted) setMessage('请求超时或已取消。已保存的服务仍保留，可手填模型 ID 或稍后重试。'); else setMessage(error.message) }
      finally { clearTimeout(timer); if (abort.current === controller) setBusy(false) }
    }
    async function saveService(signal) {
      const config = providerConfig(form, Boolean(selected))
      if (!selected && !form.key.trim()) throw new Error('请填写此兼容服务的密钥。Ollama / LM Studio 等免密服务可在“已有服务”中直接配置。')
      const match = !selected && providers.find(p => {
        try { return normalizeBaseUrl(p.base_url) === config.base_url && p.chat_model === config.chat_model } catch { return false }
      })
      if (match) throw new Error('已有相同地址的服务，请在上方选择已有服务，避免重复添加。')
      let provider
      if (selected) {
        const body = { ...config }
        if (!providers.find(p => p.id === selected)?.is_custom) delete body.name
        provider = await api('/models/' + encodeURIComponent(selected) + '/config', 'PUT', body, signal)
      } else {
        const id = newProviderId()
        provider = await api('/models/custom-providers', 'POST', {
          id, name: config.name, default_base_url: config.base_url,
          // Creating with the key starts upstream background discovery. Store
          // the key in the subsequent explicit config call to avoid two probes.
          api_key: '', chat_model: config.chat_model, models: [],
        }, signal)
        setSelected(provider.id)
        if (config.api_key) await api('/models/' + encodeURIComponent(provider.id) + '/config', 'PUT', config, signal)
      }
      setSelected(provider.id); change('key', ''); change('url', config.base_url)
      await load(signal)
      setDirty(false)
      return provider.id
    }
    function saveAndDiscover() {
      perform(async signal => {
        setRemotePool(false)
        const id = await saveService(signal)
        setMessage('服务已保存，正在获取模型列表…')
        const result = await api('/models/' + encodeURIComponent(id) + '/discover', 'POST', {}, signal)
        if (!result.success) { setMessage('服务已保存。' + discoveryMessage(result.error_kind)); return }
        const list = mergeModels({ models: result.models })
        setModels(list); setModel(''); setSearch('')
        setMessage(result.used_static_fallback ? '服务已保存。当前显示内置候选，未确认实时服务列表；也可手填模型 ID。' : `服务已保存，获取到 ${list.length} 个模型。请选择或填写模型 ID。`)
      })
    }
    function testService() {
      perform(async signal => {
        const id = await saveService(signal)
        const result = await api('/models/' + encodeURIComponent(id) + '/test', 'POST', {}, signal)
        setMessage(result.success ? '服务连接正常。此检测不代表模型推理已经通过。' : '服务已保存，但连接检测失败，请检查地址、密钥和服务运行状态。')
      })
    }
    function activate() {
      perform(async signal => {
        if (!selected || !model.trim()) throw new Error('请先保存服务，并选择或填写模型 ID。')
        const id = model.trim()
        try { await api('/models/' + encodeURIComponent(selected) + '/models/' + encodeURIComponent(id) + '/pool', 'PUT', { selected: true }, signal) }
        catch (error) {
          // The metadata preview endpoint fabricates a preview for unknown IDs;
          // use the native pool's exact not-found response instead. Never
          // mistake permission or connectivity errors for an absent model.
          if (error.status !== 400 || error.nativeDetail !== `Model '${id}' not found`) throw error
          await api('/models/' + encodeURIComponent(selected) + '/models', 'POST', { id, name: id }, signal)
        }
        const body = { provider_id: selected, model: id, scope }
        if (scope === 'agent') body.agent_id = Q.host.getSelectedAgentId?.() || 'default'
        await api('/models/active', 'PUT', body, signal)
        setMessage(scope === 'agent' ? '已保存为当前智能体的模型。其他智能体和全局默认保持原设置。' : '已保存为全局默认模型。已有智能体单独指定的模型保持原设置。')
      })
    }
    const field = (name, label, options = {}) => h(R.Fragment, { key: name },
      h('label', { htmlFor: 'aios-model-' + name }, label),
      h('input', { id: 'aios-model-' + name, value: form[name], onChange: e => change(name, e.target.value), disabled: busy || managed, ...options }))
    const filtered = (remotePool ? models : models.filter(m => (m.id + ' ' + m.name).toLowerCase().includes(search.toLowerCase()))).slice(0, 100)
    return h('main', { className: 'aios-model-setup', style: {
      '--fg': dark ? '#ededed' : '#172b38', '--bg': dark ? '#202528' : '#fff',
      '--line': dark ? '#46515a' : '#dbe3e8', '--muted': dark ? '#b5c3cd' : '#536572',
      '--notice': dark ? '#203a45' : '#eef7fa', '--link': dark ? '#79d2ed' : '#007795',
    } }, h('style', null, css),
    h('h1', null, '快速配置模型'),
    h('p', { className: 'muted' }, '填好服务地址 → 获取模型 → 设为默认。已有服务、密钥和高级参数继续由平台原生管理。'),
    h('a', { href: advanced }, '全部供应商 / 高级模型设置'),
    h('p', { className: 'notice', role: 'status', 'aria-live': 'polite' }, managed ? '此运行环境由 Hub 集中供给模型，请在原生模型页面选择，或联系管理员配置服务。' : message),
    !managed && h(R.Fragment, null,
      h('section', { 'aria-labelledby': 'aios-service-title' },
        h('h2', { id: 'aios-service-title' }, '1. 连接模型服务'),
        h('label', { htmlFor: 'aios-existing' }, '已有服务'),
        h('select', { id: 'aios-existing', value: selected, disabled: busy || !loaded, onChange: e => choose(e.target.value) },
          h('option', { value: '' }, '添加新服务'), providers.map(p => h('option', { key: p.id, value: p.id }, p.name))),
        !selected && h(R.Fragment, null,
          h('label', { htmlFor: 'aios-preset' }, '服务类型'),
          h('select', { id: 'aios-preset', value: preset, disabled: busy, onChange: e => {
            const type = e.target.value; setPreset(type)
            const local = type !== 'compatible' && providers.find(p => p.id === type)
            if (local) choose(local.id)
            else { setDirty(true); setForm({ ...PRESETS[type], key: '' }) }
          } },
            h('option', { value: 'compatible' }, 'OpenAI 兼容 / 其他本地服务'), h('option', { value: 'ollama' }, '本地 Ollama'), h('option', { value: 'lmstudio' }, '本地 LM Studio'))),
        field('name', '服务名称', { placeholder: '例如：本机模型服务', autoComplete: 'off', readOnly: Boolean(selected && !providers.find(p => p.id === selected)?.is_custom) }),
        field('url', '服务地址', { placeholder: 'http://127.0.0.1:8888/v1', type: 'url', autoComplete: 'off' }),
        h('p', { className: 'muted' }, '可粘贴完整的 /v1/chat/completions 地址，会自动识别基础地址。不会从网址读取密钥。'),
        field('key', selected ? 'API 密钥（留空保留原密钥）' : 'API 密钥', { type: 'password', autoComplete: 'new-password', spellCheck: false }),
        h('p', { className: 'muted' }, 'Ollama / LM Studio 可直接从已有服务选择。内置服务名称保持原样；密钥不会回显。'),
        h('label', { htmlFor: 'aios-protocol' }, '接口协议'),
        h('select', { id: 'aios-protocol', value: form.protocol, disabled: busy, onChange: e => change('protocol', e.target.value) },
          h('option', { value: 'OpenAIChatModel' }, 'OpenAI 兼容（Chat Completions）'), h('option', { value: 'OpenAIResponseModel' }, 'OpenAI Responses'),
          h('option', { value: 'AnthropicChatModel' }, 'Anthropic'), h('option', { value: 'GeminiChatModel' }, 'Google Gemini'),
          form.protocol === 'DashScopeChatModel' && h('option', { value: 'DashScopeChatModel' }, '当前 DashScope 协议')),
        h('div', { className: 'actions' }, h('button', { className: 'primary', disabled: busy || !loaded, onClick: saveAndDiscover }, busy ? '正在处理…' : '保存并获取模型'), h('button', { disabled: busy || !loaded, onClick: testService }, '保存并检测连接'))),
      h('section', { 'aria-labelledby': 'aios-model-title' },
        h('h2', { id: 'aios-model-title' }, '2. 选择模型并开始使用'),
        (remotePool || models.length > 0) && h(R.Fragment, null,
          h('label', { htmlFor: 'aios-search' }, '搜索模型'),
          h('input', { id: 'aios-search', value: search, disabled: busy, placeholder: '输入模型名的一部分', onChange: e => setSearch(e.target.value) }),
          h('label', { htmlFor: 'aios-model-list' }, '模型列表'),
          h('select', { id: 'aios-model-list', size: 5, value: filtered.some(m => m.id === model) ? model : '', disabled: busy, onChange: e => setModel(e.target.value) },
            h('option', { value: '', disabled: true }, '请选择模型，或在下方手填 ID'), filtered.map(m => h('option', { key: m.id, value: m.id }, m.id))),
          h('p', { className: 'muted' }, `共 ${remotePool ? poolTotal : models.length} 个匹配模型，最多显示 100 项；可搜索缩小范围。`)),
        h('label', { htmlFor: 'aios-model-id' }, '模型 ID（也可直接填写）'),
        h('input', { id: 'aios-model-id', value: model, disabled: busy, autoComplete: 'off', placeholder: '填写服务端实际提供的模型 ID', onChange: e => setModel(e.target.value) }),
        h('label', { htmlFor: 'aios-scope' }, '应用范围'),
        h('select', { id: 'aios-scope', value: scope, disabled: busy, onChange: e => setScope(e.target.value) }, h('option', { value: 'global' }, '全局默认模型'), h('option', { value: 'agent' }, '仅当前智能体')),
        h('p', { className: 'muted' }, '不会修改其他智能体已单独指定的模型。应用后平台可能自动探测模型能力，产生少量服务请求；保存成功不代表推理已经通过。'),
        h('div', { className: 'actions' }, h('button', { className: 'primary', disabled: busy || dirty || !selected || !model.trim(), onClick: activate }, '保存并应用模型')))))
  }
}
