// React Query hooks: each one fetches a piece of backend data and caches it under a key.
// After a change (create, attach, publish…) pages call invalidate(...) so the data refetches.

import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./api";
import type { Agent, AgentDetail, Dataset, Evaluation, EvaluationRow, Health, ModelList, Run, RunSummary, Skill, Tool } from "./types";

export const keys = {
  health: ["health"] as const,
  agents: ["agents"] as const,
  agent: (id: string) => ["agents", id] as const,
  skills: ["skills"] as const,
  skill: (id: string) => ["skills", id] as const,
  tools: ["tools"] as const,
  tool: (id: string) => ["tools", id] as const,
  datasets: ["datasets"] as const,
  models: ["models"] as const,
  runs: (agentId: string) => ["runs", "agent", agentId] as const,
  run: (id: string) => ["runs", id] as const,
  runEvaluations: (runId: string) => ["evaluations", "run", runId] as const,
  agentEvaluations: (agentId: string) => ["evaluations", "agent", agentId] as const,
};

const POLL_MS = 4_000;

export function useHealth() {
  return useQuery({
    queryKey: keys.health,
    queryFn: () => api.get<Health>("/health"),
    refetchInterval: 15_000,
    retry: false,
  });
}

export function useAgents() {
  return useQuery({ queryKey: keys.agents, queryFn: () => api.get<Agent[]>("/agents") });
}

export function useAgent(id: string) {
  return useQuery({ queryKey: keys.agent(id), queryFn: () => api.get<AgentDetail>(`/agents/${id}`) });
}

export function useSkills() {
  return useQuery({ queryKey: keys.skills, queryFn: () => api.get<Skill[]>("/skills") });
}

export function useSkill(id: string | undefined) {
  return useQuery({
    queryKey: keys.skill(id ?? "new"),
    queryFn: () => api.get<Skill>(`/skills/${id}`),
    enabled: Boolean(id),
  });
}

export function useTools() {
  return useQuery({ queryKey: keys.tools, queryFn: () => api.get<Tool[]>("/tools") });
}

export function useTool(id: string | undefined) {
  return useQuery({
    queryKey: keys.tool(id ?? "new"),
    queryFn: () => api.get<Tool>(`/tools/${id}`),
    enabled: Boolean(id),
  });
}

/** Model deployments for the dropdowns: Foundry's list (when configured) plus .env. */
export function useModels() {
  return useQuery({ queryKey: keys.models, queryFn: () => api.get<ModelList>("/models"), staleTime: 5 * 60_000 });
}

export function useDataset() {
  return useQuery({ queryKey: keys.datasets, queryFn: () => api.get<Dataset>("/datasets"), staleTime: 60_000 });
}

/** The agent's run history. Polls while any run is still going. */
export function useRuns(agentId: string) {
  return useQuery({
    queryKey: keys.runs(agentId),
    queryFn: () => api.get<RunSummary[]>(`/agents/${agentId}/runs`),
    refetchInterval: (query) => (query.state.data?.some((run) => run.status === "running") ? POLL_MS : false),
  });
}

/** One run with its answer and tool trace. Polls until it finishes. */
export function useRun(id: string | null) {
  return useQuery({
    queryKey: keys.run(id ?? "none"),
    queryFn: () => api.get<Run>(`/runs/${id}`),
    enabled: Boolean(id),
    refetchInterval: (query) => (query.state.data?.status === "running" ? POLL_MS : false),
  });
}

export function useRunEvaluations(runId: string | null) {
  return useQuery({
    queryKey: keys.runEvaluations(runId ?? "none"),
    queryFn: () => api.get<Evaluation[]>(`/runs/${runId}/evaluations`),
    enabled: Boolean(runId),
    refetchInterval: (query) => (query.state.data?.some((item) => item.status === "running") ? POLL_MS : false),
  });
}

export function useAgentEvaluations(agentId: string) {
  return useQuery({
    queryKey: keys.agentEvaluations(agentId),
    queryFn: () => api.get<EvaluationRow[]>(`/agents/${agentId}/evaluations`),
  });
}

/** Refetch everything under the given top-level keys, e.g. invalidate("agents", "tools"). */
export function useInvalidate() {
  const client = useQueryClient();
  return (...roots: Array<"agents" | "skills" | "tools" | "health" | "runs" | "evaluations">) =>
    Promise.all(roots.map((root) => client.invalidateQueries({ queryKey: [root] })));
}
