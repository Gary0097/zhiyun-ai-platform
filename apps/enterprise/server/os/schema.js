// Additive, idempotent AI-OS schema. Existing V2 tables remain authoritative during migration.
export const OS_SCHEMA = `
CREATE TABLE IF NOT EXISTS runtime_task (
  task_id TEXT PRIMARY KEY,
  tenant_id INTEGER NOT NULL REFERENCES business_tenant(id),
  title TEXT NOT NULL,
  objective TEXT NOT NULL,
  created_by INTEGER,
  owner_id INTEGER,
  source_type TEXT,
  source_id TEXT,
  priority TEXT NOT NULL DEFAULT 'normal',
  risk_level TEXT NOT NULL DEFAULT 'low',
  status TEXT NOT NULL DEFAULT 'draft',
  plan_version INTEGER NOT NULL DEFAULT 0,
  context_snapshot_id TEXT,
  current_step TEXT,
  progress REAL NOT NULL DEFAULT 0,
  approval_status TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  data_origin TEXT NOT NULL DEFAULT 'real'
);

CREATE TABLE IF NOT EXISTS runtime_task_plan (
  plan_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  tenant_id INTEGER NOT NULL REFERENCES business_tenant(id),
  version INTEGER NOT NULL,
  plan_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(task_id, version),
  FOREIGN KEY(task_id) REFERENCES runtime_task(task_id)
);

CREATE TABLE IF NOT EXISTS runtime_context_snapshot (
  snapshot_id TEXT PRIMARY KEY,
  tenant_id INTEGER NOT NULL REFERENCES business_tenant(id),
  task_id TEXT,
  context_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(task_id) REFERENCES runtime_task(task_id)
);

CREATE TABLE IF NOT EXISTS runtime_execution (
  execution_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  tenant_id INTEGER NOT NULL REFERENCES business_tenant(id),
  runner TEXT NOT NULL,
  trigger_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  trace_id TEXT,
  context_snapshot_id TEXT,
  input_json TEXT,
  output_json TEXT,
  error_code TEXT,
  error_message TEXT,
  retry_count INTEGER NOT NULL DEFAULT 0,
  started_at TEXT,
  finished_at TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(task_id) REFERENCES runtime_task(task_id)
);

CREATE TABLE IF NOT EXISTS runtime_process (
  process_id TEXT PRIMARY KEY,
  tenant_id INTEGER NOT NULL REFERENCES business_tenant(id),
  task_id TEXT NOT NULL,
  execution_id TEXT NOT NULL,
  agent_id INTEGER,
  agent_version INTEGER,
  status TEXT NOT NULL DEFAULT 'spawned',
  current_step TEXT,
  model TEXT,
  token_input INTEGER NOT NULL DEFAULT 0,
  token_output INTEGER NOT NULL DEFAULT 0,
  tool_call_count INTEGER NOT NULL DEFAULT 0,
  heartbeat_at TEXT,
  started_at TEXT,
  finished_at TEXT,
  FOREIGN KEY(task_id) REFERENCES runtime_task(task_id),
  FOREIGN KEY(execution_id) REFERENCES runtime_execution(execution_id)
);

CREATE TABLE IF NOT EXISTS runtime_checkpoint (
  checkpoint_id TEXT PRIMARY KEY,
  tenant_id INTEGER NOT NULL REFERENCES business_tenant(id),
  task_id TEXT NOT NULL,
  execution_id TEXT NOT NULL,
  process_id TEXT,
  step_key TEXT NOT NULL,
  state_json TEXT NOT NULL,
  safe_to_resume INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  FOREIGN KEY(task_id) REFERENCES runtime_task(task_id),
  FOREIGN KEY(execution_id) REFERENCES runtime_execution(execution_id)
);

CREATE TABLE IF NOT EXISTS runtime_event (
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  tenant_id INTEGER NOT NULL REFERENCES business_tenant(id),
  task_id TEXT,
  execution_id TEXT,
  process_id TEXT,
  trace_id TEXT,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime_approval (
  approval_id TEXT PRIMARY KEY,
  tenant_id INTEGER NOT NULL REFERENCES business_tenant(id),
  task_id TEXT NOT NULL,
  execution_id TEXT,
  action_type TEXT NOT NULL,
  action_json TEXT NOT NULL,
  risk_level TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  requested_by TEXT,
  decided_by INTEGER,
  decision_reason TEXT,
  expires_at TEXT,
  created_at TEXT NOT NULL,
  decided_at TEXT
);

CREATE TABLE IF NOT EXISTS runtime_artifact (
  artifact_id TEXT PRIMARY KEY,
  tenant_id INTEGER NOT NULL REFERENCES business_tenant(id),
  task_id TEXT NOT NULL,
  execution_id TEXT,
  artifact_type TEXT NOT NULL,
  name TEXT NOT NULL,
  uri TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'draft',
  source_json TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS capability_registry (
  capability_id TEXT PRIMARY KEY,
  tenant_id INTEGER REFERENCES business_tenant(id),
  capability_type TEXT NOT NULL,
  name TEXT NOT NULL,
  version TEXT NOT NULL,
  input_schema TEXT NOT NULL DEFAULT '{}',
  output_schema TEXT NOT NULL DEFAULT '{}',
  risk_level TEXT NOT NULL DEFAULT 'low',
  approval_required INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'active',
  config_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, capability_type, name, version)
);

CREATE TABLE IF NOT EXISTS capability_policy (
  policy_id TEXT PRIMARY KEY,
  tenant_id INTEGER NOT NULL REFERENCES business_tenant(id),
  capability_id TEXT NOT NULL,
  subject_type TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  effect TEXT NOT NULL,
  data_scope TEXT,
  approval_required INTEGER,
  expires_at TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(capability_id) REFERENCES capability_registry(capability_id)
);

CREATE INDEX IF NOT EXISTS idx_os_task_tenant_status ON runtime_task(tenant_id, status, updated_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_os_task_source ON runtime_task(tenant_id, source_type, source_id) WHERE source_type IS NOT NULL AND source_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_os_execution_task ON runtime_execution(tenant_id, task_id, created_at);
CREATE INDEX IF NOT EXISTS idx_os_process_state ON runtime_process(tenant_id, status, heartbeat_at);
CREATE INDEX IF NOT EXISTS idx_os_event_trace ON runtime_event(tenant_id, trace_id, created_at);
CREATE INDEX IF NOT EXISTS idx_os_approval_state ON runtime_approval(tenant_id, status, created_at);
`

export function ensureOsSchema (database) {
  database.exec(OS_SCHEMA)
  return database
}
