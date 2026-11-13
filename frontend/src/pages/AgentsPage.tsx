import { useMutation } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router";

import { useToast } from "../components/toast";
import {
  Button,
  EmptyState,
  ErrorNotice,
  Field,
  Input,
  Loading,
  Modal,
  PageHeader,
  StatusBadge,
  Table,
  Td,
  Th,
  Textarea,
  cx,
} from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { timeAgo } from "../lib/format";
import { useAgents, useInvalidate } from "../lib/queries";
import type { AgentCreateInput, AgentDetail, AgentStatus } from "../lib/types";

type Filter = "ALL" | AgentStatus;

const FILTERS: Array<{ id: Filter; label: string }> = [
  { id: "ALL", label: "All" },
  { id: "ACTIVE", label: "Active" },
  { id: "DRAFT", label: "Draft" },
  { id: "INACTIVE", label: "Paused" },
  { id: "ARCHIVED", label: "Archived" },
];

function CreateAgentModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const notify = useToast();
  const invalidate = useInvalidate();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [owner, setOwner] = useState("");
  const [temperature, setTemperature] = useState("0.2");

  const create = useMutation({
    mutationFn: (input: AgentCreateInput) => api.post<AgentDetail>("/agents", input),
    onSuccess: async (agent) => {
      await invalidate("agents");
      notify("success", `Created ${agent.name}. Attach a skill, then publish.`);
      onClose();
      navigate(`/agents/${agent.id}`);
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    const temp = temperature.trim() === "" ? null : Number(temperature);
    create.mutate({
      name: name.trim(),
      description: description.trim() || null,
      owner: owner.trim() || null,
      configuration: { temperature: temp },
    });
  }

  return (
    <Modal
      open={open}
      title="New agent"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="create-agent" loading={create.isPending} disabled={!name.trim()}>
            Create agent
          </Button>
        </>
      }
    >
      <form id="create-agent" onSubmit={submit} className="space-y-4">
        <Field label="Name" htmlFor="agent-name" hint="Unique. Shown everywhere the agent appears.">
          <Input id="agent-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Test Plan Agent" autoFocus />
        </Field>
        <Field label="Description" htmlFor="agent-description">
          <Textarea
            id="agent-description"
            rows={3}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Writes a test plan from a BRD and an architecture description."
          />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Owner" htmlFor="agent-owner">
            <Input id="agent-owner" value={owner} onChange={(event) => setOwner(event.target.value)} placeholder="QA platform" />
          </Field>
          <Field label="Temperature" htmlFor="agent-temperature" hint="0 to 2. Low values give repeatable output.">
            <Input
              id="agent-temperature"
              type="number"
              min={0}
              max={2}
              step={0.1}
              value={temperature}
              onChange={(event) => setTemperature(event.target.value)}
            />
          </Field>
        </div>
        {create.isError && <p className="text-sm text-bad-600">{errorMessage(create.error)}</p>}
      </form>
    </Modal>
  );
}

export function AgentsPage() {
  const agents = useAgents();
  const [filter, setFilter] = useState<Filter>("ALL");
  const [creating, setCreating] = useState(false);

  const list = (agents.data ?? []).filter((agent) => filter === "ALL" || agent.status === filter);

  return (
    <>
      <PageHeader
        title="Agents"
        description="Each agent is a set of skills and tools plus model settings. Publish an agent to build the instructions it runs with."
        actions={
          <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>
            New agent
          </Button>
        }
      />

      <div className="mb-4 flex flex-wrap gap-1" role="group" aria-label="Filter by status">
        {FILTERS.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setFilter(item.id)}
            aria-pressed={filter === item.id}
            className={cx(
              "rounded-full border px-3 py-1 text-sm transition-colors",
              filter === item.id ? "border-ink-900 bg-ink-900 text-white" : "border-line bg-surface text-ink-700 hover:border-ink-400",
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      {agents.isPending ? (
        <Loading />
      ) : agents.isError ? (
        <ErrorNotice error={agents.error} />
      ) : list.length === 0 ? (
        <EmptyState
          title={filter === "ALL" ? "No agents yet" : "No agents with this status"}
          body={filter === "ALL" ? "Create an agent, attach at least one skill, then publish it." : "Choose another filter or create a new agent."}
          action={
            <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setCreating(true)}>
              New agent
            </Button>
          }
        />
      ) : (
        <Table
          head={
            <>
              <Th>Agent</Th>
              <Th>Status</Th>
              <Th>Published</Th>
              <Th className="hidden md:table-cell">Owner</Th>
              <Th className="hidden md:table-cell">Changed</Th>
            </>
          }
        >
          {list.map((agent) => (
            <tr key={agent.id} className="hover:bg-paper/70">
              <Td>
                <Link to={`/agents/${agent.id}`} className="font-medium text-ink-950 underline-offset-2 hover:underline">
                  {agent.name}
                </Link>
                {agent.description && <p className="mt-0.5 line-clamp-1 max-w-[60ch] text-sm text-ink-500">{agent.description}</p>}
              </Td>
              <Td>
                <StatusBadge status={agent.status} />
              </Td>
              <Td className="text-ink-700 tabular-nums">{agent.publishedVersion > 0 ? `v${agent.publishedVersion}, ${timeAgo(agent.publishedAt)}` : "Not yet"}</Td>
              <Td className="hidden text-ink-700 md:table-cell">{agent.owner ?? "—"}</Td>
              <Td className="hidden text-ink-500 md:table-cell">{timeAgo(agent.updatedAt)}</Td>
            </tr>
          ))}
        </Table>
      )}

      <CreateAgentModal open={creating} onClose={() => setCreating(false)} />
    </>
  );
}
