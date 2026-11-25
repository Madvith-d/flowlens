"""Contract serializers: DB rows → OpenAPI response shapes.

These functions are the single place that turns model records into
client-visible JSON so responses stay aligned with contracts/openapi.yaml.
No serializer ever includes GitHub tokens, server paths, or secrets.
"""

from app.models.projects import Project, SourceSnapshot
from app.services.github.app_client import InstallationInfo, RepositoryInfo


def pagination_view(page: int, per_page: int, total: int) -> dict:
    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": (total + per_page - 1) // per_page if per_page else 0,
    }


def installation_view(info: InstallationInfo) -> dict:
    return {
        "id": info.installation_id,
        "account_login": info.account_login,
        "account_type": info.account_type,
        "avatar_url": info.avatar_url,
    }


def repository_view(repo: RepositoryInfo) -> dict:
    return {
        "id": repo.repository_id,
        "full_name": repo.full_name,
        "owner": repo.owner,
        "visibility": repo.visibility,
        "default_branch": repo.default_branch,
        "description": repo.description,
        "html_url": f"https://github.com/{repo.full_name}" if repo.full_name else None,
    }


def snapshot_view(snapshot: SourceSnapshot) -> dict:
    github_provenance = None
    if snapshot.provider == "github":
        github_provenance = {
            "repository_id": snapshot.github_repository_id,
            "full_name": snapshot.github_full_name,
            "ref": snapshot.github_ref,
            "commit_sha": snapshot.github_commit_sha,
            "imported_at": snapshot.imported_at.isoformat() if snapshot.imported_at else None,
        }
    return {
        "id": snapshot.id,
        "project_id": snapshot.project_id,
        "provider": snapshot.provider,
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        "content_hash": snapshot.content_hash,
        "file_count": snapshot.file_count,
        "github_provenance": github_provenance,
    }


def github_connection_view(project: Project) -> dict | None:
    if project.source_provider != "github" or project.github_repository_id is None:
        return None
    if project.disconnected_at is not None:
        # Disconnected projects keep snapshots; the live connection is gone.
        return None
    return {
        "installation_id": project.github_installation_id,
        "repository_id": project.github_repository_id,
        "full_name": project.github_full_name,
        "ref": project.github_ref,
        "visibility": project.github_visibility,
        "connected_at": project.updated_at.isoformat() if project.updated_at else None,
    }


def project_view(
    project: Project,
    latest_snapshot: SourceSnapshot | None = None,
    latest_analysis: dict | None = None,
) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "source_provider": project.source_provider,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        "github_connection": github_connection_view(project),
        "latest_snapshot": snapshot_view(latest_snapshot) if latest_snapshot else None,
        "latest_analysis": latest_analysis,
    }


def analysis_view(run, diagnostics_summary: dict | None = None) -> dict:
    """AnalysisRun contract payload (state, counters, diagnostics summary)."""
    return {
        "id": run.id,
        "snapshot_id": run.snapshot_id,
        "state": run.state,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "flowlens_version": run.flowlens_version,
        "graph_schema_version": run.graph_schema_version,
        "python_file_count": run.python_file_count,
        "symbol_count": run.symbol_count,
        "edge_count": run.edge_count,
        "diagnostics_summary": diagnostics_summary or {},
        "error_code": run.error_code,
    }


def symbol_view(symbol) -> dict:
    """Symbol contract payload with snapshot-relative source locations."""
    return {
        "id": symbol.id,
        "kind": symbol.kind,
        "name": symbol.name,
        "qualified_name": symbol.qualified_name,
        "file_path": symbol.file_path,
        "location": {
            "start_line": symbol.start_line,
            "end_line": symbol.end_line,
            "start_column": symbol.start_column,
            "end_column": symbol.end_column,
        },
        "parent_id": symbol.parent_id,
    }
