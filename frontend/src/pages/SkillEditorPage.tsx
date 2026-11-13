import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import Markdown from "react-markdown";
import { Link, useNavigate, useParams } from "react-router";
import remarkGfm from "remark-gfm";

import { TagInput } from "../components/TagInput";
import { useToast } from "../components/toast";
import { Button, ConfirmDialog, ErrorNotice, Field, Input, Loading, PageHeader, Section, Textarea, cx } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { keys, useInvalidate, useSkill, useTools } from "../lib/queries";
import type { Skill, SkillInput } from "../lib/types";

const STARTER = `# BRD to Test Plan

## When to use
When the user asks for a test plan from a BRD.

## Your tools
| Tool | Use it to |
|---|---|
| \`read_file\` | Read the BRD and the architecture description |

## Procedure
1. Read the BRD and the architecture description. Never guess what a file contains.
2. Write the plan in the standard sections.
3. If an input is missing, say what is missing and stop.

## Output
Markdown, one heading per section.
`;

export function SkillEditorPage() {
  const { skillId } = useParams();
  const isNew = !skillId;
  const navigate = useNavigate();
  const notify = useToast();
  const client = useQueryClient();
  const invalidate = useInvalidate();
  const skill = useSkill(skillId);
  const tools = useTools();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [triggers, setTriggers] = useState<string[]>([]);
  const [toolIds, setToolIds] = useState<string[]>([]);
  const [instructions, setInstructions] = useState(isNew ? STARTER : "");
  const [mode, setMode] = useState<"write" | "preview">("write");
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!skill.data) return;
    setName(skill.data.name);
    setDescription(skill.data.description ?? "");
    setTriggers(skill.data.triggerPhrases);
    setToolIds(skill.data.requiredToolIds);
    setInstructions(skill.data.instructions);
  }, [skill.data]);

  const save = useMutation({
    mutationFn: (input: SkillInput) => (isNew ? api.post<Skill>("/skills", input) : api.put<Skill>(`/skills/${skillId}`, input)),
    onSuccess: async (saved) => {
      client.setQueryData(keys.skill(saved.id), saved);
      await invalidate("skills", "agents");
      notify(
        "success",
        isNew ? `Created ${saved.name}.` : `Saved ${saved.name}. Instructions apply on the next run; republish agents to update their skill index.`,
      );
      if (isNew) navigate(`/skills/${saved.id}`, { replace: true });
    },
    onError: (error) => notify("error", errorMessage(error)),
  });

  const remove = useMutation({
    mutationFn: () => api.delete(`/skills/${skillId}`),
    onSuccess: async () => {
      await invalidate("skills", "agents");
      notify("success", "Skill deleted and detached from every agent.");
      navigate("/skills");
    },
    onError: (error) => notify("error", errorMessage(error)),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate({
      name: name.trim(),
      description: description.trim() || null,
      instructions,
      triggerPhrases: triggers,
      requiredToolIds: toolIds,
    });
  }

  function toggleTool(id: string) {
    setToolIds((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
  }

  const back = (
    <Link to="/skills" className="inline-flex items-center gap-1 text-sm text-ink-500 hover:text-ink-900">
      <ChevronLeft className="size-4" aria-hidden />
      Skills
    </Link>
  );

  if (!isNew && skill.isPending) return <Loading label="Loading skill…" />;
  if (!isNew && skill.isError)
    return (
      <>
        <div className="mb-4">{back}</div>
        <ErrorNotice error={skill.error} title="Couldn't load this skill" />
      </>
    );

  return (
    <>
      <PageHeader
        back={back}
        title={isNew ? "New skill" : name || "Skill"}
        description="The description and trigger phrases go into every agent's skill index. The instructions are sent only when the skill is selected for a message."
        actions={
          !isNew && (
            <Button variant="ghost" icon={<Trash2 className="size-4" />} onClick={() => setDeleting(true)}>
              Delete
            </Button>
          )
        }
      />

      <form onSubmit={submit} className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <section className="rounded-lg border border-line bg-surface">
            <div className="flex items-center justify-between border-b border-line px-5 py-3">
              <h2 className="font-semibold text-ink-950">Instructions</h2>
              <div className="flex rounded-md border border-line p-0.5 text-sm" role="tablist">
                {(["write", "preview"] as const).map((item) => (
                  <button
                    key={item}
                    type="button"
                    role="tab"
                    aria-selected={mode === item}
                    onClick={() => setMode(item)}
                    className={cx("rounded px-3 py-1 capitalize", mode === item ? "bg-ink-900 text-white" : "text-ink-500 hover:text-ink-900")}
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>
            {mode === "write" ? (
              <Textarea
                aria-label="Instructions"
                rows={24}
                spellCheck={false}
                value={instructions}
                onChange={(event) => setInstructions(event.target.value)}
                className="rounded-none rounded-b-lg border-0 font-mono text-[13px] focus:ring-0"
              />
            ) : (
              <div className="md min-h-[30rem] px-6 py-5">
                <Markdown remarkPlugins={[remarkGfm]}>{instructions || "*Nothing written yet.*"}</Markdown>
              </div>
            )}
          </section>
        </div>

        <div className="space-y-6">
          <Section title="Details">
            <div className="space-y-4">
              <Field label="Name" htmlFor="skill-name">
                <Input id="skill-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="BRD to Test Plan" />
              </Field>
              <Field label="Description" htmlFor="skill-description" hint="What it produces and from what. The model reads this to decide whether the skill applies.">
                <Textarea id="skill-description" rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
              </Field>
              <Field label="Trigger phrases" htmlFor="skill-triggers" hint="Press Enter after each. Make them specific: “test plan from brd”, not “report”.">
                <TagInput id="skill-triggers" value={triggers} onChange={setTriggers} placeholder="generate test plan" />
              </Field>
            </div>
          </Section>

          <Section title="Required tools" description="Attaching this skill to an agent attaches these too.">
            {tools.isPending ? (
              <Loading />
            ) : (tools.data ?? []).length === 0 ? (
              <p className="text-sm text-ink-500">
                No tools registered. <Link to="/tools/new" className="text-ink-900 underline">Create one</Link> if the instructions call a tool.
              </p>
            ) : (
              <ul className="space-y-1">
                {(tools.data ?? []).map((tool) => (
                  <li key={tool.id}>
                    <label className="flex cursor-pointer items-start gap-3 rounded-md px-2 py-2 hover:bg-paper">
                      <input
                        type="checkbox"
                        checked={toolIds.includes(tool.id)}
                        onChange={() => toggleTool(tool.id)}
                        className="mt-1 size-4 accent-ink-900"
                      />
                      <span className="min-w-0">
                        <span className="block font-mono text-[13.5px] text-ink-950">{tool.name}</span>
                        <span className="block text-sm text-ink-500">{tool.description}</span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Button type="submit" variant="primary" className="w-full" loading={save.isPending} disabled={!name.trim() || !instructions.trim()}>
            {isNew ? "Create skill" : "Save skill"}
          </Button>
        </div>
      </form>

      <ConfirmDialog
        open={deleting}
        title={`Delete ${name}?`}
        body="The skill is removed from every agent that has it. Tools it brought to those agents stay attached until you detach them."
        confirmLabel="Delete skill"
        loading={remove.isPending}
        onConfirm={() => remove.mutate()}
        onClose={() => setDeleting(false)}
      />
    </>
  );
}
