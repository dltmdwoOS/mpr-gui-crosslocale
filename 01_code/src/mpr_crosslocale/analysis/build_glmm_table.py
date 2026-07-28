from __future__ import annotations

import argparse
import csv
import io
import itertools
import json
import math
import subprocess
import zipfile
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, TextIO


LANGUAGES = ("en", "zh", "fr", "ru", "ja", "th")
DIMENSIONS = ("wf", "wi", "au", "ap", "ael", "rel")
LABELS = frozenset(("A", "B", "C", "D"))
EXPECTED_PAIRS = frozenset(itertools.product(LANGUAGES, LANGUAGES))

OUTPUT_COLUMNS = (
    "input_id",
    "parallel_id",
    "model_id",
    "model_revision",
    "code_commit",
    "question_language",
    "gui_language",
    "dimension",
    "matched",
    "generation_correct",
    "scoring_correct",
    "scoring_correct_token_tiebreak",
    "gold_label",
    "parsed_generated_label",
    "scored_predicted_label",
    "scored_predicted_label_token_tiebreak",
    "top_label_tie_count",
    "gold_is_top_tied",
    "parse_success",
    "gold_probability",
    "gold_vs_best_wrong_margin",
    "entropy",
    "num_images",
    "visual_token_count",
)

CONFIG_FIELDS = (
    "run_id",
    "code_commit",
    "model_id",
    "model_revision",
    "processor_revision",
    "precision",
    "attn_implementation",
    "vision_token_limit",
    "prompt_profile",
    "prompt_template_version",
    "system_prompt_mode",
    "processor_profile",
    "input_size",
    "min_num",
    "max_num",
    "use_thumbnail",
    "use_flash_attn",
)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)

    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    raise ValueError(f"Cannot interpret as boolean: {value!r}")


def _iter_jsonl(handle: TextIO, source_name: str) -> Iterator[dict[str, Any]]:
    for line_number, line in enumerate(handle, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON at {source_name}:{line_number}: {exc}"
            ) from exc
        if not isinstance(row, dict):
            raise ValueError(f"Expected a JSON object at {source_name}:{line_number}")
        yield row


def _read_git_object(revision: str, path: Path) -> bytes:
    try:
        repository_root = Path(
            subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ).stdout.strip()
        ).resolve()
        absolute_path = path.resolve()
        try:
            repository_path = absolute_path.relative_to(repository_root).as_posix()
        except ValueError as exc:
            raise ValueError(
                f"Git-backed input must be inside the repository: {absolute_path}"
            ) from exc
        object_name = f"{revision}:{repository_path}"
        return subprocess.run(
            ["git", "show", object_name],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        stderr = getattr(exc, "stderr", "")
        detail = (
            stderr.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes)
            else str(stderr)
        ).strip()
        raise ValueError(f"Could not read Git object for {path}: {detail}") from exc


@contextmanager
def _open_binary(path: Path, git_revision: str | None) -> Iterator[io.BufferedIOBase]:
    if git_revision is None:
        with path.open("rb") as handle:
            yield handle
        return

    # This also lets analysis proceed without restoring intentionally deleted
    # large result archives into the working tree.
    yield io.BytesIO(_read_git_object(git_revision, path))


def _select_zip_member(archive: zipfile.ZipFile, zip_member: str | None) -> str:
    jsonl_members = [
        name
        for name in archive.namelist()
        if name.lower().endswith(".jsonl") and not name.endswith("/")
    ]
    if zip_member is None:
        if len(jsonl_members) != 1:
            raise ValueError(
                "ZIP contains zero or multiple JSONL files; specify --zip-member. "
                f"Candidates: {jsonl_members}"
            )
        return jsonl_members[0]
    if zip_member not in archive.namelist():
        raise ValueError(f"ZIP member not found: {zip_member}")
    return zip_member


@contextmanager
def open_rows(
    path: Path,
    zip_member: str | None = None,
    git_revision: str | None = None,
) -> Iterator[Iterable[dict[str, Any]]]:
    """Open JSONL rows from a file/ZIP or from the same path in a Git revision."""
    with _open_binary(path, git_revision) as binary:
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(binary) as archive:
                member = _select_zip_member(archive, zip_member)
                with archive.open(member) as member_binary:
                    text = io.TextIOWrapper(member_binary, encoding="utf-8")
                    yield _iter_jsonl(text, f"{path}:{member}")
            return

        text = io.TextIOWrapper(binary, encoding="utf-8")
        yield _iter_jsonl(text, str(path))


