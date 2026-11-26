"""Repositories for Phase 7A coverage records."""

from sqlalchemy import delete, select

from app.models.coverage import CoverageFile, SymbolCoverage
from app.repositories.base import BaseRepository


class CoverageFileRepository(BaseRepository):
    def add_many(self, files: list[CoverageFile]) -> None:
        if files:
            self.session.add_all(files)
            self.session.flush()

    def replace_for_analysis(self, analysis_id: str, files: list[CoverageFile]) -> None:
        self.session.execute(
            delete(CoverageFile).where(CoverageFile.analysis_id == analysis_id)
        )
        self.add_many(files)

    def list_for_analysis(self, analysis_id: str) -> list[CoverageFile]:
        return list(
            self.session.scalars(
                select(CoverageFile)
                .where(CoverageFile.analysis_id == analysis_id)
                .order_by(CoverageFile.source_path.asc())
            ).all()
        )

    def has_any(self, analysis_id: str) -> bool:
        row = self.session.scalar(
            select(CoverageFile.id)
            .where(CoverageFile.analysis_id == analysis_id)
            .limit(1)
        )
        return row is not None


class SymbolCoverageRepository(BaseRepository):
    def add_many(self, records: list[SymbolCoverage]) -> None:
        if records:
            self.session.add_all(records)
            self.session.flush()

    def replace_for_analysis(self, analysis_id: str, records: list[SymbolCoverage]) -> None:
        self.session.execute(
            delete(SymbolCoverage).where(SymbolCoverage.analysis_id == analysis_id)
        )
        self.add_many(records)

    def list_for_analysis(self, analysis_id: str) -> list[SymbolCoverage]:
        return list(
            self.session.scalars(
                select(SymbolCoverage)
                .where(SymbolCoverage.analysis_id == analysis_id)
                .order_by(SymbolCoverage.file_path.asc(), SymbolCoverage.qualified_name.asc())
            ).all()
        )

    def status_by_symbol(self, analysis_id: str) -> dict[str, str]:
        rows = self.session.execute(
            select(SymbolCoverage.symbol_id, SymbolCoverage.status).where(
                SymbolCoverage.analysis_id == analysis_id
            )
        ).all()
        return {symbol_id: status for symbol_id, status in rows}

    def has_any(self, analysis_id: str) -> bool:
        row = self.session.scalar(
            select(SymbolCoverage.id)
            .where(SymbolCoverage.analysis_id == analysis_id)
            .limit(1)
        )
        return row is not None
