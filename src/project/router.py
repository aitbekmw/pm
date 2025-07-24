from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from .models import Project, ProjectMembership
from .schemas import ProjectRead, ProjectCreate, ProjectMembershipRead, ProjectMembershipCreate
from src.database import get_db
from sqlalchemy.future import select

router = APIRouter(prefix="/projects", tags=["projects"])

# Project Management
@router.get("/", response_model=List[ProjectRead])
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project))
    projects = result.scalars().all()
    return projects

@router.get("/{id}", response_model=ProjectRead)
async def get_project(id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.post("/", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(project_in: ProjectCreate, db: AsyncSession = Depends(get_db)):
    project = Project(**project_in.dict())
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project

@router.patch("/{id}", response_model=ProjectRead)
async def update_project(id: int, project_update: ProjectCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    for field, value in project_update.dict(exclude_unset=True).items():
        setattr(project, field, value)
    await db.commit()
    await db.refresh(project)
    return project

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await db.delete(project)
    await db.commit()
    return None

# Project Membership
@router.get("/{project_id}/members/", response_model=List[ProjectMembershipRead])
async def list_project_members(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ProjectMembership).where(ProjectMembership.project_id == project_id))
    memberships = result.scalars().all()
    return memberships

@router.post("/{project_id}/members/", response_model=ProjectMembershipRead, status_code=status.HTTP_201_CREATED)
async def add_project_member(project_id: int, membership_in: ProjectMembershipCreate, db: AsyncSession = Depends(get_db)):
    membership = ProjectMembership(project_id=project_id, **membership_in.dict(exclude={"project_id"}))
    db.add(membership)
    await db.commit()
    await db.refresh(membership)
    return membership

@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_project_member(project_id: int, user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ProjectMembership).where(ProjectMembership.project_id == project_id, ProjectMembership.user_id == user_id))
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")
    await db.delete(membership)
    await db.commit()
    return None 