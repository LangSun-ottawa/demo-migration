import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const brokerBase = process.env.TOOL_BROKER_BASE_URL || "";
const runId = process.env.AGENT_RUN_ID || "";
const executionToken = process.env.AGENT_EXECUTION_TOKEN || "";

async function invoke(name: string, args: Record<string, unknown>) {
  if (!brokerBase || !runId || !executionToken) throw new Error("Tool broker context is missing");
  const response = await fetch(
    `${brokerBase}/internal/agent-runs/${encodeURIComponent(runId)}/tools/${encodeURIComponent(name)}`,
    {
      method: "POST",
      headers: { "Authorization": `Bearer ${executionToken}`, "Content-Type": "application/json" },
      body: JSON.stringify({ args }),
    },
  );
  const payload = await response.json();
  if (!response.ok) throw new Error(payload?.detail || "Tool Broker rejected the request");
  return {
    content: [{ type: "text" as const, text: JSON.stringify(payload) }],
    details: { broker: payload },
  };
}

export default function businessTools(pi: ExtensionAPI) {
  pi.registerTool({
    name: "ask_user_question", label: "Ask the user",
    description: "Ask for missing required information or an ambiguous choice, then end this turn and wait for the user's reply. This does not call Django or change business data.",
    parameters: Type.Object({
      question: Type.String({ minLength: 1, maxLength: 800 }),
      missing_fields: Type.Array(Type.String({ minLength: 1 }), { maxItems: 10 }),
    }, { additionalProperties: false }),
    execute: async (_id, params) => ({
      content: [{ type: "text" as const, text: params.question }],
      details: { clarification: params },
      terminate: true,
    }),
  });
  pi.registerTool({
    name: "query_setup_state", label: "Query setup state",
    description: "Load existing Admin Profiles, Admin Users, Instances and Adapters before choosing related IDs.",
    parameters: Type.Object({}, { additionalProperties: false }),
    execute: async () => invoke("query_setup_state", {}),
  });
  pi.registerTool({
    name: "create_admin_profile", label: "Create Admin Profile",
    description: "Create a reusable Django admin permission profile.",
    parameters: Type.Object({
      name: Type.String({ minLength: 1, maxLength: 80 }),
      access_level: Type.Union([Type.Literal("readonly"), Type.Literal("readwrite")]),
    }, { additionalProperties: false }),
    execute: async (_id, params) => invoke("create_admin_profile", params),
  });
  pi.registerTool({
    name: "create_admin_user", label: "Create Admin User",
    description: "Create a demo admin user assigned to an existing profile_id. Query setup state first.",
    parameters: Type.Object({
      username: Type.String({ minLength: 1, maxLength: 80 }),
      email: Type.String({ minLength: 3, maxLength: 254 }),
      profile_id: Type.Number({ minimum: 1 }),
    }, { additionalProperties: false }),
    execute: async (_id, params) => invoke("create_admin_user", params),
  });
  pi.registerTool({
    name: "create_instance", label: "Create Instance",
    description: "Create a managed demo system instance.",
    parameters: Type.Object({
      name: Type.String({ minLength: 1, maxLength: 80 }),
      environment: Type.Union([Type.Literal("dev"), Type.Literal("test"), Type.Literal("prod")]),
    }, { additionalProperties: false }),
    execute: async (_id, params) => invoke("create_instance", params),
  });
  pi.registerTool({
    name: "create_adapter", label: "Create Adapter",
    description: "Save an adapter configuration for an existing instance_id. Query setup state first. No real connection is attempted.",
    parameters: Type.Object({
      name: Type.String({ minLength: 1, maxLength: 80 }),
      adapter_type: Type.Union([Type.Literal("rest"), Type.Literal("syslog"), Type.Literal("custom")]),
      endpoint: Type.String({ minLength: 1, maxLength: 200 }),
      instance_id: Type.Number({ minimum: 1 }),
    }, { additionalProperties: false }),
    execute: async (_id, params) => invoke("create_adapter", params),
  });
}
