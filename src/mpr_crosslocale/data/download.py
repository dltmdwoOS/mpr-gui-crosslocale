from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download


DEFAULT_HF_REPO = "chenruihan/MPR-GUI-Bench"
DEFAULT_GITHUB_REPO = "https://github.com/chenruihan32/MPR-GUI-Bench.git"


def load_source_lock(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def download_hf_images(repo_id: str, images_dir: Path, revision: str | None) -> dict[str, object]:
    api = HfApi()
    info = api.dataset_info(repo_id, revision=revision, files_metadata=True)
    images_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = images_dir.parent / ".images-download"
    staging_dir.mkdir(parents=True, exist_ok=True)

    try:
        snapshot_download(
            repo_id=repo_id,
            repo_type="dataset",
            revision=revision,
            local_dir=staging_dir,
            max_workers=4,
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
    except Exception:
        print(f"Image download interrupted; partial files were left in {staging_dir}")
        raise

    if images_dir.exists():
        shutil.rmtree(images_dir)
    shutil.move(str(staging_dir), str(images_dir))
    return {
        "repo_id": repo_id,
        "requested_revision": revision,
        "sha": info.sha,
        "siblings": len(info.siblings),
    }


def download_github_qas(repo_url: str, qas_dir: Path, ref: str | None) -> dict[str, object]:
    qas_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mpr-gui-qas-") as tmp:
        clone_dir = Path(tmp) / "repo"
        subprocess.run(
            ["git", "clone", "--filter=blob:none", "--sparse", repo_url, str(clone_dir)],
            check=True,
        )
        if ref:
            subprocess.run(["git", "checkout", ref], cwd=clone_dir, check=True)
        subprocess.run(["git", "sparse-checkout", "set", "qas"], cwd=clone_dir, check=True)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=clone_dir, text=True).strip()
        source_qas = clone_dir / "qas"
        if qas_dir.exists():
            shutil.rmtree(qas_dir)
        shutil.copytree(source_qas, qas_dir)
    return {
        "repo_url": repo_url,
        "requested_ref": ref,
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
    parser.add_argument("--hf-revision", default=None)
    parser.add_argument("--github-repo", default=DEFAULT_GITHUB_REPO)
    parser.add_argument("--github-ref", default=None)
    parser.add_argument("--source-lock", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.source_lock:
        lock = load_source_lock(args.source_lock)
        args.hf_repo = lock.get("huggingface", {}).get("repo_id", args.hf_repo)
        args.hf_revision = lock.get("huggingface", {}).get("sha", args.hf_revision)
        args.github_repo = lock.get("github", {}).get("repo_url", args.github_repo)
        args.github_ref = lock.get("github", {}).get("commit", args.github_ref)

    args.root.mkdir(parents=True, exist_ok=True)
    hf_meta = download_hf_images(args.hf_repo, args.root / "images", args.hf_revision)
    github_meta = download_github_qas(args.github_repo, args.root / "qas", args.github_ref)
    source_path = write_source_metadata(args.root, hf_meta, github_meta)
    print(f"Downloaded MPR-GUI-Bench into {args.root}")
    print(f"Wrote source metadata to {source_path}")


if __name__ == "__main__":
    main()
