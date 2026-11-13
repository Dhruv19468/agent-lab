import { Plus } from "lucide-react";
import { Link, useNavigate } from "react-router";

import { Button, Chip, EmptyState, ErrorNotice, Loading, PageHeader, Table, Td, Th } from "../components/ui";
import { timeAgo } from "../lib/format";
import { useSkills, useTools } from "../lib/queries";

export function SkillsPage() {
  const skills = useSkills();
  const tools = useTools();
  const navigate = useNavigate();
  const toolNames = new Map((tools.data ?? []).map((tool) => [tool.id, tool.name]));

  const newButton = (
    <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => navigate("/skills/new")}>
      New skill
    </Button>
  );

  return (
    <>
      <PageHeader
        title="Skills"
        description="A skill is a procedure in Markdown: when to use it, how, and which tools it calls. Agents behave only through their skills."
        actions={newButton}
      />

      {skills.isPending ? (
        <Loading />
      ) : skills.isError ? (
        <ErrorNotice error={skills.error} />
      ) : skills.data.length === 0 ? (
        <EmptyState
          title="No skills yet"
          body="Write the first one, for example BRD to Test Plan, with trigger phrases like “generate test plan”."
          action={newButton}
        />
      ) : (
        <Table
          head={
            <>
              <Th>Skill</Th>
              <Th>Trigger phrases</Th>
              <Th className="hidden lg:table-cell">Required tools</Th>
              <Th className="hidden md:table-cell">Changed</Th>
            </>
          }
        >
          {skills.data.map((skill) => (
            <tr key={skill.id} className="hover:bg-paper/70">
              <Td>
                <Link to={`/skills/${skill.id}`} className="font-medium text-ink-950 underline-offset-2 hover:underline">
                  {skill.name}
                </Link>
                {skill.description && <p className="mt-0.5 line-clamp-2 max-w-[56ch] text-sm text-ink-500">{skill.description}</p>}
              </Td>
              <Td>
                {skill.triggerPhrases.length ? (
                  <div className="flex max-w-xs flex-wrap gap-1.5">
                    {skill.triggerPhrases.slice(0, 4).map((phrase) => (
                      <Chip key={phrase}>{phrase}</Chip>
                    ))}
                    {skill.triggerPhrases.length > 4 && <span className="text-sm text-ink-500">+{skill.triggerPhrases.length - 4}</span>}
                  </div>
                ) : (
                  <span className="text-sm text-ink-400">None: chosen from the index only</span>
                )}
              </Td>
              <Td className="hidden lg:table-cell">
                {skill.requiredToolIds.length ? (
                  <div className="flex flex-wrap gap-1.5">
                    {skill.requiredToolIds.map((id) => (
                      <Chip key={id}>{toolNames.get(id) ?? "unknown tool"}</Chip>
                    ))}
                  </div>
                ) : (
                  <span className="text-sm text-ink-400">None</span>
                )}
              </Td>
              <Td className="hidden text-ink-500 md:table-cell">{timeAgo(skill.updatedAt)}</Td>
            </tr>
          ))}
        </Table>
      )}
    </>
  );
}
