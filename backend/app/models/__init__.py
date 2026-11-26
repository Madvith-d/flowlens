"""All ORM models; imported so Base.metadata covers every table."""

from app.db.base import Base
from app.models.analysis import (
    AnalysisDiagnostic,
    DependencyEdge,
    SourceFile,
    Symbol,
    SymbolCall,
)
from app.models.auth import OAuthState, UserSession
from app.models.coverage import CoverageFile, SymbolCoverage
from app.models.github import GitHubCredential, GitHubInstallation
from app.models.projects import AnalysisRun, Project, Report, SourceSnapshot
from app.models.user import User, new_object_id

__all__ = [
    "Base",
    "AnalysisDiagnostic",
    "AnalysisRun",
    "CoverageFile",
    "DependencyEdge",
    "GitHubCredential",
    "GitHubInstallation",
    "OAuthState",
    "Project",
    "Report",
    "SourceFile",
    "SourceSnapshot",
    "Symbol",
    "SymbolCall",
    "SymbolCoverage",
    "User",
    "UserSession",
    "new_object_id",
]
