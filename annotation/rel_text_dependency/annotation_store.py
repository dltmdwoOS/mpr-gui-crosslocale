from __future__ import annotations

import csv
import io
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


VALID_LABELS = {"dependent", "independent"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AnnotationStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS annotations (
                    annotator_id TEXT NOT NULL,
                    parallel_id TEXT NOT NULL,
                    display_order INTEGER NOT NULL,
                    label TEXT,
                    review_flag INTEGER NOT NULL DEFAULT 0,
                    note TEXT NOT NULL DEFAULT '',
                    current_locale TEXT NOT NULL DEFAULT 'en',
                    annotation_seconds REAL NOT NULL DEFAULT 0,
                    guideline_version TEXT NOT NULL,
                    manifest_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (annotator_id, parallel_id)
                );
                CREATE TABLE IF NOT EXISTS annotation_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    annotator_id TEXT NOT NULL,
                    parallel_id TEXT NOT NULL,
                    label TEXT,
                    review_flag INTEGER NOT NULL,
                    note TEXT NOT NULL,
                    current_locale TEXT NOT NULL,
                    annotation_seconds REAL NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                """
            )

    def upsert(
        self,
        *,
        annotator_id: str,
        parallel_id: str,
        display_order: int,
        label: str | None,
        review_flag: bool,
        note: str,
        current_locale: str,
        annotation_seconds: float,
        guideline_version: str,
        manifest_sha256: str,
    ) -> dict[str, object]:
        annotator_id = annotator_id.strip()
        if not annotator_id or len(annotator_id) > 80:
            raise ValueError("annotator_id must contain 1–80 characters")
        if label is not None and label not in VALID_LABELS:
            raise ValueError(f"invalid label: {label}")
        if current_locale not in {"en", "zh", "fr", "ru", "ja", "th"}:
            raise ValueError(f"invalid locale: {current_locale}")
        note = note.strip()[:2000]
        now = utc_now()
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT created_at FROM annotations WHERE annotator_id=? AND parallel_id=?",
                (annotator_id, parallel_id),
            ).fetchone()
            created_at = existing["created_at"] if existing else now
            values = (
                annotator_id,
                parallel_id,
                int(display_order),
                label,
                int(bool(review_flag)),
                note,
                current_locale,
                max(0.0, float(annotation_seconds)),
                guideline_version,
                manifest_sha256,
                created_at,
                now,
            )
            connection.execute(
                """
                INSERT INTO annotations (
                    annotator_id, parallel_id, display_order, label, review_flag,
                    note, current_locale, annotation_seconds, guideline_version,
                    manifest_sha256, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(annotator_id, parallel_id) DO UPDATE SET
                    display_order=excluded.display_order,
                    label=excluded.label,
                    review_flag=excluded.review_flag,
                    note=excluded.note,
                    current_locale=excluded.current_locale,
                    annotation_seconds=annotations.annotation_seconds + excluded.annotation_seconds,
                    guideline_version=excluded.guideline_version,
                    manifest_sha256=excluded.manifest_sha256,
                    updated_at=excluded.updated_at
                """,
                values,
            )
            connection.execute(
                """
                INSERT INTO annotation_events (
                    annotator_id, parallel_id, label, review_flag, note,
                    current_locale, annotation_seconds, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    annotator_id,
                    parallel_id,
                    label,
                    int(bool(review_flag)),
                    note,
                    current_locale,
                    max(0.0, float(annotation_seconds)),
                    now,
                ),
            )
        return self.get(annotator_id, parallel_id) or {}

    def get(self, annotator_id: str, parallel_id: str) -> dict[str, object] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM annotations WHERE annotator_id=? AND parallel_id=?",
                (annotator_id, parallel_id),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def all_for(self, annotator_id: str) -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM annotations WHERE annotator_id=? ORDER BY display_order",
                (annotator_id,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def progress(self, annotator_id: str, total_items: int) -> dict[str, int]:
        rows = self.all_for(annotator_id)
        labeled = sum(row["label"] in VALID_LABELS for row in rows)
        review = sum(bool(row["review_flag"]) for row in rows)
        dependent = sum(row["label"] == "dependent" for row in rows)
        independent = sum(row["label"] == "independent" for row in rows)
        return {
            "total": total_items,
            "labeled": labeled,
            "remaining": max(0, total_items - labeled),
            "review": review,
            "dependent": dependent,
            "independent": independent,
        }

    def export_csv(self, annotator_id: str) -> str:
        rows = self.all_for(annotator_id)
        fields = [
            "parallel_id",
            "annotator_id",
            "display_order",
            "text_dependency",
            "review_flag",
            "note",
            "current_locale",
            "annotation_seconds",
            "guideline_version",
            "manifest_sha256",
            "created_at",
            "updated_at",
        ]
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "parallel_id": row["parallel_id"],
                    "annotator_id": row["annotator_id"],
                    "display_order": row["display_order"],
                    "text_dependency": row["label"] or "",
                    "review_flag": int(bool(row["review_flag"])),
                    "note": row["note"],
                    "current_locale": row["current_locale"],
                    "annotation_seconds": f"{float(row['annotation_seconds']):.3f}",
                    "guideline_version": row["guideline_version"],
                    "manifest_sha256": row["manifest_sha256"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        return buffer.getvalue()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, object]:
        result = dict(row)
        result["review_flag"] = bool(result["review_flag"])
        return result
