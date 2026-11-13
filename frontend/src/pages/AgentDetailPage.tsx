import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, Eye, Pencil, Rocket, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { useToast } from "../components/toast";
import {
  Badge,
  Button,
  Chip,
  ConfirmDialog,
  EmptyState,
  ErrorNotice,
  Field,
  Input,
  Loading,
  Modal,
  PageHeader,
  Section,
  Select,
  StatusBadge,
  Tabs,
  Textarea,
  cx,
} from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { dateTime } from "../lib/format";
import { keys, useAgent, useInvalidate, useModels, useSkills, useTools } from "../lib/queries";
import { RunTab, ScoresTab } from "./AgentRunsTabs";
import type { AgentConfiguration, AgentDetail, AgentStatus, AgentUpdateInput, PromptPreview } from "../lib/types";

type TabId = "setup" | "run" | "scores" | "preview" | "instructions";

/** Runs a change against the agent, puts the returned agent in the cache and shows a toast. */
function useAgentChange(agentId: string) {
  const client = useQueryClient();
  const invalidate = useInvalidate();
  const notify = useToast();
  return useMutation({
    mutationFn: (change: { run: () => Promise<AgentDetail>; done: string | ((agent: AgentDetail) => string) }) => change.run(),
    onSuccess: async (agent, change) => {
      client.setQueryData(keys.agent(agentId), agent);
      await invalidate("agents");
      notify("success", typeof change.done === "function" ? change.done(agent) : change.done);
      for (const warning of agent.publishWarnings ?? []) notify("error", warning);
    },
    onError: (error) => notify("error", errorMessage(error)),
  });
}

/* ---------------------------------------------------------------------------- skills */

