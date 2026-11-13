import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { JsonField, parseJsonObject } from "../components/JsonField";
import { useToast } from "../components/toast";
import { Button, ConfirmDialog, ErrorNotice, Field, Input, Loading, PageHeader, Section, Select, Textarea } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { keys, useInvalidate, useTool } from "../lib/queries";
import type { Tool, ToolInput, ToolType } from "../lib/types";

const NAME_PATTERN = /^[a-zA-Z0-9_-]{1,64}$/;

const STARTER_PARAMETERS = {
  type: "object",
  properties: {
    path: { type: "string", description: "File path inside the data folder, e.g. processed/validation/P06/brd.md" },
    offset: { type: "integer", description: "Character position to continue from for long files. Default 0." },
  },
  required: ["path"],
};

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export function ToolEditorPage() {
  const { toolId } = useParams();
  const isNew = !toolId;
  const navigate = useNavigate();
  const notify = useToast();
  const client = useQueryClient();
  const invalidate = useInvalidate();
  const tool = useTool(toolId);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [toolType, setToolType] = useState<ToolType>("builtin");
  const [parameters, setParameters] = useState(isNew ? pretty(STARTER_PARAMETERS) : "");
  const [config, setConfig] = useState(isNew ? "{}" : "");
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!tool.data) return;
    setName(tool.data.name);
    setDescription(tool.data.description);
    setToolType(tool.data.toolType);
    setParameters(pretty(tool.data.parameters));
    setConfig(pretty(tool.data.config));
  }, [tool.data]);

  const parsedParameters = parseJsonObject(parameters);
  const parsedConfig = parseJsonObject(config);
  const nameError = name && !NAME_PATTERN.test(name) ? "Letters, digits, _ and - only, no spaces (max 64)." : null;
  const canSave = Boolean(name) && !nameError && description.trim() !== "" && !parsedParameters.error && !parsedConfig.error;

  const save = useMutation({
    mutationFn: (input: ToolInput) => (isNew ? api.post<Tool>("/tools", input) : api.put<Tool>(`/tools/${toolId}`, input)),
    onSuccess: async (saved) => {
      client.setQueryData(keys.tool(saved.id), saved);
      await invalidate("tools", "skills", "agents");
      notify("success", isNew ? `Created ${saved.name}.` : `Saved ${saved.name}. Republish agents that use it.`);
      if (isNew) navigate(`/tools/${saved.id}`, { replace: true });
    },
    onError: (error) => notify("error", errorMessage(error)),
  });

  const remove = useMutation({
    mutationFn: () => api.delete(`/tools/${toolId}`),
    onSuccess: async () => {
      await invalidate("tools", "agents");
      notify("success", "Tool deleted.");
      navigate("/tools");
    },
    onError: (error) => {
      setDeleting(false);
      notify("error", errorMessage(error));
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!canSave || !parsedParameters.value || !parsedConfig.value) return;
    save.mutate({
      name,
      description: description.trim(),
      toolType,
      parameters: parsedParameters.value,
      config: parsedConfig.value,
    });
  }

  const back = (
    <Link to="/tools" className="inline-flex items-center gap-1 text-sm text-ink-500 hover:text-ink-900">
      <ChevronLeft className="size-4" aria-hidden />
      Tools
    </Link>
  );

  if (!isNew && tool.isPending) return <Loading label="Loading tool…" />;
  if (!isNew && tool.isError)
    return (
      <>
        <div className="mb-4">{back}</div>
        <ErrorNotice error={tool.error} title="Couldn't load this tool" />
      </>
    );

  return (
    <>
      <PageHeader
        back={back}
        title={isNew ? "New tool" : <span className="font-mono text-[22px]">{name || "tool"}</span>}
        description="The name, description and parameter schema are what the model sees. Config is for the backend only and never reaches the model."
        actions={
          !isNew && (
            <Button variant="ghost" icon={<Trash2 className="size-4" />} onClick={() => setDeleting(true)}>
              Delete
            </Button>
          )
        }
      />

      <form onSubmit={submit} className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6">
          <Section title="What the model sees">
            <div className="space-y-4">
              <Field label="Name" htmlFor="tool-name" error={nameError} hint="The function name the model calls, e.g. read_file.">
                <Input id="tool-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="read_file" className="font-mono text-[14px]" />
              </Field>
              <Field label="Description" htmlFor="tool-description" hint="What it does, when to use it and what it returns. The model decides when to call it from this.">
                <Textarea
                  id="tool-description"
                  rows={5}
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder="Read a text file from the project data folder. Use it to get a BRD before writing a plan."
                />
              </Field>
              <Field label="Runs as" htmlFor="tool-type">
                <Select id="tool-type" value={toolType} onChange={(event) => setToolType(event.target.value as ToolType)}>
                  <option value="builtin">Built-in Python function</option>
                  <option value="http">External HTTP endpoint</option>
                </Select>
              </Field>
            </div>
          </Section>
          <Button type="submit" variant="primary" className="w-full" loading={save.isPending} disabled={!canSave}>
            {isNew ? "Create tool" : "Save tool"}
          </Button>
        </div>

        <div className="space-y-6 lg:col-span-2">
          <Section title="Parameters" description='A JSON Schema with "type": "object". Each property is an argument the model fills in.'>
            <JsonField id="tool-parameters" value={parameters} onChange={setParameters} rows={16} />
          </Section>
          <Section title="Config" description="Settings for running the tool, e.g. a base folder. Not shown to the model.">
            <JsonField id="tool-config" value={config} onChange={setConfig} rows={6} />
          </Section>
        </div>
      </form>

      <ConfirmDialog
        open={deleting}
        title={`Delete ${name}?`}
        body="The tool is removed from every agent. A tool that a skill still requires can't be deleted; remove it from those skills first."
        confirmLabel="Delete tool"
        loading={remove.isPending}
        onConfirm={() => remove.mutate()}
        onClose={() => setDeleting(false)}
      />
    </>
  );
}
