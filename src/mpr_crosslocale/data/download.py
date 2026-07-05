from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download


DEFAULT_HF_REPO = "chenruihan/MPR-GUI-Bench"
DEFAULT_GITHUB_REPO = "https://github.com/chenruihan32/MPR-GUI-Bench.git"


def download_hf_images(repo_id: str, images_dir: Path) -> dict[str, object]:
    images_dir.mkdir(parents=True, exist_ok=True)
    api = HfApi()
    info = api.dataset_info(repo_id, files_metadata=True)
    snapshot_download(
        repo_id=repo_id,
        repo_type="dataset",
        local_dir=images_dir,
        allow_patterns=[
            "1/**",
            "2/**",
            "3/**",
            "4/**",
            "5/**",
            "6/**",
            "rich/**",
            "sparse/**",
            "README.md",
            ".gitattributes",
        ],
    )
    return {
        "repo_id": repo_id,
        "sha": info.sha,
        "siblings": len(info.siblings),
    }


def download_github_qas(repo_url: str, qas_dir: Path) -> dict[str, object]:
    qas_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mpr-gui-qas-") as tmp:
        clone_dir = Path(tmp) / "repo"
        subprocess.run(
            ["git", "clone", "--filter=blob:none", "--sparse", repo_url, str(clone_dir)],
            check=True,
        )
        subprocess.run(["git", "sparse-checkout", "set", "qas"], cwd=clone_dir, check=True)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=clone_dir, text=True).strip()
        source_qas = clone_dir / "qas"
        if qas_dir.exists():
            shutil.rmtree(qas_dir)
        shutil.copytree(source_qas, qas_dir)
    return {
        "repo_url": repo_url,
        "commit": commit,
        "jsonl_files": len(list(qas_dir.glob("*.jsonl"))),
    }


def write_source_metadata(root: Path, hf_meta: dict[str, object], github_meta: dict[str, object]) -> Path:
    metadata = {
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "layout": {
            "root": root.as_posix(),
            "images_dir": (root / "images").as_posix(),
            "qas_dir": (root / "qas").as_posix(),
        },
        "huggingface": hf_meta,
        "github": github_meta,
    }
    out = root / "SOURCE.json"
    out.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Download and normalize MPR-GUI-Bench assets.")
    parser.add_argument("--root", type=Path, default=Path("data/raw/mpr_gui_bench"))
    parser.add_argument("--hf-repo", default=DEFAULT_HF_REPO)
    parser.add_argument("--github-repo", default=DEFAULT_GITHUB_REPO)
    args = parser.parse_args(argv)

    args.root.mkdir(parents=True, exist_ok=True)
    hf_meta = download_hf_images(args.hf_repo, args.root / "images")
    github_meta = download_github_qas(args.github_repo, args.root / "qas")
    source_path = write_source_metadata(args.root, hf_meta, github_meta)
    print(f"Downloaded MPR-GUI-Bench into {args.root}")
    print(f"Wrote source metadata to {source_path}")


if __name__ == "__main__":
    main()
