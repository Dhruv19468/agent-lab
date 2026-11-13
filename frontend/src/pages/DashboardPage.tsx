import { Check } from "lucide-react";
import { Link } from "react-router";

import { Loading, PageHeader, StatusBadge, cx } from "../components/ui";
import { timeAgo } from "../lib/format";
import { useAgents, useHealth, useSkills, useTools } from "../lib/queries";

function Figure({ label, value, to }: { label: string; value: number | string; to: string }) {
  return (
    <Link to={to} className="group bg-surface px-5 py-4 hover:bg-paper">
      <p className="text-sm text-ink-500">{label}</p>
      <p className="mt-1 text-3xl font-semibold tracking-[-0.02em] text-ink-950 tabular-nums group-hover:text-ink-800">{value}</p>
    </Link>
  );
}

export function DashboardPage() {
  const agents = useAgents();
  const skills = useSkills();
  const tools = useTools();
  const health = useHealth();

  const agentList = agents.data ?? [];
  const active = agentList.filter((agent) => agent.status === "ACTIVE").length;
  const toolCount = tools.data?.length ?? 0;
  const skillCount = skills.data?.length ?? 0;
  const skillsWithTools = (skills.data ?? []).filter((skill) => skill.requiredToolIds.length > 0).length;
  const published = agentList.some((agent) => agent.publishedVersion > 0);

  // A real sequence: each step needs the one before it.
  const steps = [
    { done: toolCount > 0, title: "Register a tool", body: "A function the model may call, described by a JSON Schema.", to: "/tools/new" },
    { done: skillCount > 0, title: "Write a skill", body: "The procedure in Markdown, its trigger phrases and the tools it calls.", to: "/skills/new" },
    { done: agentList.length > 0, title: "Create an agent", body: "Name it and choose its model settings.", to: "/agents" },
    { done: published, title: "Attach the skill and publish", body: "Publishing builds the skill index the model receives on every run.", to: "/agents" },
  ];
  const nextStep = steps.findIndex((step) => !step.done);
  const recent = [...agentList].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)).slice(0, 5);

  return (
    <>
      <PageHeader
        title="Overview"
        description="Build agents from skills and tools, publish them, and check exactly what they will send to the model."
      />

      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-4">
        <Figure label="Agents" value={agents.isPending ? "…" : agentList.length} to="/agents" />
        <Figure label="Active" value={agents.isPending ? "…" : active} to="/agents" />
        <Figure label="Skills" value={skills.isPending ? "…" : skillCount} to="/skills" />
        <Figure label="Tools" value={tools.isPending ? "…" : toolCount} to="/tools" />
      </div>

      <div className="mt-10 grid gap-10 lg:grid-cols-5">
        <section className="lg:col-span-3">
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-lg font-semibold text-ink-950">Recently changed agents</h2>
            <Link to="/agents" className="text-sm text-ink-500 hover:text-ink-900">
              All agents
            </Link>
          </div>
          {agents.isPending ? (
            <Loading />
          ) : recent.length === 0 ? (
            <p className="rounded-lg border border-dashed border-line-strong bg-surface px-5 py-8 text-ink-500">
              No agents yet. Follow the steps on the right to build the first one.
            </p>
          ) : (
            <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
              {recent.map((agent) => (
                <li key={agent.id}>
                  <Link to={`/agents/${agent.id}`} className="flex items-center justify-between gap-4 px-5 py-3.5 hover:bg-paper">
                    <div className="min-w-0">
                      <p className="truncate font-medium text-ink-950">{agent.name}</p>
                      <p className="truncate text-sm text-ink-500">
                        {agent.publishedVersion > 0 ? `Version ${agent.publishedVersion}` : "Not published"}, changed {timeAgo(agent.updatedAt)}
                      </p>
                    </div>
                    <StatusBadge status={agent.status} />
                  </Link>
                </li>
              ))}
            </ul>
          )}

          <div className="mt-6 text-sm text-ink-500">
            Backend:{" "}
            {health.isPending ? "checking…" : health.isSuccess ? (health.data.database === "ok" ? "running, database connected" : "running, database unreachable") : "not reachable on port 8080"}
            . Skills with required tools: {skillsWithTools} of {skillCount}.
          </div>
        </section>

        <section className="lg:col-span-2">
          <h2 className="mb-3 text-lg font-semibold text-ink-950">Build your first agent</h2>
          <ol className="space-y-1">
            {steps.map((step, index) => (
              <li key={step.title}>
                <Link
                  to={step.to}
                  className={cx(
                    "flex gap-3 rounded-md px-3 py-3 hover:bg-surface",
                    index === nextStep && "bg-surface ring-1 ring-signal-500/50",
                  )}
                >
                  <span
                    className={cx(
                      "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
                      step.done ? "bg-ok-600 text-white" : index === nextStep ? "bg-signal-500 text-ink-950" : "bg-line text-ink-500",
                    )}
                  >
                    {step.done ? <Check className="size-3.5" aria-label="Done" /> : index + 1}
                  </span>
                  <span>
                    <span className={cx("block font-medium", step.done ? "text-ink-500" : "text-ink-950")}>{step.title}</span>
                    <span className="block text-sm text-ink-500">{step.body}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </>
  );
}
