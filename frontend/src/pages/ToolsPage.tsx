import { Plus } from "lucide-react";
import { Link, useNavigate } from "react-router";

import { Badge, Button, EmptyState, ErrorNotice, Loading, PageHeader, Table, Td, Th } from "../components/ui";
import { timeAgo } from "../lib/format";
import { useSkills, useTools } from "../lib/queries";

function argumentNames(parameters: Record<string, unknown>): string[] {
  const properties = parameters.properties;
  return properties && typeof properties === "object" ? Object.keys(properties as Record<string, unknown>) : [];
}

export function ToolsPage() {
  const tools = useTools();
  const skills = useSkills();
  const navigate = useNavigate();

  const usedBy = new Map<string, string[]>();
  for (const skill of skills.data ?? []) {
    for (const toolId of skill.requiredToolIds) usedBy.set(toolId, [...(usedBy.get(toolId) ?? []), skill.name]);
  }

  const newButton = (
    <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => navigate("/tools/new")}>
      New tool
    </Button>
  );

  return (
    <>
      <PageHeader
        title="Tools"
        description="Functions an agent may call. The model sees each tool's name, description and argument schema, and asks the backend to run it."
        actions={newButton}
      />

      {tools.isPending ? (
        <Loading />
      ) : tools.isError ? (
        <ErrorNotice error={tools.error} />
      ) : tools.data.length === 0 ? (
        <EmptyState title="No tools yet" body="Register a tool such as read_file so skills can read the BRD instead of guessing." action={newButton} />
      ) : (
        <Table
          head={
            <>
              <Th>Tool</Th>
              <Th className="hidden md:table-cell">Arguments</Th>
              <Th className="hidden lg:table-cell">Required by</Th>
              <Th className="hidden md:table-cell">Changed</Th>
            </>
          }
        >
          {tools.data.map((tool) => {
            const args = argumentNames(tool.parameters);
            const skillsUsing = usedBy.get(tool.id) ?? [];
            return (
              <tr key={tool.id} className="hover:bg-paper/70">
                <Td>
                  <div className="flex flex-wrap items-center gap-2">
                    <Link to={`/tools/${tool.id}`} className="font-mono text-[14px] font-medium text-ink-950 underline-offset-2 hover:underline">
                      {tool.name}
                    </Link>
                    {tool.toolType === "http" && <Badge>HTTP</Badge>}
                  </div>
                  <p className="mt-0.5 line-clamp-2 max-w-[60ch] text-sm text-ink-500">{tool.description}</p>
                </Td>
                <Td className="hidden font-mono text-[13px] text-ink-700 md:table-cell">{args.length ? args.join(", ") : "none"}</Td>
                <Td className="hidden text-sm text-ink-700 lg:table-cell">{skillsUsing.length ? skillsUsing.join(", ") : <span className="text-ink-400">No skill</span>}</Td>
                <Td className="hidden text-ink-500 md:table-cell">{timeAgo(tool.updatedAt)}</Td>
              </tr>
            );
          })}
        </Table>
      )}
    </>
  );
}
