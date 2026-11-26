export interface CreatedRecordCard {
  callId: string;
  title: string;
  name: string;
  id: number;
  replayed: boolean;
  route: string;
  fields: Array<{ label: string; value: string }>;
}

const resources: Record<string, {
  tool: string; title: string; route: string; fields: Array<[string, string]>;
}> = {
  profiles: { tool: 'create_admin_profile', title: 'Admin Profile', route: '/admin-profiles', fields: [['access_level', 'Access']] },
  users: { tool: 'create_admin_user', title: 'Admin User', route: '/admin-users', fields: [['email', 'Email'], ['profile_name', 'Profile']] },
  instances: { tool: 'create_instance', title: 'Instance', route: '/instances', fields: [['environment', 'Environment'], ['status', 'Status']] },
  adapters: { tool: 'create_adapter', title: 'Adapter', route: '/adapters', fields: [['adapter_type', 'Type'], ['instance_name', 'Instance'], ['endpoint', 'Endpoint']] },
};

export function createdRecordCard(callId: string, tool: string, result?: Record<string, unknown>): CreatedRecordCard | null {
  const created = result?.['created_record'] as { resource?: string; record?: Record<string, unknown> } | undefined;
  if (!created?.resource || !created.record) return null;
  const config = resources[created.resource];
  const record = created.record;
  if (!config || config.tool !== tool || !Number.isSafeInteger(record['id']) || Number(record['id']) <= 0) return null;
  const name = record['name'] ?? record['username'];
  if (typeof name !== 'string') return null;
  return {
    callId, title: config.title, name, id: Number(record['id']), route: config.route,
    replayed: result?.['operation_replayed'] === true,
    fields: config.fields.flatMap(([key, label]) => typeof record[key] === 'string' ? [{ label, value: record[key] as string }] : []),
  };
}