def _validate_label(value: Any, field: str, input_id: str, *, nullable: bool) -> str | None:
    if value is None and nullable:
        return None
    label = str(value)
    if label not in LABELS:
        raise ValueError(f"Invalid {field} for {input_id}: {value!r}")
    return label


def _token_tiebreak_label(
    row: dict[str, Any],
    scored_label: str,
    input_id: str,
) -> tuple[str, int, bool]:
    logprobs = row.get("label_logprobs")
    token_ids = row.get("label_token_ids")
    if not isinstance(logprobs, dict) or not isinstance(token_ids, dict):
        return scored_label, 1, False
    if any(label not in logprobs or label not in token_ids for label in LABELS):
        raise ValueError(f"Incomplete label scores/token IDs for {input_id}")

    values = {label: float(logprobs[label]) for label in LABELS}
    maximum = max(values.values())
    tied = [
        label
        for label in LABELS
        if math.isclose(values[label], maximum, rel_tol=0.0, abs_tol=1e-12)
    ]
    single_token_ids: dict[str, int] = {}
    for label in tied:
        ids = token_ids[label]
        if not isinstance(ids, list) or len(ids) != 1:
            return scored_label, len(tied), str(row.get("gold_label")) in tied
        single_token_ids[label] = int(ids[0])
    # torch.argmax over the full vocabulary resolves an exact tie to the
    # smallest vocabulary index.
    selected = min(tied, key=single_token_ids.__getitem__)
    return selected, len(tied), str(row.get("gold_label")) in tied


