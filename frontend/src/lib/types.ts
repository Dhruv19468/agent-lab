// Shapes of the backend's JSON (camelCase, as FastAPI returns it). Mirrors the Pydantic schemas.

export type AgentStatus = "DRAFT" | "ACTIVE" | "INACTIVE" | "ARCHIVED";
export type ToolType = "builtin" | "http";
export type ToolSource = "manual" | "skill";

export interface Health {
  status: string;
  database: "ok" | "unreachable" | string;
}

export interface Tool {
  id: string;
  name: string;
  description: string;
  toolType: ToolType;
  parameters: Record<string, unknown>;
  config: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface ToolInput {
  name: string;
  description: string;
  toolType: ToolType;
  parameters: Record<string, unknown>;
  config: Record<string, unknown>;
}

export interface Skill {
  id: string;
  name: string;
  description: string | null;
  instructions: string;
  triggerPhrases: string[];
  requiredToolIds: string[];
  createdAt: string;
  updatedAt: string;
}

export interface SkillInput {
  name: string;
  description: string | null;
  instructions: string;
  triggerPhrases: string[];
  requiredToolIds: string[];
}

export interface AgentConfiguration {
  model: string | null;
  temperature: number | null;
  maxTokens: number | null;
  maxToolRounds: number;
}

export interface Agent {
  id: string;
  name: string;
  description: string | null;
  owner: string | null;
  status: AgentStatus;
  publishedVersion: number;
  publishedAt: string | null;
  /** Set once the agent has been published to Azure AI Foundry. */
  foundryAgentName: string | null;
  foundryAgentVersion: string | null;
  foundryPublishedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface AgentSkill {
  id: string;
  name: string;
  description: string | null;
  triggerPhrases: string[];
}

export interface AgentTool {
  id: string;
  name: string;
  description: string;
  source: ToolSource;
}

export interface AgentDetail extends Agent {
  configuration: AgentConfiguration;
  skills: AgentSkill[];
  tools: AgentTool[];
  publishedInstructions: string | null;
  /** Only in the answer to a publish, e.g. "o4-mini does not accept a temperature…" */
  publishWarnings?: string[];
}

export interface ModelList {
  /** AZURE_OPENAI_DEPLOYMENT: used when an agent has no model chosen */
  default: string | null;
  models: string[];
  foundryEnabled: boolean;
  foundryError: string | null;
}

export interface AgentCreateInput {
  name: string;
  description: string | null;
  owner: string | null;
  configuration?: Partial<AgentConfiguration>;
}

export interface AgentUpdateInput {
  name?: string;
  description?: string | null;
  owner?: string | null;
  status?: AgentStatus;
}

export interface PromptPreview {
  matchedSkills: string[];
  systemMessage: string;
  userMessage: string;
  tools: string[];
}

/* ---------------------------------------------------------------- datasets, runs, evaluations */

export interface Project {
  project: string;
  split: "train" | "validation" | "test" | string;
  title: string;
  folder: string;
  brd: string | null;
  diagrams: string[];
  hasReference: boolean;
  hasGold: boolean;
  suggestedMessage: string;
}

export interface Dataset {
  dataDir: string;
  projects: Project[];
}

export type WorkStatus = "running" | "completed" | "failed";

/** File formats a plan can be saved or downloaded in (the backend converts the Markdown). */
export type OutputFormat = "docx" | "xlsx" | "pdf" | "md";

export interface ToolCallLog {
  round: number;
  name: string;
  arguments: string;
  ok: boolean;
  result: string;
  durationMs: number;
}

export interface RunSummary {
  id: string;
  agentId: string;
  agentVersion: number;
  model: string;
  status: WorkStatus;
  prompt: string;
  error: string | null;
  toolRounds: number;
  promptTokens: number;
  completionTokens: number;
  durationMs: number | null;
  outputFormat: OutputFormat | null;
  outputFile: string | null;
  createdAt: string;
  finishedAt: string | null;
  latestOverall: number | null;
}

export interface Run extends RunSummary {
  answer: string | null;
  matchedSkills: string[];
  toolCalls: ToolCallLog[];
}

export interface SectionScore {
  key: string;
  title: string;
  required: boolean;
  inPlan: boolean;
  inReference: boolean;
  similarity: number | null;
  covered: number | null;
  points: number | null;
}

export interface CoveragePoint {
  section: string;
  point: string;
  quote: string;
  covered: boolean;
  candidateQuote: string;
  note: string;
}

export interface Claim {
  claim: string;
  planQuote: string;
  support: "brd" | "diagram" | "none";
  brdQuote: string;
  note: string;
}

export interface EvaluationDetails {
  weights?: { structure: number; coverage: number; similarity: number };
  sections?: SectionScore[];
  missingRequired?: string[];
  points?: CoveragePoint[];
  claims?: Claim[];
  counts?: { points: number; covered: number; claims: number; supported: number };
}

export interface EvaluationSummary {
  id: string;
  runId: string;
  project: string;
  split: string | null;
  referenceSource: "gold" | "testplan" | null;
  judgeModel: string;
  status: WorkStatus;
  structure: number | null;
  coverage: number | null;
  similarity: number | null;
  faithfulness: number | null;
  overall: number | null;
  error: string | null;
  promptTokens: number;
  completionTokens: number;
  durationMs: number | null;
  createdAt: string;
  finishedAt: string | null;
}

export interface Evaluation extends EvaluationSummary {
  details: EvaluationDetails;
}

export interface EvaluationRow extends EvaluationSummary {
  agentVersion: number;
  runModel: string;
}
