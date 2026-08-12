from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import select

from glyph.config import Settings, get_settings
from glyph.contract_ai import create_implementation_contract_provider
from glyph.contract_export import (
    ExportFormat,
    ExportLanguage,
    export_implementation_contract,
)
from glyph.contract_schemas import ImplementationContractOut
from glyph.database import create_session_factory
from glyph.implementation_contracts import (
    ImplementationContractConflictError,
    ImplementationContractNotFoundError,
    ImplementationContractService,
    load_implementation_contract,
)
from glyph.models import Document, ImplementationContractVersion

logger = logging.getLogger(__name__)


def main(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    active_settings = settings or get_settings()
    factory = create_session_factory(active_settings)
    try:
        if arguments.command == "list":
            return _list_contracts(factory)
        if arguments.command == "show":
            return _show_contract(factory, arguments.document_id)
        if arguments.command == "generate":
            return _generate_contract(
                factory,
                active_settings,
                arguments.document_id,
                arguments.map_version,
            )
        if arguments.command == "export":
            return _export_contract(
                factory,
                arguments.version_id,
                arguments.export_format,
                arguments.language,
                arguments.output,
            )
    except (
        ImplementationContractNotFoundError,
        ImplementationContractConflictError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (OSError, TypeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    logger.error("Unknown glyph-contract command", extra={"command": arguments.command})
    print("Unknown glyph-contract command", file=sys.stderr)
    return 1


def entrypoint() -> None:
    raise SystemExit(main())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="glyph-contract")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List active Implementation Contracts")

    show = subparsers.add_parser("show", help="Show a document's active contract")
    show.add_argument("document_id")

    generate = subparsers.add_parser("generate", help="Generate a contract locally")
    generate.add_argument("document_id")
    generate.add_argument("--map-version", dest="map_version")

    export = subparsers.add_parser("export", help="Export one contract version")
    export.add_argument("version_id")
    export.add_argument(
        "--format",
        dest="export_format",
        choices=("json", "markdown"),
        required=True,
    )
    export.add_argument(
        "--language",
        choices=("en", "zh-TW", "bilingual"),
        required=True,
    )
    export.add_argument("--output", type=Path, required=True)
    return parser


def _list_contracts(factory) -> int:
    with factory() as session:
        rows = session.execute(
            select(Document.id, ImplementationContractVersion)
            .join(
                ImplementationContractVersion,
                ImplementationContractVersion.document_id == Document.id,
            )
            .where(ImplementationContractVersion.is_active.is_(True))
            .order_by(Document.id)
        ).all()
        payload = [
            {
                "document_id": document_id,
                "version_id": version.id,
                "status": version.status,
                "readiness": version.readiness,
            }
            for document_id, version in rows
        ]
    _print_json(payload)
    return 0


def _show_contract(factory, document_id: str) -> int:
    with factory() as session:
        version_id = session.scalar(
            select(ImplementationContractVersion.id).where(
                ImplementationContractVersion.document_id == document_id,
                ImplementationContractVersion.is_active.is_(True),
            )
        )
        if version_id is None:
            raise ImplementationContractNotFoundError(
                "Active Implementation Contract not found"
            )
        view = load_implementation_contract(session, version_id)
        payload = ImplementationContractOut.model_validate(view).model_dump(mode="json")
    _print_json(payload)
    return 0


def _generate_contract(
    factory,
    settings: Settings,
    document_id: str,
    map_version_id: str | None,
) -> int:
    with factory() as session:
        contract = ImplementationContractService(
            session,
            create_implementation_contract_provider(settings),
        ).generate(document_id, map_version_id)
        session.commit()
        payload = {
            "contract_version_id": contract.id,
            "document_id": contract.document_id,
            "research_map_version_id": contract.research_map_version_id,
            "status": contract.status,
            "readiness": contract.readiness,
        }
    _print_json(payload)
    return 0


def _export_contract(
    factory,
    version_id: str,
    export_format: ExportFormat,
    language: ExportLanguage,
    output: Path,
) -> int:
    with factory() as session:
        artifact = export_implementation_contract(
            session,
            version_id,
            export_format,
            language,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(artifact.content)
    _print_json({"output": str(output), "version_id": version_id})
    return 0


def _print_json(payload: object) -> None:
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
