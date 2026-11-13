// The "Run" and "Scores" tabs of an agent: generate a test plan for a project, watch the
// agent work, score the plan against the reference, and compare scores across versions.

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Download, Gauge, LoaderCircle, Play, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { ScoreBadge, ScoreCard, pct } from "../components/ScoreCard";
import { useToast } from "../components/toast";
import { Badge, Button, EmptyState, ErrorNotice, Field, Loading, Section, Select, Table, Td, Textarea, Th, cx } from "../components/ui";
import { BASE, api, errorMessage } from "../lib/api";
import { dateTime, timeAgo } from "../lib/format";
import { keys, useAgentEvaluations, useDataset, useModels, useRun, useRunEvaluations, useRuns } from "../lib/queries";
import type { AgentDetail, Evaluation, OutputFormat, Run, RunSummary, WorkStatus } from "../lib/types";

const FORMATS: Array<{ id: OutputFormat; label: string }> = [
  { id: "docx", label: "Word" },
  { id: "xlsx", label: "Excel" },
  { id: "pdf", label: "PDF" },
  { id: "md", label: "Markdown" },
];

function seconds(ms: number | null): string {
  return ms == null ? "–" : `${Math.round(ms / 1000)} s`;
}

function StatusChip({ status }: { status: WorkStatus }) {
  if (status === "running")
    return (
      <Badge tone="signal">
        <LoaderCircle className="size-3 animate-spin" aria-hidden /> running
      </Badge>
    );
  return <Badge tone={status === "completed" ? "ok" : "bad"}>{status}</Badge>;
}

function projectOf(prompt: string): string {
  return prompt.match(/\bP\d{2}\b/i)?.[0].toUpperCase() ?? "–";
}

/* ---------------------------------------------------------------------------- start a run */

