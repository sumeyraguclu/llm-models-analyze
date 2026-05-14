from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from database import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, index=True)
    file_name = Column(String(255), nullable=False)
    table_name = Column(String(128), nullable=False, unique=True, index=True)
    column_defs = Column(JSON, nullable=False, default=list)
    column_profile = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    ai_models = relationship("AIModel", back_populates="dataset", cascade="all, delete-orphan")
    plan_snapshots = relationship("PlanSnapshot", back_populates="dataset", cascade="all, delete-orphan")
    analysis_jobs = relationship("AnalysisJob", back_populates="dataset", cascade="all, delete-orphan")


class PlanSnapshot(Base):
    """Onay akışı için immutable analysis_plan anlık görüntüsü."""

    __tablename__ = "plan_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    payload_json = Column(JSON, nullable=False)
    mapping_confidence_json = Column(JSON, nullable=True)
    warnings_json = Column(JSON, nullable=False, default=list)
    status = Column(String(32), nullable=False, default="draft", index=True)
    source = Column(String(32), nullable=False, default="llm")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    dataset = relationship("Dataset", back_populates="plan_snapshots")
    analysis_jobs = relationship("AnalysisJob", back_populates="plan_snapshot", cascade="all, delete-orphan")


class AIModel(Base):
    __tablename__ = "ai_models"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    template = Column(String(64), nullable=False)
    column_map = Column(JSON, nullable=False, default=dict)
    metrics = Column(JSON, nullable=True)
    status = Column(String(32), nullable=False, default="pending")
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    dataset = relationship("Dataset", back_populates="ai_models")


class AnalysisJob(Base):
    """Arka planda çalışan analyze işi (onaylı plan + dataset)."""

    __tablename__ = "analysis_jobs"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_snapshot_id = Column(Integer, ForeignKey("plan_snapshots.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="queued", index=True)
    progress = Column(Integer, nullable=False, default=0)
    result_model_run_id = Column(Integer, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True, index=True)
    result_summary = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    dataset = relationship("Dataset", back_populates="analysis_jobs")
    plan_snapshot = relationship("PlanSnapshot", back_populates="analysis_jobs")
    result_model = relationship("AIModel", foreign_keys=[result_model_run_id])
