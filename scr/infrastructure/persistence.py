"""Optional SQL persistence for accounts, tenant-scoped research, and evidence."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, create_engine, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class OrganizationRecord(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class UserRecord(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(256))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ResearchProjectRecord(Base):
    __tablename__ = "research_projects"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_project_org_name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class MembershipRecord(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_org_member"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(24), default="analyst")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class BootstrapClaimRecord(Base):
    __tablename__ = "bootstrap_claims"
    claim_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ResearchTaskRecord(Base):
    __tablename__ = "research_tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("research_projects.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    message: Mapped[str] = mapped_column(Text)
    marketplace: Mapped[str] = mapped_column(String(8))
    intent: Mapped[str | None] = mapped_column(String(40), nullable=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    progress: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class EvidenceRecord(Base):
    __tablename__ = "research_evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id: Mapped[str] = mapped_column(ForeignKey("research_tasks.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(80))
    source: Mapped[str] = mapped_column(String(240))
    marketplace: Mapped[str] = mapped_column(String(8))
    captured_at: Mapped[str] = mapped_column(String(40))
    expires_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    raw_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AuditRecord(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class ReportVersionRecord(Base):
    __tablename__ = "report_versions"
    __table_args__ = (UniqueConstraint("task_id", "version", name="uq_report_task_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id: Mapped[str] = mapped_column(ForeignKey("research_tasks.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ReportReviewRecord(Base):
    __tablename__ = "report_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id: Mapped[str] = mapped_column(ForeignKey("research_tasks.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="comment", index=True)
    comment: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ProductCandidateRecord(Base):
    __tablename__ = "product_candidates"
    __table_args__ = (UniqueConstraint("organization_id", "external_key", name="uq_candidate_org_external"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("research_projects.id", ondelete="SET NULL"), nullable=True, index=True)
    originating_task_id: Mapped[str | None] = mapped_column(ForeignKey("research_tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    external_key: Mapped[str] = mapped_column(String(320))
    title: Mapped[str] = mapped_column(Text)
    marketplace: Mapped[str] = mapped_column(String(8))
    source: Mapped[str] = mapped_column(String(240))
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(32), default="unverified")
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class CandidateSnapshotRecord(Base):
    __tablename__ = "candidate_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    candidate_id: Mapped[str] = mapped_column(ForeignKey("product_candidates.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(240))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ComplianceAssessmentRecord(Base):
    __tablename__ = "compliance_assessments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("research_projects.id", ondelete="SET NULL"), nullable=True, index=True)
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("product_candidates.id", ondelete="SET NULL"), nullable=True, index=True)
    marketplace: Mapped[str] = mapped_column(String(8))
    category: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(24), default="needs_human_review", index=True)
    rule_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    rules_updated_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    findings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class BusinessFeedbackRecord(Base):
    __tablename__ = "business_feedback"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("research_tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    outcome: Mapped[str] = mapped_column(String(40))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")


Index("ix_tasks_org_created", ResearchTaskRecord.organization_id, ResearchTaskRecord.created_at)
Index("ix_evidence_org_stage", EvidenceRecord.organization_id, EvidenceRecord.stage)


class PersistenceStore:
    """Small synchronous repository; instantiate only when DATABASE_URL is set."""

    def __init__(self, database_url: str) -> None:
        options: dict[str, Any] = {"pool_pre_ping": True}
        if database_url.startswith("sqlite"):
            options["connect_args"] = {"check_same_thread": False}
        elif database_url.startswith(("mysql://", "mysql+")):
            options.update(pool_recycle=1800, pool_size=5, max_overflow=10)
            options["connect_args"] = {"connect_timeout": 5, "charset": "utf8mb4"}
        self.engine = create_engine(database_url, **options)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        from scr.infrastructure.schema_migrations import migrate
        self.schema_version = migrate(self.engine)

    @contextmanager
    def session(self) -> Iterator[Any]:
        db = self.sessions()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def ping(self) -> None:
        with self.engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")

    def create_account(self, email: str, display_name: str, password_hash: str, organization_name: str) -> dict[str, str]:
        with self.session() as db:
            return self._create_account(db, email, display_name, password_hash, organization_name)

    def create_initial_account(self, email: str, display_name: str, password_hash: str, organization_name: str) -> dict[str, str]:
        with self.session() as db:
            db.add(BootstrapClaimRecord(claim_name="initial_workspace"))
            try:
                db.flush()
            except IntegrityError as exc:
                raise PermissionError("工作区已初始化，请联系管理员添加成员。") from exc
            if db.scalar(select(func.count()).select_from(UserRecord)):
                raise PermissionError("工作区已初始化，请联系管理员添加成员。")
            return self._create_account(db, email, display_name, password_hash, organization_name)

    @staticmethod
    def _create_account(db: Any, email: str, display_name: str, password_hash: str, organization_name: str) -> dict[str, str]:
        normalized = email.strip().casefold()
        if db.scalar(select(UserRecord).where(UserRecord.email == normalized)):
            raise ValueError("该邮箱已注册。")
        organization = OrganizationRecord(name=organization_name.strip()[:160] or f"{display_name.strip()[:80]} 的工作区")
        user = UserRecord(email=normalized, display_name=display_name.strip()[:120], password_hash=password_hash)
        db.add_all([organization, user])
        db.flush()
        db.add(MembershipRecord(organization_id=organization.id, user_id=user.id, role="owner"))
        return {"user_id": user.id, "organization_id": organization.id, "role": "owner", "email": normalized, "display_name": user.display_name}

    def find_user(self, email: str) -> dict[str, Any] | None:
        with self.session() as db:
            user = db.scalar(select(UserRecord).where(UserRecord.email == email.strip().casefold()))
            if not user or not user.active:
                return None
            membership = db.scalar(select(MembershipRecord).where(MembershipRecord.user_id == user.id).order_by(MembershipRecord.created_at))
            if not membership:
                return None
            return {"user_id": user.id, "organization_id": membership.organization_id, "role": membership.role,
                    "email": user.email, "display_name": user.display_name, "password_hash": user.password_hash,
                    "token_version": user.token_version}

    def account_count(self) -> int:
        with self.session() as db:
            return int(db.scalar(select(func.count()).select_from(UserRecord)) or 0)

    def member_role(self, user_id: str, organization_id: str) -> str | None:
        with self.session() as db:
            membership = db.scalar(select(MembershipRecord).join(UserRecord, UserRecord.id == MembershipRecord.user_id)
                                    .where(MembershipRecord.user_id == user_id, MembershipRecord.organization_id == organization_id,
                                           UserRecord.active.is_(True)))
            return membership.role if membership else None

    def session_version(self, user_id: str) -> int | None:
        with self.session() as db:
            user = db.get(UserRecord, user_id)
            return user.token_version if user and user.active else None

    def disable_member(self, organization_id: str, user_id: str) -> bool:
        with self.session() as db:
            membership = db.scalar(select(MembershipRecord).where(
                MembershipRecord.organization_id == organization_id, MembershipRecord.user_id == user_id))
            user = db.get(UserRecord, user_id)
            if not membership or not user:
                return False
            db.delete(membership)
            user.token_version += 1
            if not db.scalar(select(MembershipRecord.id).where(MembershipRecord.user_id == user_id).limit(1)):
                user.active = False
            return True

    def rotate_sessions(self, user_id: str) -> bool:
        with self.session() as db:
            user = db.get(UserRecord, user_id)
            if not user or not user.active:
                return False
            user.token_version += 1
            return True

    def create_project(self, organization_id: str, user_id: str | None, name: str, description: str = "") -> dict[str, Any]:
        with self.session() as db:
            row = ResearchProjectRecord(organization_id=organization_id, created_by=user_id,
                                        name=name.strip()[:160], description=description.strip()[:4000])
            db.add(row)
            db.flush()
            return {"project_id": row.id, "name": row.name, "description": row.description,
                    "archived": row.archived, "created_at": row.created_at.isoformat()}

    def list_projects(self, organization_id: str, include_archived: bool = False) -> list[dict[str, Any]]:
        with self.session() as db:
            query = select(ResearchProjectRecord).where(ResearchProjectRecord.organization_id == organization_id)
            if not include_archived:
                query = query.where(ResearchProjectRecord.archived.is_(False))
            rows = db.scalars(query.order_by(ResearchProjectRecord.created_at.desc())).all()
            return [{"project_id": row.id, "name": row.name, "description": row.description,
                     "archived": row.archived, "created_at": row.created_at.isoformat()} for row in rows]

    def archive_project(self, organization_id: str, project_id: str) -> bool:
        with self.session() as db:
            row = db.scalar(select(ResearchProjectRecord).where(
                ResearchProjectRecord.id == project_id, ResearchProjectRecord.organization_id == organization_id))
            if not row:
                return False
            row.archived = True
            return True

    def add_member(self, organization_id: str, email: str, display_name: str, password_hash: str, role: str) -> dict[str, str]:
        with self.session() as db:
            user = db.scalar(select(UserRecord).where(UserRecord.email == email.strip().casefold()))
            if user:
                if db.scalar(select(MembershipRecord).where(MembershipRecord.organization_id == organization_id, MembershipRecord.user_id == user.id)):
                    raise ValueError("该用户已在当前工作区。")
            else:
                user = UserRecord(email=email.strip().casefold(), display_name=display_name.strip()[:120], password_hash=password_hash)
                db.add(user)
                db.flush()
            membership = MembershipRecord(organization_id=organization_id, user_id=user.id, role=role)
            db.add(membership)
            return {"user_id": user.id, "email": user.email, "display_name": user.display_name, "role": role}

    def list_members(self, organization_id: str) -> list[dict[str, str]]:
        with self.session() as db:
            rows = db.execute(select(UserRecord, MembershipRecord).join(MembershipRecord, MembershipRecord.user_id == UserRecord.id)
                              .where(MembershipRecord.organization_id == organization_id).order_by(UserRecord.created_at)).all()
            return [{"user_id": user.id, "email": user.email, "display_name": user.display_name, "role": membership.role}
                    for user, membership in rows]

    def create_task(self, actor: dict[str, Any] | None, message: str, marketplace: str, intent: str | None,
                    params: dict[str, Any] | None = None, project_id: str | None = None) -> str:
        row = ResearchTaskRecord(organization_id=(actor or {}).get("organization_id"), user_id=(actor or {}).get("user_id"),
                                 project_id=project_id, message=message, marketplace=marketplace, intent=intent, params=params or {}, status="queued")
        with self.session() as db:
            db.add(row)
            db.flush()
            task_id = row.id
        self.audit(actor, "research.task.created", task_id)
        return task_id

    def validate_project(self, organization_id: str, project_id: str | None) -> bool:
        if project_id is None:
            return True
        with self.session() as db:
            return db.scalar(select(ResearchProjectRecord.id).where(
                ResearchProjectRecord.id == project_id, ResearchProjectRecord.organization_id == organization_id,
                ResearchProjectRecord.archived.is_(False))) is not None

    def validate_candidate(self, organization_id: str, candidate_id: str | None) -> bool:
        if candidate_id is None:
            return True
        with self.session() as db:
            return db.scalar(select(ProductCandidateRecord.id).where(
                ProductCandidateRecord.id == candidate_id,
                ProductCandidateRecord.organization_id == organization_id)) is not None

    def update_task(self, task_id: str, organization_id: str | None, *, status: str | None = None,
                    progress: dict[str, Any] | None = None, result: dict[str, Any] | None = None,
                    error: str | None = None) -> None:
        with self.session() as db:
            row = db.get(ResearchTaskRecord, task_id)
            if not row or row.organization_id != organization_id:
                return
            if status is not None:
                row.status = status
            if progress is not None:
                row.progress = progress
            if result is not None:
                row.result = result
            if error is not None:
                row.error = error

    def cancel_task(self, task_id: str, organization_id: str | None) -> bool:
        with self.session() as db:
            row = db.scalar(select(ResearchTaskRecord).where(
                ResearchTaskRecord.id == task_id, ResearchTaskRecord.organization_id == organization_id))
            if not row or row.status not in {"queued", "running"}:
                return False
            row.status = "cancelled"
            row.progress = {**(row.progress or {}), "stage": "cancelled"}
            return True

    def claim_task(self, task_id: str, organization_id: str | None, stale_after_seconds: int = 120) -> bool:
        """Atomically claim a queued task, or reclaim a task whose worker lease expired."""
        cutoff = now_utc() - timedelta(seconds=max(1, stale_after_seconds))
        with self.session() as db:
            result = db.execute(update(ResearchTaskRecord).where(
                ResearchTaskRecord.id == task_id,
                ResearchTaskRecord.organization_id == organization_id,
                (ResearchTaskRecord.status == "queued") |
                ((ResearchTaskRecord.status == "running") & (ResearchTaskRecord.updated_at < cutoff)),
            ).values(status="running", progress={"stage": "starting"}, updated_at=now_utc()))
            return result.rowcount == 1

    def requeue_task(self, task_id: str, organization_id: str | None) -> bool:
        """Reset a failed task for a bounded automatic retry."""
        with self.session() as db:
            row = db.scalar(select(ResearchTaskRecord).where(
                ResearchTaskRecord.id == task_id,
                ResearchTaskRecord.organization_id == organization_id,
                ResearchTaskRecord.status == "failed",
            ))
            if not row:
                return False
            row.status = "queued"
            row.error = None
            row.progress = {**(row.progress or {}), "stage": "retry_queued"}
            row.updated_at = now_utc()
            return True

    def heartbeat_task(self, task_id: str, organization_id: str | None) -> bool:
        with self.session() as db:
            row = db.scalar(select(ResearchTaskRecord).where(
                ResearchTaskRecord.id == task_id,
                ResearchTaskRecord.organization_id == organization_id,
                ResearchTaskRecord.status == "running",
            ))
            if not row:
                return False
            row.updated_at = now_utc()
            return True

    def recoverable_tasks(self, stale_after_seconds: int = 120) -> list[dict[str, Any]]:
        """Return queued and expired running tasks without stealing active worker leases."""
        cutoff = now_utc() - timedelta(seconds=max(1, stale_after_seconds))
        with self.session() as db:
            rows = db.scalars(select(ResearchTaskRecord).where(
                (ResearchTaskRecord.status == "queued") |
                ((ResearchTaskRecord.status == "running") & (ResearchTaskRecord.updated_at < cutoff))
            ).order_by(ResearchTaskRecord.created_at)).all()
            recovered = []
            for row in rows:
                if row.status == "running":
                    row.status = "queued"
                    row.progress = {**(row.progress or {}), "stage": "recovered_after_restart"}
                recovered.append({"task_id": row.id, "organization_id": row.organization_id,
                    "user_id": row.user_id, "message": row.message, "marketplace": row.marketplace,
                    "intent": row.intent, "params": row.params or {}, "project_id": row.project_id})
            return recovered

    def get_task(self, task_id: str, organization_id: str | None) -> dict[str, Any] | None:
        with self.session() as db:
            row = db.scalar(select(ResearchTaskRecord).where(ResearchTaskRecord.id == task_id,
                                                             ResearchTaskRecord.organization_id == organization_id))
            return self._task_dict(row) if row else None

    def list_tasks(self, organization_id: str | None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        with self.session() as db:
            rows = db.scalars(select(ResearchTaskRecord).where(ResearchTaskRecord.organization_id == organization_id)
                              .order_by(ResearchTaskRecord.created_at.desc()).offset(offset).limit(limit)).all()
            return [self._task_dict(row, include_result=False) for row in rows]

    def set_favorite(self, task_id: str, organization_id: str | None, favorite: bool) -> bool:
        with self.session() as db:
            row = db.scalar(select(ResearchTaskRecord).where(ResearchTaskRecord.id == task_id,
                                                             ResearchTaskRecord.organization_id == organization_id))
            if not row:
                return False
            row.favorite = favorite
            return True

    def save_evidence(self, task_id: str, organization_id: str | None, result: dict[str, Any]) -> None:
        intent = result.get("intent") or {}
        marketplace = str(result.get("marketplace") or intent.get("marketplace") or "US")
        stages = result.get("stages") or {}
        with self.session() as db:
            existing_version = db.scalar(select(func.max(ReportVersionRecord.version)).where(ReportVersionRecord.task_id == task_id)) or 0
            report = result.get("report_markdown") or result.get("answer") or ""
            if report:
                db.add(ReportVersionRecord(task_id=task_id, organization_id=organization_id,
                                           version=int(existing_version) + 1, content=str(report),
                                           created_by=result.get("created_by")))
            for stage, output in stages.items():
                data = (output or {}).get("data") or {}
                evidence = data.get("evidence") or []
                rows = []
                for field in ("competitors", "suppliers", "raw_products"):
                    rows.extend(item for item in data.get(field, []) if isinstance(item, dict))
                db.add(EvidenceRecord(
                    task_id=task_id, organization_id=organization_id, stage=stage,
                    source=str(data.get("source") or "未知来源")[:240], marketplace=str(data.get("marketplace") or marketplace),
                    captured_at=str(data.get("data_timestamp") or now_utc().isoformat()),
                    expires_at=data.get("expires_at"), raw_url=data.get("source_url"),
                    evidence={"claims": evidence, "items": rows[:100]},
                ))

    def list_report_versions(self, task_id: str, organization_id: str) -> list[dict[str, Any]]:
        with self.session() as db:
            rows = db.scalars(select(ReportVersionRecord).where(
                ReportVersionRecord.task_id == task_id, ReportVersionRecord.organization_id == organization_id
            ).order_by(ReportVersionRecord.version)).all()
            return [{"version_id": row.id, "version": row.version, "content": row.content,
                     "created_at": row.created_at.isoformat()} for row in rows]

    def add_report_review(self, task_id: str, organization_id: str, user_id: str | None,
                          status: str, comment: str) -> dict[str, Any]:
        with self.session() as db:
            if not db.scalar(select(ResearchTaskRecord.id).where(
                ResearchTaskRecord.id == task_id, ResearchTaskRecord.organization_id == organization_id)):
                raise ValueError("任务不存在或不属于当前工作区。")
            row = ReportReviewRecord(task_id=task_id, organization_id=organization_id, user_id=user_id,
                                     status=status, comment=comment.strip()[:4000])
            db.add(row)
            db.flush()
            return {"review_id": row.id, "task_id": task_id, "status": row.status,
                    "comment": row.comment, "created_at": row.created_at.isoformat()}

    def list_report_reviews(self, task_id: str, organization_id: str) -> list[dict[str, Any]]:
        with self.session() as db:
            rows = db.scalars(select(ReportReviewRecord).where(
                ReportReviewRecord.task_id == task_id, ReportReviewRecord.organization_id == organization_id
            ).order_by(ReportReviewRecord.created_at)).all()
            return [{"review_id": row.id, "user_id": row.user_id, "status": row.status,
                     "comment": row.comment, "created_at": row.created_at.isoformat()} for row in rows]

    def save_candidate(self, actor: dict[str, Any] | None, external_key: str, title: str,
                       marketplace: str, source: str, source_url: str | None,
                       data: dict[str, Any], project_id: str | None = None,
                       task_id: str | None = None) -> dict[str, Any]:
        organization_id = (actor or {}).get("organization_id")
        user_id = (actor or {}).get("user_id")
        with self.session() as db:
            query = select(ProductCandidateRecord).where(ProductCandidateRecord.organization_id == organization_id,
                                                         ProductCandidateRecord.external_key == external_key[:320])
            row = db.scalar(query)
            if row:
                row.title, row.source_url, row.data = title[:1000], source_url, data
                row.originating_task_id = task_id or row.originating_task_id
                row.project_id = project_id or row.project_id
            else:
                row = ProductCandidateRecord(organization_id=organization_id, created_by=user_id,
                    external_key=external_key[:320], title=title[:1000], marketplace=marketplace,
                    source=source[:240], source_url=source_url, data=data, project_id=project_id,
                    originating_task_id=task_id, verification_status="unverified")
                db.add(row)
                db.flush()
            db.add(CandidateSnapshotRecord(candidate_id=row.id, organization_id=organization_id,
                                           source=source[:240], data=data))
            db.flush()
            return {"candidate_id": row.id, "title": row.title, "marketplace": row.marketplace,
                    "source": row.source, "source_url": row.source_url,
                    "verification_status": row.verification_status, "data": row.data}

    def list_candidates(self, organization_id: str, project_id: str | None = None) -> list[dict[str, Any]]:
        with self.session() as db:
            query = select(ProductCandidateRecord).where(ProductCandidateRecord.organization_id == organization_id)
            if project_id:
                query = query.where(ProductCandidateRecord.project_id == project_id)
            rows = db.scalars(query.order_by(ProductCandidateRecord.created_at.desc())).all()
            return [{"candidate_id": row.id, "title": row.title, "marketplace": row.marketplace,
                     "source": row.source, "source_url": row.source_url,
                     "verification_status": row.verification_status, "data": row.data,
                     "created_at": row.created_at.isoformat()} for row in rows]

    def add_compliance_assessment(self, actor: dict[str, Any] | None, marketplace: str, category: str,
                                  rule_source: str | None, rules_updated_at: str | None,
                                  findings: dict[str, Any], project_id: str | None = None,
                                  candidate_id: str | None = None) -> dict[str, Any]:
        row = ComplianceAssessmentRecord(organization_id=(actor or {}).get("organization_id"),
            project_id=project_id, candidate_id=candidate_id, marketplace=marketplace, category=category[:160],
            rule_source=rule_source, rules_updated_at=rules_updated_at, findings=findings,
            reviewed_by=None, status="needs_human_review")
        with self.session() as db:
            db.add(row)
            db.flush()
            return {"assessment_id": row.id, "marketplace": row.marketplace, "category": row.category,
                    "status": row.status, "rule_source": row.rule_source,
                    "rules_updated_at": row.rules_updated_at, "findings": row.findings}

    def add_business_feedback(self, actor: dict[str, Any] | None, outcome: str,
                              task_id: str | None, metrics: dict[str, Any], notes: str = "") -> dict[str, Any]:
        row = BusinessFeedbackRecord(organization_id=(actor or {}).get("organization_id"),
            task_id=task_id, user_id=(actor or {}).get("user_id"), outcome=outcome[:40],
            metrics=metrics, notes=notes.strip()[:4000])
        with self.session() as db:
            db.add(row)
            db.flush()
            return {"feedback_id": row.id, "outcome": row.outcome, "observed_at": row.observed_at.isoformat()}

    def audit(self, actor: dict[str, Any] | None, action: str, target_id: str | None = None,
              details: dict[str, Any] | None = None) -> None:
        with self.session() as db:
            db.add(AuditRecord(organization_id=(actor or {}).get("organization_id"), user_id=(actor or {}).get("user_id"),
                               action=action[:80], target_id=target_id, details=details or {}))

    @staticmethod
    def _task_dict(row: ResearchTaskRecord, include_result: bool = True) -> dict[str, Any]:
        result = {"task_id": row.id, "organization_id": row.organization_id, "user_id": row.user_id,
                  "project_id": row.project_id,
                  "message": row.message, "marketplace": row.marketplace, "intent": row.intent, "status": row.status,
                  "progress": row.progress or {}, "error": row.error, "favorite": row.favorite,
                  "created_at": row.created_at.isoformat() if row.created_at else None,
                  "updated_at": row.updated_at.isoformat() if row.updated_at else None}
        if include_result:
            result["result"] = row.result
            result["params"] = row.params or {}
        return result
