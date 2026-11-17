"""Archive completed OCR runs and their frozen repository-file dependencies, not weights/images."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tarfile

REPO = Path(__file__).resolve().parents[3]
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / '01_code/src'), str(REPO), str(Path(__file__).parent)]
import run_ocr_inventory as screen
import run_ocr_remaining as full
import run_ocr_4b as four
from mpr_crosslocale.methods.selective_alignment.schemas import digest


def main():
    files = set()
    expected = {}
    roots = [(screen.DEFAULT_OUTPUT, screen.verify), (full.DEFAULT_OUTPUT, full.verify),
             (four.DEFAULT_OUTPUT, four.verify)]
    for root, verify in roots:
        c = verify(root)
        done = json.loads((root / 'COMPLETE.json').read_text())
        if c['execution_mode'] != 'gpu' or done['contract_sha256'] != digest(c):
            raise ValueError('Only completed real runs may be archived')
        for name, sha in c['source_sha256'].items():
            path = REPO / name
            if path in expected and expected[path] != sha:
                raise ValueError('Conflicting frozen source checksum')
            expected[path] = sha
            files.add(path)
        for name in ('contract.json', 'COMPLETE.json', 'results.json', 'REPORT_KO.md', 'ocr_weights.json'):
            path = root / name
            if path.exists():
                files.add(path)
        cohorts = [root] if root == screen.DEFAULT_OUTPUT else [root / x for x in c['cohorts']]
        for work in cohorts:
            for name in ('contract.json', 'COMPLETE.json', 'inputs.jsonl', 'ocr_weights.json'):
                path = work / name
                if path.exists():
                    files.add(path)
            for stage in ('ocr', 'rewrite', 'infer'):
                complete = sorted(p for p in (work / stage).glob('attempt_*') if (p / 'COMPLETE').exists())
                if not complete:
                    continue
                for path in complete[-1].rglob('*'):
                    if path.is_file():
                        files.add(path)
    files.update([Path(__file__), ROOT / 'reports/OCR_FINAL_RESULTS_KO.md',
                  ROOT / 'reports/OCR_INVENTORY_FULL_DEV_RESULTS_KO.md',
                  ROOT / 'reports/OCR_QWEN3_VL_4B_RESULTS_KO.md',
                  ROOT / 'reports/OCR_8B_4B_CHAIN_PROTOCOL_KO.md',
                  ROOT / 'artifacts/ocr_inventory_results_snapshot.json',
                  ROOT / 'artifacts/ocr_inventory_full_dev_results_snapshot.json',
                  ROOT / 'artifacts/ocr_qwen3_vl_4b_results_snapshot.json',
                  REPO / 'followup_rel_4lang/dataset_lock.json',
                  REPO / 'followup_rel_4lang/data_bundle.py'])
    entries = {}
    for path in sorted(files):
        resolved = path.resolve()
        if not resolved.is_relative_to(REPO) or 'PRIVATE' in str(path):
            raise ValueError('Private or out-of-repository file cannot enter archive')
        if path.suffix.lower() in ('.safetensors', '.pth', '.png', '.jpg', '.jpeg'):
            raise ValueError('Models/screenshots must stay outside the result archive')
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if path in expected and expected[path] != sha:
            raise ValueError('Frozen source changed before archive')
        entries[str(path.relative_to(REPO))] = {'bytes': path.stat().st_size, 'sha256': sha}
    target = ROOT / 'artifacts/ocr_completed_8b_4b.tar.gz'
    with tarfile.open(target, 'w:gz', compresslevel=6, dereference=True) as archive:
        for name in sorted(entries):
            archive.add(REPO / name, arcname=name, recursive=False)
    # Verify every archived byte against its manifest, including dereferenced caches.
    with tarfile.open(target, 'r:gz') as archive:
        if set(archive.getnames()) != set(entries):
            raise ValueError('Archive member coverage differs')
        for member in archive:
            with archive.extractfile(member) as stream:
                if hashlib.sha256(stream.read()).hexdigest() != entries[member.name]['sha256']:
                    raise ValueError('Archive member checksum differs: ' + member.name)
    manifest = {'as_of_utc': datetime.now(timezone.utc).isoformat(),
                'archive': str(target.relative_to(REPO)), 'bytes': target.stat().st_size,
                'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                'files': entries, 'uncompressed_bytes': sum(x['bytes'] for x in entries.values()),
                'scope': 'Completed Screen/remaining8B/4B OCR raw calls, transformations, predictions, '
                         'contracts, environment/cost records and frozen repository-file dependencies. '
                         'No model weights, screenshots, private evaluation-label file, mock outputs, '
                         'incomplete attempts or redundant new-run caches.',
                'restore': 'Extract from the repository root with tar -xzf followed by the archive path. '
                           'Existing paths are overwritten, so restore in a clean checkout. '
                           'Restore dataset/screenshots using dataset_lock.json and the data_bundle guide, '
                           'and keep the frozen HF revisions/environment from the contracts. '
                           'Some historical runtime contracts contain absolute paths for this lab workspace.'}
    path = ROOT / 'artifacts/ocr_completed_archive_manifest.json'
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print('ARCHIVED', len(entries), 'verified files;', target.stat().st_size, 'bytes;', manifest['sha256'])


if __name__ == '__main__':
    main()
