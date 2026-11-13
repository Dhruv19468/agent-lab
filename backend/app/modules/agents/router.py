from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.core.dependencies import DbSession
from app.modules.agents.schemas import (
    AgentConfigurationRead,
    AgentConfigurationUpdate,
    AgentCreate,
    AgentDetailRead,
    AgentRead,
    AgentStatus,
    AgentUpdate,
    AttachSkillRequest,
    AttachToolRequest,
    PromptPreviewRead,
    PromptPreviewRequest,
)
from app.modules.agents.service import AgentService

router = APIRouter(prefix="/agents", tags=["agents"])


# --- agents -------------------------------------------------------------------------------


@router.post("", response_model=AgentDetailRead, status_code=status.HTTP_201_CREATED)
async def create_agent(payload: AgentCreate, session: DbSession) -> AgentDetailRead:
    return await AgentService(session).create_agent(payload)


@router.get("", response_model=list[AgentRead])
async def list_agents(
    session: DbSession,
    status_filter: AgentStatus | None = Query(default=None, alias="status"),
) -> list[AgentRead]:
    return await AgentService(session).list_agents(status_filter)


@router.get("/{agent_id}", response_model=AgentDetailRead)
async def get_agent(agent_id: uuid.UUID, session: DbSession) -> AgentDetailRead:
    return await AgentService(session).detail(agent_id)


@router.put("/{agent_id}", response_model=AgentDetailRead)
async def update_agent(agent_id: uuid.UUID, payload: AgentUpdate, session: DbSession) -> AgentDetailRead:
    return await AgentService(session).update_agent(agent_id, payload)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: uuid.UUID, session: DbSession) -> None:
    await AgentService(session).delete_agent(agent_id)


# --- configuration ------------------------------------------------------------------------


@router.get("/{agent_id}/configuration", response_model=AgentConfigurationRead)
async def get_configuration(agent_id: uuid.UUID, session: DbSession) -> AgentConfigurationRead:
    return await AgentService(session).read_configuration(agent_id)


@router.put("/{agent_id}/configuration", response_model=AgentConfigurationRead)
async def update_configuration(
    agent_id: uuid.UUID, payload: AgentConfigurationUpdate, session: DbSession
) -> AgentConfigurationRead:
    return await AgentService(session).update_configuration(agent_id, payload)


# --- skills and tools ---------------------------------------------------------------------


@router.post("/{agent_id}/skills", response_model=AgentDetailRead)
async def attach_skill(agent_id: uuid.UUID, payload: AttachSkillRequest, session: DbSession) -> AgentDetailRead:
    return await AgentService(session).attach_skill(agent_id, payload.skill_id)


@router.delete("/{agent_id}/skills/{skill_id}", response_model=AgentDetailRead)
async def detach_skill(agent_id: uuid.UUID, skill_id: uuid.UUID, session: DbSession) -> AgentDetailRead:
    return await AgentService(session).detach_skill(agent_id, skill_id)


@router.post("/{agent_id}/tools", response_model=AgentDetailRead)
async def attach_tool(agent_id: uuid.UUID, payload: AttachToolRequest, session: DbSession) -> AgentDetailRead:
    return await AgentService(session).attach_tool(agent_id, payload.tool_id)


@router.delete("/{agent_id}/tools/{tool_id}", response_model=AgentDetailRead)
async def detach_tool(agent_id: uuid.UUID, tool_id: uuid.UUID, session: DbSession) -> AgentDetailRead:
    return await AgentService(session).detach_tool(agent_id, tool_id)


# --- publish and preview ------------------------------------------------------------------


@router.post("/{agent_id}/publish", response_model=AgentDetailRead)
async def publish_agent(agent_id: uuid.UUID, session: DbSession) -> AgentDetailRead:
    return await AgentService(session).publish_agent(agent_id)


@router.post("/{agent_id}/preview-prompt", response_model=PromptPreviewRead)
async def preview_prompt(
    agent_id: uuid.UUID, payload: PromptPreviewRequest, session: DbSession
) -> PromptPreviewRead:
    return await AgentService(session).preview_prompt(agent_id, payload.message)
