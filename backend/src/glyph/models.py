from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    source_path: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    processed_content_hash: Mapped[str | None] = mapped_column(String(64))
    file_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="discovered"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    jobs: Mapped[list[ProcessingJob]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    pages: Mapped[list[Page]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    blocks: Mapped[list[Block]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    sections: Mapped[list[Section]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    summaries: Mapped[list[Summary]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    research_map_versions: Mapped[list[ResearchMapVersion]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    research_map_jobs: Mapped[list[ResearchMapJob]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    document: Mapped[Document] = relationship(back_populates="jobs")


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    image_path: Mapped[str | None] = mapped_column(String(2048))
    raw_text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    document: Mapped[Document] = relationship(back_populates="pages")


class Section(Base):
    __tablename__ = "sections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    path: Mapped[str] = mapped_column(String(2048), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("sections.id"))
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")

    document: Mapped[Document] = relationship(
        back_populates="sections", foreign_keys=[document_id]
    )


class Block(Base):
    __tablename__ = "blocks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), nullable=False)
    source_content_hash: Mapped[str | None] = mapped_column(String(64))
    section_id: Mapped[str | None] = mapped_column(ForeignKey("sections.id"))
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    block_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    translated_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    formula_latex: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    document: Mapped[Document] = relationship(back_populates="blocks")
    research_evidence: Mapped[list[ResearchEvidence]] = relationship(
        back_populates="block"
    )


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), nullable=False)
    section_id: Mapped[str | None] = mapped_column(ForeignKey("sections.id"))
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    document: Mapped[Document] = relationship(back_populates="summaries")


class ResearchMapVersion(Base):
    __tablename__ = "research_map_versions"
    __table_args__ = (
        Index("ix_research_map_versions_document_id", "document_id"),
        Index(
            "uq_research_map_active_document",
            "document_id",
            unique=True,
            sqlite_where=text("is_active = 1"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), nullable=False)
    previous_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("research_map_versions.id")
    )
    source_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document: Mapped[Document] = relationship(back_populates="research_map_versions")
    previous_version: Mapped[ResearchMapVersion | None] = relationship(remote_side=[id])
    nodes: Mapped[list[ResearchNode]] = relationship(
        back_populates="map_version", cascade="all, delete-orphan"
    )
    issues: Mapped[list[ResearchMapIssue]] = relationship(
        back_populates="map_version", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[ResearchMapJob]] = relationship(back_populates="map_version")
    reviews: Mapped[list[ResearchNodeReview]] = relationship(
        back_populates="based_on_map_version"
    )


class ResearchNode(Base):
    __tablename__ = "research_nodes"
    __table_args__ = (
        UniqueConstraint("map_version_id", "node_key"),
        Index("ix_research_nodes_map_version_order", "map_version_id", "display_order"),
        Index("ix_research_nodes_signature", "node_signature"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    map_version_id: Mapped[str] = mapped_column(
        ForeignKey("research_map_versions.id"), nullable=False
    )
    parent_node_id: Mapped[str | None] = mapped_column(ForeignKey("research_nodes.id"))
    node_key: Mapped[str] = mapped_column(String(128), nullable=False)
    node_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    provenance: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_quality: Mapped[str] = mapped_column(String(32), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    node_signature: Mapped[str] = mapped_column(String(64), nullable=False)

    map_version: Mapped[ResearchMapVersion] = relationship(back_populates="nodes")
    parent: Mapped[ResearchNode | None] = relationship(
        back_populates="children", remote_side=[id]
    )
    children: Mapped[list[ResearchNode]] = relationship(back_populates="parent")
    evidence: Mapped[list[ResearchEvidence]] = relationship(
        back_populates="node", cascade="all, delete-orphan"
    )
    reviews: Mapped[list[ResearchNodeReview]] = relationship(
        back_populates="node", cascade="all, delete-orphan"
    )
    issues: Mapped[list[ResearchMapIssue]] = relationship(back_populates="node")


class ResearchEvidence(Base):
    __tablename__ = "research_evidence"
    __table_args__ = (
        UniqueConstraint("node_id", "block_id", "quote_start", "quote_end", "relation"),
        Index("ix_research_evidence_node_id", "node_id"),
        Index("ix_research_evidence_block_id", "block_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    node_id: Mapped[str] = mapped_column(
        ForeignKey("research_nodes.id"), nullable=False
    )
    block_id: Mapped[str] = mapped_column(ForeignKey("blocks.id"), nullable=False)
    locator_type: Mapped[str] = mapped_column(String(32), nullable=False)
    quote_text: Mapped[str] = mapped_column(Text, nullable=False)
    quote_start: Mapped[int] = mapped_column(Integer, nullable=False)
    quote_end: Mapped[int] = mapped_column(Integer, nullable=False)
    source_quote_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    relation: Mapped[str] = mapped_column(String(32), nullable=False)
    source_label: Mapped[str | None] = mapped_column(String(512))

    node: Mapped[ResearchNode] = relationship(back_populates="evidence")
    block: Mapped[Block] = relationship(back_populates="research_evidence")


class ResearchNodeReview(Base):
    __tablename__ = "research_node_reviews"
    __table_args__ = (
        UniqueConstraint("node_id", "revision_number"),
        Index("ix_research_node_reviews_node_time", "node_id", "reviewed_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    node_id: Mapped[str] = mapped_column(
        ForeignKey("research_nodes.id"), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    supersedes_review_id: Mapped[str | None] = mapped_column(
        ForeignKey("research_node_reviews.id")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    corrected_claim_text: Mapped[str | None] = mapped_column(Text)
    review_note: Mapped[str | None] = mapped_column(Text)
    based_on_map_version_id: Mapped[str] = mapped_column(
        ForeignKey("research_map_versions.id"), nullable=False
    )
    based_on_node_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    node: Mapped[ResearchNode] = relationship(
        back_populates="reviews", foreign_keys=[node_id]
    )
    based_on_map_version: Mapped[ResearchMapVersion] = relationship(
        back_populates="reviews", foreign_keys=[based_on_map_version_id]
    )
    supersedes_review: Mapped[ResearchNodeReview | None] = relationship(
        remote_side=[id], foreign_keys=[supersedes_review_id]
    )


class ResearchMapIssue(Base):
    __tablename__ = "research_map_issues"
    __table_args__ = (Index("ix_research_map_issues_version_id", "map_version_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    map_version_id: Mapped[str] = mapped_column(
        ForeignKey("research_map_versions.id"), nullable=False
    )
    node_id: Mapped[str | None] = mapped_column(ForeignKey("research_nodes.id"))
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    map_version: Mapped[ResearchMapVersion] = relationship(back_populates="issues")
    node: Mapped[ResearchNode | None] = relationship(back_populates="issues")


class ResearchMapJob(Base):
    __tablename__ = "research_map_jobs"
    __table_args__ = (
        Index("ix_research_map_jobs_document_status", "document_id", "status"),
        Index(
            "uq_research_map_active_job",
            "document_id",
            unique=True,
            sqlite_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), nullable=False)
    map_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("research_map_versions.id")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    document: Mapped[Document] = relationship(back_populates="research_map_jobs")
    map_version: Mapped[ResearchMapVersion | None] = relationship(back_populates="jobs")
