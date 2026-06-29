"""
SynapseForge — Master Data Seeder from Backup

Creates or synchronizes master data directly from the canonical backup
stored in backend/db/backup/synapse-backup-v2-260526.

The script parses INSERT INTO public.<table> statements for the following tables:
- workspaces
- llm_configs
- tools
- agents
- orchestrations
- pipeline_artifacts

It then upserts those records into MongoDB while masking any
secret-bearing fields before persistence.

Usage:
    python -m setup.seed_master_data_from_backup
    python -m setup.seed_master_data_from_backup --backup ./db/backup/synapse-backup-v2-260526
    python -m setup.seed_master_data_from_backup --reset
"""

from __future__ import annotations

import argparse
import asyncio
import ast
import json
import logging
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

_backend_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_backend_dir))

from dotenv import load_dotenv

load_dotenv(dotenv_path=_backend_dir / ".env")

from db.engine import get_database, init_db, normalize_mongo_document, prepare_document, reset_db
from db.models import (
    Agent,
    ArchitectureType,
    LLMConfig,
    LLMProviderEnum,
    MCPServerStatus,
    MCPTransportType,
    Orchestration,
    OrchestrationFramework,
    PipelineArtifact,
    Tool,
    ToolType,
    Workspace,
    WorkspaceStatus,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("seed_master_data_from_backup")

DEFAULT_BACKUP_PATH = _backend_dir / "db" / "backup" / "synapse-backup-v2-260526"
TARGET_TABLES = ("workspaces", "llm_configs", "tools", "agents", "orchestrations", "pipeline_artifacts")
SECRET_KEY_PATTERN = re.compile(r"(api[_-]?key|token|secret|password|credential)", re.IGNORECASE)
# NOTE: re.DOTALL is required so that '.' in (?P<values>.*) crosses embedded newlines
# inside SQL string literals (multi-line system prompts, etc.).
# The ;\Z anchor matches the literal semicolon at the very end of the statement string.
INSERT_PATTERN = re.compile(
    r"INSERT INTO public\.(?P<table>workspaces|llm_configs|tools|agents|orchestrations|pipeline_artifacts)\s*"
    r"\((?P<columns>.*?)\)\s*VALUES\s*\((?P<values>.*)\);\Z",
    re.DOTALL,
)


def _split_sql_csv(text: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    in_string = False
    depth_curly = 0
    depth_square = 0
    i = 0

    while i < len(text):
        ch = text[i]

        if ch == "'" and (i + 1) < len(text) and text[i + 1] == "'":
            current.append("''")
            i += 2
            continue

        if ch == "'":
            in_string = not in_string
            current.append(ch)
            i += 1
            continue

        if not in_string:
            if ch == "{":
                depth_curly += 1
            elif ch == "}":
                depth_curly = max(0, depth_curly - 1)
            elif ch == "[":
                depth_square += 1
            elif ch == "]":
                depth_square = max(0, depth_square - 1)
            elif ch == "," and depth_curly == 0 and depth_square == 0:
                items.append("".join(current).strip())
                current = []
                i += 1
                continue

        current.append(ch)
        i += 1

    if current:
        items.append("".join(current).strip())

    return items


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def _parse_pg_array(value: str) -> list[Any]:
    inner = value[1:-1]
    if not inner:
        return []

    parts = _split_sql_csv(inner)
    parsed: list[Any] = []
    for part in parts:
        raw = part.strip()
        if not raw or raw.upper() == "NULL":
            parsed.append(None)
            continue
        cleaned = _strip_quotes(raw)
        if re.fullmatch(r"[0-9a-fA-F-]{36}", cleaned):
            parsed.append(str(uuid.UUID(cleaned)))
        else:
            parsed.append(cleaned)
    return parsed


def _parse_scalar(value: str) -> Any:
    token = value.strip()

    if token.upper() == "NULL":
        return None
    if token.lower() == "true":
        return True
    if token.lower() == "false":
        return False
    if token.startswith("'") and token.endswith("'"):
        inner = _strip_quotes(token)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?\+00", inner):
            return datetime.fromisoformat(inner.replace(" ", "T"))
        if re.fullmatch(r"[0-9a-fA-F-]{36}", inner):
            return str(uuid.UUID(inner))
        if inner.startswith("[") or inner == "null":
            try:
                return json.loads(inner)
            except json.JSONDecodeError:
                return inner
        if inner.startswith("{") and inner.endswith("}") and ":" in inner:
            try:
                return json.loads(inner)
            except json.JSONDecodeError:
                return inner
        if inner.startswith("{") and inner.endswith("}"):
            return _parse_pg_array(inner)
        return inner
    if token.startswith("{") and token.endswith("}"):
        return _parse_pg_array(token)
    try:
        return ast.literal_eval(token)
    except Exception:
        return token


def _mask_secret_value(key: str, value: Any) -> Any:
    if value is None:
        return None
    if SECRET_KEY_PATTERN.search(key):
        return "***"
    return value


def _sanitize_structure(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _sanitize_structure(_mask_secret_value(k, v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_structure(item) for item in value]
    return value


def _parse_insert_line(line: str) -> tuple[str, dict[str, Any]] | None:
    # Use search() so that leading SQL comment lines (-- ...) before the INSERT
    # keyword are ignored.  DOTALL on the pattern means this correctly handles
    # multi-line statements with embedded newlines.
    match = INSERT_PATTERN.search(line)
    if not match:
        return None

    table = match.group("table")
    columns = [part.strip() for part in _split_sql_csv(match.group("columns"))]
    raw_values = _split_sql_csv(match.group("values"))
    values = [_parse_scalar(raw) for raw in raw_values]

    row = dict(zip(columns, values, strict=True))

    if "credentials" in row:
        row["credentials"] = _sanitize_structure(row["credentials"])
    if "env" in row:
        row["env"] = _sanitize_structure(row["env"])
    if "connection_config" in row:
        row["connection_config"] = _sanitize_structure(row["connection_config"])
    if "config" in row:
        row["config"] = _sanitize_structure(row["config"])

    return table, row


def _extract_sql_statements(text: str) -> list[str]:
    """
    Extract complete SQL statements from a pg_dump file.

    A statement ends at a semicolon that is NOT inside a single-quoted string
    literal.  This handles system prompts and JSON config values that contain
    embedded newlines and semicolons.
    """
    statements: list[str] = []
    current: list[str] = []
    in_string = False
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]

        # Handle escaped single-quote inside a string literal ('').
        if in_string and ch == "'" and i + 1 < n and text[i + 1] == "'":
            current.append("''")
            i += 2
            continue

        if ch == "'":
            in_string = not in_string
            current.append(ch)
            i += 1
            continue

        if not in_string and ch == ";":
            current.append(ch)
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
            continue

        current.append(ch)
        i += 1

    # Trailing content without a semicolon
    remainder = "".join(current).strip()
    if remainder:
        statements.append(remainder)

    return statements


def _load_backup_rows(backup_path: Path) -> dict[str, list[dict[str, Any]]]:
    data: dict[str, list[dict[str, Any]]] = {table: [] for table in TARGET_TABLES}

    raw = backup_path.read_text(encoding="utf-8")
    for stmt in _extract_sql_statements(raw):
        parsed = _parse_insert_line(stmt)
        if not parsed:
            continue
        table, row = parsed
        data[table].append(row)

    return data


def _enum_or_none(enum_cls: type, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, enum_cls):
        return value
    normalized = str(value)
    for candidate in (normalized, normalized.lower(), normalized.upper()):
        try:
            return enum_cls(candidate)
        except ValueError:
            continue
    for member in enum_cls.__members__.values():
        if member.name == normalized.upper():
            return member
    raise ValueError(f"{value!r} is not a valid {enum_cls.__name__}")


def _workspace_from_row(row: dict[str, Any]) -> Workspace:
    return Workspace(
        id=row["id"],
        name=row["name"],
        description=row.get("description"),
        embedding_model=row["embedding_model"],
        embedding_dim=row["embedding_dim"],
        is_default=row["is_default"],
        status=_enum_or_none(WorkspaceStatus, row["status"]),
        shared_with=row.get("shared_with"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        created_by=row.get("created_by"),
        updated_by=row.get("updated_by"),
    )


def _llm_config_from_row(row: dict[str, Any]) -> LLMConfig:
    return LLMConfig(
        id=row["id"],
        workspace_id=row["workspace_id"],
        name=row["name"],
        provider=_enum_or_none(LLMProviderEnum, row["provider"]),
        model_name=row["model_name"],
        credentials=row.get("credentials"),
        temperature=row["temperature"],
        max_tokens=row["max_tokens"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        created_by=row.get("created_by"),
        updated_by=row.get("updated_by"),
    )


def _tool_from_row(row: dict[str, Any]) -> Tool:
    return Tool(
        id=row["id"],
        workspace_id=row["workspace_id"],
        name=row["name"],
        description=row.get("description"),
        type=_enum_or_none(ToolType, row["type"]),
        is_enabled=row["is_enabled"],
        connection_config=row.get("connection_config"),
        schema_def=row.get("schema"),
        transport=_enum_or_none(MCPTransportType, row.get("transport")),
        command=row.get("command"),
        args=row.get("args"),
        env=row.get("env"),
        url=row.get("url"),
        status=_enum_or_none(MCPServerStatus, row["status"]),
        last_error=row.get("last_error"),
        parent_id=row.get("parent_id"),
        category=row.get("category"),
        sub_category=row.get("sub_category"),
        tags=row.get("tags"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        created_by=row.get("created_by"),
        updated_by=row.get("updated_by"),
    )


def _agent_from_row(row: dict[str, Any]) -> Agent:
    return Agent(
        id=row["id"],
        workspace_id=row["workspace_id"],
        name=row["name"],
        description=row.get("description"),
        system_prompt=row.get("system_prompt"),
        llm_config_id=row.get("llm_config_id"),
        use_neural_router=row["use_neural_router"],
        router_model_id=row.get("router_model_id"),
        router_top_k=row.get("router_top_k"),
        memory_type=row.get("memory_type"),
        memory_window=row.get("memory_window"),
        max_iterations=row.get("max_iterations"),
        timeout_seconds=row.get("timeout_seconds"),
        attached_tool_ids=row.get("attached_tool_ids"),
        collaborator_agent_ids=row.get("collaborator_agent_ids"),
        category=row.get("category"),
        sub_category=row.get("sub_category"),
        tags=row.get("tags"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        created_by=row.get("created_by"),
        updated_by=row.get("updated_by"),
    )


def _orchestration_from_row(row: dict[str, Any]) -> Orchestration:
    return Orchestration(
        id=row["id"],
        workspace_id=row["workspace_id"],
        name=row["name"],
        framework=_enum_or_none(OrchestrationFramework, row["framework"]),
        architecture_type=_enum_or_none(ArchitectureType, row["architecture_type"]),
        config=row.get("config"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        created_by=row.get("created_by"),
        updated_by=row.get("updated_by"),
    )


def _pipeline_artifact_from_row(row: dict[str, Any]) -> PipelineArtifact:
    return PipelineArtifact(
        id=row["id"],
        workspace_id=row["workspace_id"],
        phase=row["phase"],
        artifact_type=row["artifact_type"],
        name=row["name"],
        cos_bucket=row["cos_bucket"],
        cos_key=row["cos_key"],
        cos_endpoint=row["cos_endpoint"],
        url=row.get("url"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        created_by=row.get("created_by"),
        updated_by=row.get("updated_by"),
    )


async def _upsert_document(collection_name: str, document_id: str, payload: dict[str, Any]) -> None:
    db = get_database()
    await db[collection_name].replace_one(
        {"_id": document_id},
        prepare_document(payload),
        upsert=True,
    )


async def seed_from_backup(backup_path: Path, reset: bool = False) -> None:
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    await init_db()

    parsed = _load_backup_rows(backup_path)
    logger.info(
        "Loaded backup rows: %s",
        ", ".join(f"{table}={len(parsed[table])}" for table in TARGET_TABLES),
    )

    if reset:
        logger.warning("Reset requested; deleting existing master-data collections before reseeding.")
        await reset_db()

    for row in parsed["workspaces"]:
        workspace = _workspace_from_row(row)
        await _upsert_document("workspaces", workspace.id, workspace.model_dump())

    for row in parsed["llm_configs"]:
        llm_config = _llm_config_from_row(row)
        await _upsert_document("llm_configs", llm_config.id, llm_config.model_dump())

    tool_rows = parsed["tools"]
    parent_tool_rows = [row for row in tool_rows if row.get("parent_id") is None]
    child_tool_rows = [row for row in tool_rows if row.get("parent_id") is not None]

    for row in parent_tool_rows:
        tool = _tool_from_row(row)
        await _upsert_document("tools", tool.id, tool.model_dump())

    child_tool_rows.sort(key=lambda row: str(row.get("parent_id")))
    for row in child_tool_rows:
        tool = _tool_from_row(row)
        await _upsert_document("tools", tool.id, tool.model_dump())

    for row in parsed["agents"]:
        agent = _agent_from_row(row)
        await _upsert_document("agents", agent.id, agent.model_dump())

    for row in parsed["orchestrations"]:
        orchestration = _orchestration_from_row(row)
        await _upsert_document("orchestrations", orchestration.id, orchestration.model_dump())

    for row in parsed["pipeline_artifacts"]:
        artifact = _pipeline_artifact_from_row(row)
        await _upsert_document("pipeline_artifacts", artifact.id, artifact.model_dump())

    logger.info("Master data sync complete from backup: %s", backup_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed SynapseForge master data from the canonical backup."
    )
    parser.add_argument(
        "--backup",
        default=str(DEFAULT_BACKUP_PATH),
        help="Path to backup file.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing target master-data rows before reseeding.",
    )
    args = parser.parse_args()
    asyncio.run(seed_from_backup(Path(args.backup), reset=args.reset))


if __name__ == "__main__":
    main()

# Made with Bob
