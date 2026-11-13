from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.core.dependencies import DbSession
from app.modules.skills.schemas import SkillCreate, SkillRead, SkillUpdate
from app.modules.skills.service import SkillService

router = APIRouter(prefix="/skills", tags=["skills"])


@router.post("", response_model=SkillRead, status_code=status.HTTP_201_CREATED)
async def create_skill(payload: SkillCreate, session: DbSession) -> SkillRead:
    return await SkillService(session).create_skill(payload)


@router.get("", response_model=list[SkillRead])
async def list_skills(session: DbSession) -> list[SkillRead]:
    return await SkillService(session).list_skills()


@router.get("/{skill_id}", response_model=SkillRead)
async def get_skill(skill_id: uuid.UUID, session: DbSession) -> SkillRead:
    return await SkillService(session).read_skill(skill_id)


@router.put("/{skill_id}", response_model=SkillRead)
async def update_skill(skill_id: uuid.UUID, payload: SkillUpdate, session: DbSession) -> SkillRead:
    return await SkillService(session).update_skill(skill_id, payload)


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(skill_id: uuid.UUID, session: DbSession) -> None:
    await SkillService(session).delete_skill(skill_id)