def build_table(
    raw_rows: Iterable[dict[str, Any]],
    expected_items: int | None = 2195,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output_rows: list[dict[str, Any]] = []
    seen_input_ids: set[str] = set()
    rows_by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    config_values: dict[str, set[str]] = defaultdict(set)
    status_counts: Counter[str] = Counter()
    raw_count = 0
    parse_failures = 0
    generated_scoring_disagreements = 0
    stored_disagreement_mismatches = 0
    stored_scoring_mismatches = 0
    top_label_ties = 0
    token_tiebreak_generation_disagreements = 0

    for row in raw_rows:
        raw_count += 1
        status = str(row.get("status") or row.get("inference_status") or "")
        status_counts[status] += 1
        if status != "success":
            # A complete 36-cell table must not be silently formed by dropping
            # failed attempts.
            continue

        input_id = str(row["input_id"])
        if input_id in seen_input_ids:
            raise ValueError(f"Duplicate successful input_id: {input_id}")
        seen_input_ids.add(input_id)

        parallel_id = str(row.get("parallel_id") or row["semantic_item_id"])
        question_language = str(row["question_language"])
        gui_language = str(row["gui_language"])
        dimension = str(row["dimension"])
        if question_language not in LANGUAGES:
            raise ValueError(f"Unexpected question language: {question_language}")
        if gui_language not in LANGUAGES:
            raise ValueError(f"Unexpected GUI language: {gui_language}")
        if dimension not in DIMENSIONS:
            raise ValueError(f"Unexpected dimension: {dimension}")

        matched = question_language == gui_language
        if _as_bool(row["matched"]) != matched:
            raise ValueError(
                f"Inconsistent matched field for {input_id}: "
                f"question={question_language}, gui={gui_language}"
            )

        gold_label = _validate_label(row.get("gold_label"), "gold_label", input_id, nullable=False)
        generated_label = _validate_label(
            row.get("parsed_generated_label"),
            "parsed_generated_label",
            input_id,
            nullable=True,
        )
        scored_label = _validate_label(
            row.get("scored_predicted_label"),
            "scored_predicted_label",
            input_id,
            nullable=False,
        )
        generation_correct = int(generated_label == gold_label)
        scoring_correct = int(scored_label == gold_label)
        token_tiebreak_label, tie_count, gold_is_top_tied = _token_tiebreak_label(
            row, scored_label, input_id
        )
        scoring_correct_token_tiebreak = int(token_tiebreak_label == gold_label)
        derived_disagreement = generated_label is not None and generated_label != scored_label
        token_tiebreak_disagreement = (
            generated_label is not None and generated_label != token_tiebreak_label
        )
        top_label_ties += int(tie_count > 1)
        token_tiebreak_generation_disagreements += int(token_tiebreak_disagreement)

        parse_success = _as_bool(row.get("parse_success", generated_label is not None))
        if parse_success != (generated_label is not None):
            raise ValueError(f"parse_success disagrees with parsed label for {input_id}")
        parse_failures += int(not parse_success)
        generated_scoring_disagreements += int(derived_disagreement)

        if "generation_scoring_disagreement" in row:
            stored_disagreement_mismatches += int(
                _as_bool(row["generation_scoring_disagreement"]) != derived_disagreement
            )
        if "correct" in row:
            stored_scoring_mismatches += int(_as_bool(row["correct"]) != bool(scoring_correct))

        for field in CONFIG_FIELDS:
            if row.get(field) is not None:
                config_values[field].add(str(row[field]))

        output_row = {
            "input_id": input_id,
            "parallel_id": parallel_id,
            "model_id": row.get("model_id"),
            "model_revision": row.get("model_revision"),
            "code_commit": row.get("code_commit"),
            "question_language": question_language,
            "gui_language": gui_language,
            "dimension": dimension,
            "matched": int(matched),
            "generation_correct": generation_correct,
            "scoring_correct": scoring_correct,
            "scoring_correct_token_tiebreak": scoring_correct_token_tiebreak,
            "gold_label": gold_label,
            "parsed_generated_label": generated_label,
            "scored_predicted_label": scored_label,
            "scored_predicted_label_token_tiebreak": token_tiebreak_label,
            "top_label_tie_count": tie_count,
            "gold_is_top_tied": int(gold_is_top_tied),
            "parse_success": int(parse_success),
            "gold_probability": row.get("gold_probability"),
            "gold_vs_best_wrong_margin": row.get("gold_vs_best_wrong_margin"),
            "entropy": row.get("entropy"),
            "num_images": row.get("num_images"),
            "visual_token_count": row.get("visual_token_count"),
        }
        output_rows.append(output_row)
        rows_by_item[parallel_id].append(output_row)

    if not output_rows:
        raise ValueError("No successful inference rows found")
    failed_count = raw_count - len(output_rows)
    if failed_count:
        raise ValueError(
            f"Found {failed_count} non-success rows; status counts={dict(status_counts)}"
        )

    for parallel_id, item_rows in rows_by_item.items():
        observed_pairs = {
            (row["question_language"], row["gui_language"]) for row in item_rows
        }
        dimensions = {row["dimension"] for row in item_rows}
        if len(item_rows) != 36 or observed_pairs != EXPECTED_PAIRS:
            missing = sorted(EXPECTED_PAIRS - observed_pairs)
            raise ValueError(
                f"{parallel_id} has an invalid 6x6 grid: "
                f"rows={len(item_rows)}, missing={missing}"
            )
        if len(dimensions) != 1:
            raise ValueError(f"{parallel_id} maps to multiple dimensions: {dimensions}")

    item_count = len(rows_by_item)
    if expected_items is not None and item_count != expected_items:
        raise ValueError(f"Expected {expected_items} items, found {item_count}")

    pair_counts = Counter(
        (row["question_language"], row["gui_language"]) for row in output_rows
    )
    if any(count != item_count for count in pair_counts.values()):
        raise ValueError("Language cells have unequal sample counts")

    dimension_item_counts = Counter(
        item_rows[0]["dimension"] for item_rows in rows_by_item.values()
    )
    summary = {
        "raw_rows": raw_count,
        "status_counts": dict(sorted(status_counts.items())),
        "analysis_rows": len(output_rows),
        "semantic_items": item_count,
        "expected_rows": item_count * 36,
        "dimension_item_counts": dict(sorted(dimension_item_counts.items())),
        "parse_failures": parse_failures,
        "generation_scoring_disagreements": generated_scoring_disagreements,
        "generation_scoring_disagreement_rate": (
            generated_scoring_disagreements / len(output_rows)
        ),
        "top_label_ties": top_label_ties,
        "top_label_tie_rate": top_label_ties / len(output_rows),
        "generation_token_tiebreak_disagreements": (
            token_tiebreak_generation_disagreements
        ),
        "generation_token_tiebreak_disagreement_rate": (
            token_tiebreak_generation_disagreements / len(output_rows)
        ),
        "stored_disagreement_mismatches": stored_disagreement_mismatches,
        "stored_correct_vs_scoring_mismatches": stored_scoring_mismatches,
        "configuration_values": {
            field: sorted(values) for field, values in sorted(config_values.items())
        },
    }
    return output_rows, summary


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build and strictly validate the 6x6 GLMM analysis table."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--zip-member")
    parser.add_argument(
        "--git-revision",
        help="Read --input from this Git revision (for example HEAD) instead of disk.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validation-out", type=Path, required=True)
    parser.add_argument("--expected-items", type=int, default=2195)
    args = parser.parse_args()

    with open_rows(args.input, args.zip_member, args.git_revision) as raw_rows:
        table, validation = build_table(raw_rows, args.expected_items)

    write_csv(table, args.output)
    args.validation_out.parent.mkdir(parents=True, exist_ok=True)
    args.validation_out.write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(validation, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