function StartRun({ agent, onStarted }: { agent: AgentDetail; onStarted: (run: Run) => void }) {
  const dataset = useDataset();
  const client = useQueryClient();
  const notify = useToast();
  const [project, setProject] = useState("");
  const [message, setMessage] = useState("");
  const [outputFormat, setOutputFormat] = useState<OutputFormat | "">("docx");
  const [model, setModel] = useState("");
  const models = useModels();
  const agentModel = agent.configuration.model ?? models.data?.default ?? "default";
  const projects = dataset.data?.projects ?? [];

  useEffect(() => {
    if (!project && projects.length) {
      const first = projects.find((item) => item.split === "validation") ?? projects[0];
      setProject(first.project);
      setMessage(first.suggestedMessage);
    }
  }, [project, projects]);

  const start = useMutation({
    mutationFn: () => api.post<Run>(`/agents/${agent.id}/runs`, { message, outputFormat: outputFormat || null, model: model || null }),
    onSuccess: async (run) => {
      client.setQueryData(keys.run(run.id), run);
      await client.invalidateQueries({ queryKey: keys.runs(agent.id) });
      onStarted(run);
    },
    onError: (error) => notify("error", errorMessage(error)),
  });

  const canRun = agent.status === "ACTIVE" && agent.publishedVersion > 0;

  function submit(event: FormEvent) {
    event.preventDefault();
    start.mutate();
  }

  return (
    <Section title="New run" description="Pick a project; the agent reads its BRD and diagram and writes the plan. Takes 1–3 minutes.">
      <form onSubmit={submit} className="space-y-4">
        {dataset.isError && <ErrorNotice error={dataset.error} title="Couldn't list the projects" />}
        {dataset.data && projects.length === 0 && (
          <p className="text-sm text-bad-600">No projects found in {dataset.data.dataDir}/raw. Copy the raw dataset there.</p>
        )}
        <Field label="Project">
          <Select
            value={project}
            onChange={(event) => {
              const chosen = projects.find((item) => item.project === event.target.value);
              setProject(event.target.value);
              if (chosen) setMessage(chosen.suggestedMessage);
            }}
          >
            {projects.map((item) => (
              <option key={item.project} value={item.project}>
                {item.project} · {item.title} ({item.split})
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Message" hint="Sent as the user message. The skill's instructions are added in front of it.">
          <Textarea rows={4} value={message} onChange={(event) => setMessage(event.target.value)} required />
        </Field>
        <Field label="Model" hint="For this run only. Compare models on the same project; the Scores tab shows each run's model.">
          <Select value={model} onChange={(event) => setModel(event.target.value)} className="font-mono">
            <option value="">Agent's model ({agentModel})</option>
            {(models.data?.models ?? [])
              .filter((name) => name !== agentModel)
              .map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
          </Select>
        </Field>
        <Field label="Save as" hint="Saved to data/agent-output/ when the run finishes. Every format can also be downloaded later.">
          <Select value={outputFormat} onChange={(event) => setOutputFormat(event.target.value as OutputFormat | "")}>
            {FORMATS.map((format) => (
              <option key={format.id} value={format.id}>
                {format.label} (.{format.id})
              </option>
            ))}
            <option value="">No file (keep in the database only)</option>
          </Select>
        </Field>
        {!canRun && <p className="text-sm text-bad-600">Publish the agent (and keep it ACTIVE) to run it.</p>}
        <Button type="submit" variant="primary" icon={<Play className="size-4" />} loading={start.isPending} disabled={!canRun || !message.trim()}>
          Run agent
        </Button>
      </form>
    </Section>
  );
}

/* ---------------------------------------------------------------------------- run history */

function RunList({ runs, selected, onSelect }: { runs: RunSummary[]; selected: string | null; onSelect: (id: string) => void }) {
  if (runs.length === 0) return <p className="text-ink-500">No runs yet.</p>;
  return (
    <ul className="-mx-5 divide-y divide-line">
      {runs.map((run) => (
        <li key={run.id}>
          <button
            type="button"
            onClick={() => onSelect(run.id)}
            aria-current={selected === run.id}
            className={cx(
              "flex w-full items-center gap-3 px-5 py-2.5 text-left hover:bg-paper",
              selected === run.id && "bg-signal-50 shadow-[inset_3px_0_0_var(--color-signal-500)]",
            )}
          >
            <span className="w-10 font-mono text-sm text-ink-900">{projectOf(run.prompt)}</span>
            <span className="flex-1 text-sm text-ink-500">
              v{run.agentVersion} · {timeAgo(run.createdAt)}
            </span>
            {run.status === "completed" ? <ScoreBadge value={run.latestOverall} /> : <StatusChip status={run.status} />}
          </button>
        </li>
      ))}
    </ul>
  );
}

/* ---------------------------------------------------------------------------- one run */

/** Built by the backend from the saved Markdown: GET /api/runs/{id}/export?format=docx */
function exportUrl(runId: string, format: OutputFormat): string {
  return `${BASE}/runs/${runId}/export?format=${format}`;
}

function ToolTrace({ run }: { run: Run }) {
  if (run.toolCalls.length === 0) return <p className="text-sm text-ink-500">{run.status === "running" ? "Waiting for the first tool call…" : "No tools were called."}</p>;
  return (
    <ol className="space-y-1.5">
      {run.toolCalls.map((call, index) => (
        <li key={index} className="flex gap-3 text-sm">
          <span className="w-14 shrink-0 font-mono text-xs leading-5 text-ink-400">round {call.round}</span>
          {call.ok ? <Check className="mt-0.5 size-4 shrink-0 text-ok-600" aria-label="ok" /> : <X className="mt-0.5 size-4 shrink-0 text-bad-600" aria-label="failed" />}
          <span className="min-w-0">
            <span className="font-mono text-ink-900">{call.name}</span>
            <span className="ml-2 font-mono text-xs break-all text-ink-500">{call.arguments}</span>
            {!call.ok && <span className="block text-xs text-bad-600">{call.result}</span>}
          </span>
        </li>
      ))}
    </ol>
  );
}

function Scoring({ run }: { run: Run }) {
  const evaluations = useRunEvaluations(run.id);
  const client = useQueryClient();
  const notify = useToast();
  const latest: Evaluation | undefined = evaluations.data?.[0];

  const score = useMutation({
    mutationFn: () => api.post<Evaluation>(`/runs/${run.id}/evaluations`, {}),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: keys.runEvaluations(run.id) });
    },
    onError: (error) => notify("error", errorMessage(error)),
  });

  // When a score finishes, refresh the history (it shows the latest score) and the Scores tab.
  const previousStatus = useRef(latest?.status);
  useEffect(() => {
    if (previousStatus.current === "running" && latest?.status === "completed") {
      void client.invalidateQueries({ queryKey: keys.runs(run.agentId) });
      void client.invalidateQueries({ queryKey: keys.agentEvaluations(run.agentId) });
    }
    previousStatus.current = latest?.status;
  }, [latest?.status, client, run.agentId]);

  const busy = score.isPending || latest?.status === "running";
  return (
    <Section
      title="Score"
      description="Compared with the project's reference test plan; every judgement is backed by a verified quote."
      actions={
        <Button size="sm" icon={<Gauge className="size-4" />} loading={busy} onClick={() => score.mutate()}>
          {latest ? "Score again" : "Score this plan"}
        </Button>
      }
    >
      {evaluations.isPending && <Loading />}
      {!latest && !evaluations.isPending && <p className="text-ink-500">Not scored yet. Scoring takes about a minute.</p>}
      {latest?.status === "running" && <Loading label="The judge is reading both plans and the BRD…" />}
      {latest?.status === "failed" && <ErrorNotice error={new Error(latest.error ?? "failed")} title="Scoring failed" />}
      {latest?.status === "completed" && <ScoreCard evaluation={latest} />}
    </Section>
  );
}

function RunView({ runId }: { runId: string }) {
  const run = useRun(runId);
  const [raw, setRaw] = useState(false);
  if (run.isPending) return <Loading label="Loading run…" />;
  if (run.isError) return <ErrorNotice error={run.error} />;
  const data = run.data;
  const project = projectOf(data.prompt);

  return (
    <div className="space-y-6">
      <Section
        title={
          <span className="flex items-center gap-3">
            {project} run <StatusChip status={data.status} />
          </span>
        }
        description={`${dateTime(data.createdAt)} · agent v${data.agentVersion} · ${data.model}`}
      >
        <dl className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-ink-500">Duration</dt>
            <dd className="font-mono">{data.status === "running" ? "…" : seconds(data.durationMs)}</dd>
          </div>
          <div>
            <dt className="text-ink-500">Tool rounds</dt>
            <dd className="font-mono">{data.toolRounds}</dd>
          </div>
          <div>
            <dt className="text-ink-500">Input tokens</dt>
            <dd className="font-mono">{data.promptTokens.toLocaleString()}</dd>
          </div>
          <div>
            <dt className="text-ink-500">Output tokens</dt>
            <dd className="font-mono">{data.completionTokens.toLocaleString()}</dd>
          </div>
        </dl>
        {data.outputFile && (
          <p className="mt-4 text-sm text-ink-700">
            Saved as <span className="font-mono text-ink-900">data/{data.outputFile}</span>
          </p>
        )}
        {data.error && <p className="mt-4 rounded border border-bad-600/25 bg-bad-50 px-3 py-2 text-sm text-bad-800">{data.error}</p>}
        <h3 className="mt-5 mb-2 text-sm font-semibold text-ink-900">What the agent did</h3>
        <ToolTrace run={data} />
      </Section>

      {data.status === "completed" && <Scoring run={data} />}

      {data.answer && (
        <Section
          title="Generated test plan"
          actions={
            <div className="flex flex-wrap justify-end gap-2">
              <Button size="sm" variant="ghost" onClick={() => setRaw(!raw)}>
                {raw ? "Formatted" : "Markdown source"}
              </Button>
              {FORMATS.map((format) => (
                <a
                  key={format.id}
                  href={exportUrl(data.id, format.id)}
                  download
                  className="inline-flex items-center gap-1.5 rounded-md border border-line-strong bg-surface px-2.5 py-1 text-sm text-ink-900 hover:border-ink-400 hover:bg-paper"
                >
                  <Download className="size-3.5" aria-hidden />
                  {format.label}
                </a>
              ))}
            </div>
          }
        >
          {raw ? (
            <pre className="max-h-[70vh] overflow-auto font-mono text-[13px] whitespace-pre-wrap text-ink-800">{data.answer}</pre>
          ) : (
            <div className="md max-w-[85ch]">
              <Markdown remarkPlugins={[remarkGfm]}>{data.answer}</Markdown>
            </div>
          )}
        </Section>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------------- tabs */

export function RunTab({ agent }: { agent: AgentDetail }) {
  const runs = useRuns(agent.id);
  const [selected, setSelected] = useState<string | null>(null);
  const current = selected ?? runs.data?.[0]?.id ?? null;

  return (
    <div className="grid gap-6 lg:grid-cols-[22rem_1fr]">
      <div className="space-y-6 lg:self-start">
        <StartRun agent={agent} onStarted={(run) => setSelected(run.id)} />
        <Section title="History" description="Newest first, with the latest score.">
          {runs.isPending ? <Loading /> : runs.isError ? <ErrorNotice error={runs.error} /> : <RunList runs={runs.data} selected={current} onSelect={setSelected} />}
        </Section>
      </div>
      <div className="min-w-0">
        {current ? (
          <RunView key={current} runId={current} />
        ) : (
          <EmptyState title="No runs yet" body="Start a run on the left. The plan, the agent's tool calls and its score appear here." />
        )}
      </div>
    </div>
  );
}

interface VersionStats {
  version: number;
  count: number;
  overall: number;
  coverage: number;
  faithfulness: number;
}

function mean(values: number[]): number {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

export function ScoresTab({ agent }: { agent: AgentDetail }) {
  const evaluations = useAgentEvaluations(agent.id);
  const completed = useMemo(() => (evaluations.data ?? []).filter((item) => item.status === "completed" && item.overall != null), [evaluations.data]);

  const byVersion: VersionStats[] = useMemo(() => {
    const groups = new Map<number, typeof completed>();
    for (const item of completed) groups.set(item.agentVersion, [...(groups.get(item.agentVersion) ?? []), item]);
    return [...groups.entries()]
      .map(([version, items]) => ({
        version,
        count: items.length,
        overall: mean(items.map((item) => item.overall ?? 0)),
        coverage: mean(items.map((item) => item.coverage ?? 0)),
        faithfulness: mean(items.map((item) => item.faithfulness ?? 0)),
      }))
      .sort((a, b) => b.version - a.version);
  }, [completed]);

  if (evaluations.isPending) return <Loading />;
  if (evaluations.isError) return <ErrorNotice error={evaluations.error} />;
  if (completed.length === 0)
    return <EmptyState title="No scores yet" body="Run the agent and score the plan on the Run tab, or run scripts/run_experiment.py for a whole split." />;

  const best = Math.max(...byVersion.map((item) => item.overall));
  return (
    <div className="space-y-6">
      <Section title="By published version" description="Each publish is a prompt version. Compare means, not single runs: the same prompt scores differently run to run.">
        <ul className="space-y-3">
          {byVersion.map((item) => (
            <li key={item.version} className="grid grid-cols-[4rem_1fr_auto] items-center gap-4">
              <span className="font-mono text-sm text-ink-900">v{item.version}</span>
              <div className="h-3 rounded-full bg-paper">
                <div
                  className={cx("h-3 rounded-full", item.overall === best ? "bg-signal-500" : "bg-ink-400")}
                  style={{ width: `${item.overall * 100}%` }}
                />
              </div>
              <span className="text-sm text-ink-500">
                <span className="font-mono text-ink-950">{pct(item.overall, 1)}</span> · coverage {pct(item.coverage)} · faithful {pct(item.faithfulness)} · n={item.count}
              </span>
            </li>
          ))}
        </ul>
      </Section>

      <Table
        head={
          <>
            <Th>When</Th>
            <Th>Project</Th>
            <Th>Version</Th>
            <Th>Model</Th>
            <Th className="text-right">Overall</Th>
            <Th className="text-right">Structure</Th>
            <Th className="text-right">Coverage</Th>
            <Th className="text-right">Similarity</Th>
            <Th className="text-right">Faithful</Th>
          </>
        }
      >
        {completed.map((item) => (
          <tr key={item.id}>
            <Td className="text-sm text-ink-500">{dateTime(item.createdAt)}</Td>
            <Td>
              <span className="font-mono">{item.project}</span> <span className="text-xs text-ink-400">{item.split}</span>
            </Td>
            <Td className="font-mono text-sm">v{item.agentVersion}</Td>
            <Td className="font-mono text-sm text-ink-500">{item.runModel}</Td>
            <Td className="text-right">
              <ScoreBadge value={item.overall} />
            </Td>
            <Td className="text-right font-mono text-sm">{pct(item.structure)}</Td>
            <Td className="text-right font-mono text-sm">{pct(item.coverage)}</Td>
            <Td className="text-right font-mono text-sm">{pct(item.similarity)}</Td>
            <Td className="text-right font-mono text-sm">{pct(item.faithfulness)}</Td>
          </tr>
        ))}
      </Table>
    </div>
  );
}