function SkillsSection({ agent }: { agent: AgentDetail }) {
  const skills = useSkills();
  const change = useAgentChange(agent.id);
  const [selected, setSelected] = useState("");
  const attachedIds = new Set(agent.skills.map((skill) => skill.id));
  const available = (skills.data ?? []).filter((skill) => !attachedIds.has(skill.id));

  function attach() {
    const skill = available.find((item) => item.id === selected);
    if (!skill) return;
    change.mutate(
      {
        run: () => api.post<AgentDetail>(`/agents/${agent.id}/skills`, { skillId: skill.id }),
        done: `Attached ${skill.name}${skill.requiredToolIds.length ? " and its tools" : ""}. Publish to apply.`,
      },
      { onSuccess: () => setSelected("") },
    );
  }

  return (
    <Section
      title="Skills"
      description="The agent's behaviour comes only from its skills. A skill's required tools are attached with it."
    >
      {agent.skills.length === 0 ? (
        <p className="mb-4 text-ink-500">No skills yet. An agent needs at least one before it can be published.</p>
      ) : (
        <ul className="mb-4 divide-y divide-line">
          {agent.skills.map((skill) => (
            <li key={skill.id} className="flex items-start justify-between gap-4 py-3 first:pt-0">
              <div className="min-w-0">
                <Link to={`/skills/${skill.id}`} className="font-medium text-ink-950 underline-offset-2 hover:underline">
                  {skill.name}
                </Link>
                {skill.description && <p className="text-sm text-ink-500">{skill.description}</p>}
                {skill.triggerPhrases.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {skill.triggerPhrases.map((phrase) => (
                      <Chip key={phrase}>{phrase}</Chip>
                    ))}
                  </div>
                )}
              </div>
              <Button
                variant="ghost"
                size="sm"
                icon={<X className="size-4" />}
                disabled={change.isPending}
                onClick={() =>
                  change.mutate({
                    run: () => api.delete<AgentDetail>(`/agents/${agent.id}/skills/${skill.id}`),
                    done: `Detached ${skill.name}. Tools that only it needed were removed.`,
                  })
                }
              >
                Detach
              </Button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-col gap-2 sm:flex-row">
        <Select value={selected} onChange={(event) => setSelected(event.target.value)} aria-label="Skill to attach" disabled={available.length === 0}>
          <option value="">{available.length === 0 ? "No other skills to attach" : "Choose a skill to attach…"}</option>
          {available.map((skill) => (
            <option key={skill.id} value={skill.id}>
              {skill.name}
            </option>
          ))}
        </Select>
        <Button onClick={attach} disabled={!selected} loading={change.isPending} className="sm:w-36">
          Attach skill
        </Button>
      </div>
    </Section>
  );
}

/* ---------------------------------------------------------------------------- tools */

function ToolsSection({ agent }: { agent: AgentDetail }) {
  const tools = useTools();
  const change = useAgentChange(agent.id);
  const [selected, setSelected] = useState("");
  const attachedIds = new Set(agent.tools.map((tool) => tool.id));
  const available = (tools.data ?? []).filter((tool) => !attachedIds.has(tool.id));

  return (
    <Section title="Tools" description="Functions the model may call during a run. Tools a skill needs can't be detached by hand.">
      {agent.tools.length === 0 ? (
        <p className="mb-4 text-ink-500">No tools. The agent will answer from its instructions alone.</p>
      ) : (
        <ul className="mb-4 divide-y divide-line">
          {agent.tools.map((tool) => (
            <li key={tool.id} className="flex items-start justify-between gap-4 py-3 first:pt-0">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <Link to={`/tools/${tool.id}`} className="font-mono text-[14px] font-medium text-ink-950 underline-offset-2 hover:underline">
                    {tool.name}
                  </Link>
                  <Badge tone={tool.source === "skill" ? "signal" : "neutral"}>{tool.source === "skill" ? "From a skill" : "Added by hand"}</Badge>
                </div>
                <p className="mt-0.5 text-sm text-ink-500">{tool.description}</p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                icon={<X className="size-4" />}
                disabled={change.isPending}
                onClick={() =>
                  change.mutate({
                    run: () => api.delete<AgentDetail>(`/agents/${agent.id}/tools/${tool.id}`),
                    done: `Detached ${tool.name}.`,
                  })
                }
              >
                Detach
              </Button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-col gap-2 sm:flex-row">
        <Select value={selected} onChange={(event) => setSelected(event.target.value)} aria-label="Tool to attach" disabled={available.length === 0}>
          <option value="">{available.length === 0 ? "No other tools to attach" : "Choose a tool to attach…"}</option>
          {available.map((tool) => (
            <option key={tool.id} value={tool.id}>
              {tool.name}
            </option>
          ))}
        </Select>
        <Button
          disabled={!selected}
          loading={change.isPending}
          className="sm:w-36"
          onClick={() =>
            change.mutate(
              {
                run: () => api.post<AgentDetail>(`/agents/${agent.id}/tools`, { toolId: selected }),
                done: "Tool attached. Publish to apply.",
              },
              { onSuccess: () => setSelected("") },
            )
          }
        >
          Attach tool
        </Button>
      </div>
    </Section>
  );
}

/* ---------------------------------------------------------------------------- configuration */

function numberOrNull(text: string): number | null {
  return text.trim() === "" ? null : Number(text);
}

function ConfigurationSection({ agent }: { agent: AgentDetail }) {
  const client = useQueryClient();
  const notify = useToast();
  const config = agent.configuration;
  const [model, setModel] = useState(config.model ?? "");
  const [temperature, setTemperature] = useState(config.temperature?.toString() ?? "");
  const [maxTokens, setMaxTokens] = useState(config.maxTokens?.toString() ?? "");
  const [maxToolRounds, setMaxToolRounds] = useState(config.maxToolRounds.toString());
  const models = useModels();
  // Keep the saved model selectable even if it no longer appears in the list.
  const modelChoices = [...new Set([...(models.data?.models ?? []), ...(config.model ? [config.model] : [])])];

  useEffect(() => {
    setModel(config.model ?? "");
    setTemperature(config.temperature?.toString() ?? "");
    setMaxTokens(config.maxTokens?.toString() ?? "");
    setMaxToolRounds(config.maxToolRounds.toString());
  }, [config.model, config.temperature, config.maxTokens, config.maxToolRounds]);

  const save = useMutation({
    mutationFn: () =>
      api.put<AgentConfiguration>(`/agents/${agent.id}/configuration`, {
        model: model.trim() || null,
        temperature: numberOrNull(temperature),
        maxTokens: numberOrNull(maxTokens),
        maxToolRounds: numberOrNull(maxToolRounds),
      }),
    onSuccess: (saved) => {
      client.setQueryData<AgentDetail>(keys.agent(agent.id), (current) => (current ? { ...current, configuration: saved } : current));
      notify("success", "Model settings saved. Runs use them right away; publish again to update the Foundry agent.");
    },
    onError: (error) => notify("error", errorMessage(error)),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate();
  }

  return (
    <Section title="Model settings" description="How each Azure OpenAI call is made. Blank means the default." className="lg:self-start">
      <form onSubmit={submit} className="space-y-4">
        <Field
          label="Model"
          htmlFor="cfg-model"
          hint={models.data?.foundryError ? `Foundry list unavailable: ${models.data.foundryError}` : "Deployments in your Azure OpenAI / Foundry resource. Publish again to register a change in Foundry."}
        >
          <Select id="cfg-model" value={model} onChange={(event) => setModel(event.target.value)} className="font-mono">
            <option value="">Default ({models.data?.default ?? "AZURE_OPENAI_DEPLOYMENT"})</option>
            {modelChoices.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </Select>
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Temperature" htmlFor="cfg-temp" hint="0 to 2">
            <Input id="cfg-temp" type="number" min={0} max={2} step={0.1} value={temperature} onChange={(event) => setTemperature(event.target.value)} />
          </Field>
          <Field label="Max tokens" htmlFor="cfg-tokens" hint="Per reply">
            <Input id="cfg-tokens" type="number" min={1} value={maxTokens} onChange={(event) => setMaxTokens(event.target.value)} />
          </Field>
        </div>
        <Field label="Tool rounds" htmlFor="cfg-rounds" hint="Safety stop for the model → tool → model loop (1 to 50).">
          <Input id="cfg-rounds" type="number" min={1} max={50} value={maxToolRounds} onChange={(event) => setMaxToolRounds(event.target.value)} />
        </Field>
        <Button type="submit" loading={save.isPending} className="w-full">
          Save settings
        </Button>
      </form>
    </Section>
  );
}

/* ---------------------------------------------------------------------------- prompt preview */

function StackBlock({
  step,
  title,
  note,
  children,
  delay,
  accent = false,
}: {
  step: string;
  title: string;
  note: ReactNode;
  children: ReactNode;
  delay: number;
  accent?: boolean;
}) {
  return (
    <li className="stack-in relative pl-10" style={{ animationDelay: `${delay}ms` }}>
      <span
        aria-hidden
        className={cx(
          "absolute top-0 left-0 flex size-7 items-center justify-center rounded-full border-2 bg-surface text-xs font-semibold",
          accent ? "border-signal-500 text-signal-800" : "border-ink-700 text-ink-700",
        )}
      >
        {step}
      </span>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-semibold text-ink-950">{title}</h3>
        <span className="text-sm text-ink-500">{note}</span>
      </div>
      <div className="mt-2">{children}</div>
    </li>
  );
}

function PromptBox({ text, tone = "light" }: { text: string; tone?: "light" | "dark" }) {
  return (
    <pre
      className={cx(
        "max-h-80 overflow-auto rounded-md border p-4 font-mono text-[12.5px] leading-relaxed whitespace-pre-wrap",
        tone === "dark" ? "border-ink-800 bg-ink-950 text-ink-200" : "border-line bg-paper text-ink-800",
      )}
    >
      {text}
    </pre>
  );
}

const USER_MARKER = "## User message\n\n";

/** The injected skill instructions (scrollable), then the person's own message, highlighted. */
function UserMessage({ text }: { text: string }) {
  const at = text.lastIndexOf(USER_MARKER);
  if (at === -1) return <PromptBox text={text} />;
  const injected = text.slice(0, at).replace(/\n+---\n+$/, "");
  const own = text.slice(at + USER_MARKER.length);
  return (
    <div className="space-y-2">
      <PromptBox text={injected} />
      <div className="rounded-md border border-signal-400/60 bg-signal-50 px-4 py-3">
        <p className="mb-1 text-xs font-medium text-signal-800">Your message, placed after the skill instructions</p>
        <p className="font-mono text-[13px] whitespace-pre-wrap text-ink-950">{own}</p>
      </div>
    </div>
  );
}

function PreviewTab({ agent }: { agent: AgentDetail }) {
  const [message, setMessage] = useState("Generate test plan for project P06");
  const preview = useMutation({
    mutationFn: (text: string) => api.post<PromptPreview>(`/agents/${agent.id}/preview-prompt`, { message: text }),
  });

  if (agent.publishedVersion === 0) {
    return (
      <EmptyState
        title="Publish first"
        body="The system message is the skill index built when you publish. Attach a skill, publish, then come back to preview a message."
      />
    );
  }

  const result = preview.data;
  const singleSkill = agent.skills.length === 1;

  return (
    <div className="grid gap-8 lg:grid-cols-5">
      <div className="lg:col-span-2">
        <h2 className="font-semibold text-ink-950">Try a message</h2>
        <p className="mt-1 text-sm text-ink-500">
          See exactly what a run would send to the model for this message: which skills are selected and how the final prompt is assembled.
          Nothing is sent to Azure OpenAI.
        </p>
        <form
          className="mt-4 space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            preview.mutate(message);
          }}
        >
          <Textarea rows={5} value={message} onChange={(event) => setMessage(event.target.value)} aria-label="Message" />
          <Button type="submit" variant="primary" icon={<Eye className="size-4" />} loading={preview.isPending} disabled={!message.trim()}>
            Preview prompt
          </Button>
        </form>
        {preview.isError && <div className="mt-4"><ErrorNotice error={preview.error} title="Preview failed" /></div>}
        <div className="mt-6 rounded-md bg-ink-900/[0.04] px-4 py-3 text-sm text-ink-700">
          {singleSkill
            ? "This agent has one skill, so its full instructions go with every message, whatever the wording."
            : "With several skills, a skill's instructions are sent only when the message contains one of its trigger phrases."}
        </div>
      </div>

      <div className="lg:col-span-3">
        {!result ? (
          <div className="flex h-full min-h-60 items-center justify-center rounded-lg border border-dashed border-line-strong bg-surface px-6 text-center text-ink-500">
            The assembled prompt appears here.
          </div>
        ) : (
          <ol key={`${result.userMessage.length}-${result.matchedSkills.join()}`} className="relative space-y-7 before:absolute before:top-3 before:bottom-3 before:left-[13px] before:w-0.5 before:bg-line">
            <StackBlock step="1" title="System message" note={`Published skill index, v${agent.publishedVersion}`} delay={0}>
              <PromptBox text={result.systemMessage} tone="dark" />
            </StackBlock>
            <StackBlock
              step="2"
              title="Skills selected for this message"
              note={result.matchedSkills.length ? (singleSkill ? "Only skill: always sent" : "Matched a trigger phrase") : "No trigger phrase matched"}
              delay={90}
              accent
            >
              {result.matchedSkills.length ? (
                <div className="flex flex-wrap gap-1.5">
                  {result.matchedSkills.map((name) => (
                    <Badge key={name} tone="signal">
                      {name}
                    </Badge>
                  ))}
                </div>
              ) : (
                <p className="rounded-md border border-signal-100 bg-signal-50 px-3 py-2 text-sm text-signal-800">
                  The model gets only the index above and must decide on its own whether a skill applies. Add a trigger phrase to the message to send the full procedure.
                </p>
              )}
            </StackBlock>
            <StackBlock step="3" title="User message as sent" note={`${result.userMessage.length.toLocaleString()} characters`} delay={180}>
              <UserMessage text={result.userMessage} />
            </StackBlock>
            <StackBlock step="4" title="Tools offered" note={`${result.tools.length} tool${result.tools.length === 1 ? "" : "s"}`} delay={270}>
              {result.tools.length ? (
                <div className="flex flex-wrap gap-1.5">
                  {result.tools.map((name) => (
                    <Chip key={name}>{name}</Chip>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-ink-500">None. The model can only answer with text.</p>
              )}
            </StackBlock>
          </ol>
        )}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------------------- edit dialog */

const STATUS_OPTIONS: Array<{ id: AgentStatus; label: string }> = [
  { id: "DRAFT", label: "Draft" },
  { id: "ACTIVE", label: "Active" },
  { id: "INACTIVE", label: "Paused" },
  { id: "ARCHIVED", label: "Archived" },
];

function EditAgentModal({ agent, open, onClose }: { agent: AgentDetail; open: boolean; onClose: () => void }) {
  const change = useAgentChange(agent.id);
  const [name, setName] = useState(agent.name);
  const [description, setDescription] = useState(agent.description ?? "");
  const [owner, setOwner] = useState(agent.owner ?? "");
  const [status, setStatus] = useState<AgentStatus>(agent.status);

  useEffect(() => {
    if (!open) return;
    setName(agent.name);
    setDescription(agent.description ?? "");
    setOwner(agent.owner ?? "");
    setStatus(agent.status);
  }, [open, agent.name, agent.description, agent.owner, agent.status]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const input: AgentUpdateInput = {
      name: name.trim(),
      description: description.trim() || null,
      owner: owner.trim() || null,
      status,
    };
    change.mutate({ run: () => api.put<AgentDetail>(`/agents/${agent.id}`, input), done: "Agent saved." }, { onSuccess: onClose });
  }

  return (
    <Modal
      open={open}
      title="Edit agent"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="edit-agent" loading={change.isPending} disabled={!name.trim()}>
            Save changes
          </Button>
        </>
      }
    >
      <form id="edit-agent" onSubmit={submit} className="space-y-4">
        <Field label="Name" htmlFor="edit-name">
          <Input id="edit-name" value={name} onChange={(event) => setName(event.target.value)} />
        </Field>
        <Field label="Description" htmlFor="edit-description">
          <Textarea id="edit-description" rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Owner" htmlFor="edit-owner">
            <Input id="edit-owner" value={owner} onChange={(event) => setOwner(event.target.value)} />
          </Field>
          <Field label="Status" htmlFor="edit-status" hint={agent.publishedVersion === 0 ? "Active needs a publish first." : undefined}>
            <Select id="edit-status" value={status} onChange={(event) => setStatus(event.target.value as AgentStatus)}>
              {STATUS_OPTIONS.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      </form>
    </Modal>
  );
}

/* ---------------------------------------------------------------------------- page */

export function AgentDetailPage() {
  const { agentId = "" } = useParams();
  const navigate = useNavigate();
  const notify = useToast();
  const invalidate = useInvalidate();
  const agent = useAgent(agentId);
  const publish = useAgentChange(agentId);
  const [tab, setTab] = useState<TabId>("setup");
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const remove = useMutation({
    mutationFn: () => api.delete(`/agents/${agentId}`),
    onSuccess: async () => {
      await invalidate("agents");
      notify(
        "success",
        agent.data?.foundryAgentName
          ? `Agent deleted here and in Azure AI Foundry (${agent.data.foundryAgentName}).`
          : "Agent deleted, with its settings and run history.",
      );
      navigate("/agents");
    },
    onError: (error) => notify("error", errorMessage(error)),
  });

  const back = (
    <Link to="/agents" className="inline-flex items-center gap-1 text-sm text-ink-500 hover:text-ink-900">
      <ChevronLeft className="size-4" aria-hidden />
      Agents
    </Link>
  );

  if (agent.isPending) return <Loading label="Loading agent…" />;
  if (agent.isError)
    return (
      <>
        <div className="mb-4">{back}</div>
        <ErrorNotice error={agent.error} title="Couldn't load this agent" />
      </>
    );

  const data = agent.data;

  return (
    <>
      <PageHeader
        back={back}
        title={
          <span className="flex flex-wrap items-center gap-3">
            {data.name}
            <StatusBadge status={data.status} />
          </span>
        }
        description={
          <>
            {data.description && <p>{data.description}</p>}
            <p className="mt-1 text-sm">
              {data.publishedVersion > 0 ? `Version ${data.publishedVersion}, published ${dateTime(data.publishedAt)}` : "Not published yet"}
              {data.owner ? `. Owner: ${data.owner}` : ""}
            </p>
            <p className="mt-1 text-sm">
              {data.foundryAgentName ? (
                <>
                  Azure AI Foundry: <span className="font-mono text-ink-900">{data.foundryAgentName}</span> version {data.foundryAgentVersion},
                  registered {dateTime(data.foundryPublishedAt)}
                </>
              ) : (
                "Not registered in Azure AI Foundry yet: Publish registers it."
              )}
            </p>
          </>
        }
        actions={
          <>
            <Button variant="ghost" icon={<Trash2 className="size-4" />} onClick={() => setDeleting(true)}>
              Delete
            </Button>
            <Button icon={<Pencil className="size-4" />} onClick={() => setEditing(true)}>
              Edit
            </Button>
            <Button
              variant="primary"
              icon={<Rocket className="size-4" />}
              loading={publish.isPending}
              disabled={data.skills.length === 0}
              title={data.skills.length === 0 ? "Attach at least one skill first" : undefined}
              onClick={() =>
                publish.mutate(
                  {
                    run: () => api.post<AgentDetail>(`/agents/${agentId}/publish`),
                    done: (published) =>
                      published.foundryAgentName
                        ? `Published version ${published.publishedVersion} and registered in Foundry as ${published.foundryAgentName} (version ${published.foundryAgentVersion}).`
                        : `Published version ${published.publishedVersion}.`,
                  },
                  { onSuccess: () => setTab("preview") },
                )
              }
            >
              {data.publishedVersion > 0 ? "Publish again" : "Publish"}
            </Button>
          </>
        }
      />

      <Tabs<TabId>
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "setup", label: "Setup" },
          { id: "run", label: "Run" },
          { id: "scores", label: "Scores" },
          { id: "preview", label: "Prompt preview" },
          { id: "instructions", label: "Published instructions" },
        ]}
      />

      {tab === "setup" && (
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            <SkillsSection agent={data} />
            <ToolsSection agent={data} />
          </div>
          <ConfigurationSection agent={data} />
        </div>
      )}

      {tab === "run" && <RunTab agent={data} />}

      {tab === "scores" && <ScoresTab agent={data} />}

      {tab === "preview" && <PreviewTab agent={data} />}

      {tab === "instructions" &&
        (data.publishedInstructions ? (
          <div>
            <p className="mb-3 max-w-[72ch] text-ink-500">
              The system message every run starts with: a short index of the agent's skills, built at version {data.publishedVersion}. Changes to
              skills or their trigger phrases appear here after the next publish.
            </p>
            <PromptBox text={data.publishedInstructions} tone="dark" />
          </div>
        ) : (
          <EmptyState title="Nothing published yet" body="Attach a skill and publish. The skill index built at publish appears here." />
        ))}

      <EditAgentModal agent={data} open={editing} onClose={() => setEditing(false)} />
      <ConfirmDialog
        open={deleting}
        title={`Delete ${data.name}?`}
        body={
          <>
            <p>
              The agent, its model settings, its skill and tool attachments and its run history are deleted. Skills and tools themselves are
              kept.
            </p>
            {data.foundryAgentName && (
              <p className="mt-3">
                It is also deleted in Azure AI Foundry: <span className="font-mono text-ink-900">{data.foundryAgentName}</span>, all versions. If
                Foundry refuses, nothing is deleted.
              </p>
            )}
          </>
        }
        confirmLabel="Delete agent"
        loading={remove.isPending}
        onConfirm={() => remove.mutate()}
        onClose={() => setDeleting(false)}
      />
    </>
  );
}
