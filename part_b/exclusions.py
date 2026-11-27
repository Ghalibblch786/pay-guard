"""Reviewed-record exclusions (SPECS D-29, Variant A): narratives a human has already reviewed are kept out of the pilot AND the main sample.

The local file holds only SHA-256 hashes, a source tag and a date: no narrative text and no Complaint IDs. It lives under data/ (gitignored),
readable by the owner only. Loading FAILS CLOSED: a missing, empty or malformed file raises instead of meaning "exclude nothing".
Report counts only; never print hashes.
"""
import csv, datetime, hashlib, os, re, tempfile
from pathlib import Path

from part_b.run_sanitizer_aggregate import norm   # the D-17 normalization used for deduplication: one definition, not a copy

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "processed" / "exclusions" / "reviewed_hashes.csv"
HEADER = ["sha256", "source", "date"]


class ExclusionError(RuntimeError):
    """Messages must never include file contents."""


def narrative_hash(raw: str) -> str:
    """SHA-256 of the D-17 normalized RAW narrative (not the sanitized text)."""
    return hashlib.sha256(norm(raw).encode("utf-8")).hexdigest()


def _check_row(row: list) -> None:
    if len(row) != 3 or not re.fullmatch(r"[0-9a-f]{64}", row[0]) or not re.fullmatch(r"[a-z0-9_]+", row[1]):
        raise ExclusionError("exclusion data has a malformed row")
    try:
        datetime.date.fromisoformat(row[2])
    except ValueError:
        raise ExclusionError("exclusion data has a malformed date") from None


def _read_rows(path: Path) -> list:
    if not path.is_file():
        raise ExclusionError("exclusion file is missing: refusing to continue without it")
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows or rows[0] != HEADER:
        raise ExclusionError("exclusion file has a missing or wrong header")
    if len(rows) == 1:
        raise ExclusionError("exclusion file has no entries")
    for row in rows[1:]:
        _check_row(row)
    return rows[1:]


def load_exclusions(path: Path = DEFAULT_PATH) -> set:
    """Set of excluded hashes. Raises ExclusionError if the file is missing, empty or malformed."""
    return {row[0] for row in _read_rows(Path(path))}


def load_by_source(path: Path = DEFAULT_PATH) -> dict:
    """{source tag: list of hashes, one per row}. Same fail-closed rules as load_exclusions."""
    out: dict = {}
    for h, source, _ in _read_rows(Path(path)):
        out.setdefault(source, []).append(h)
    return out


def add_exclusions(hashes, source: str, day: str, path: Path = DEFAULT_PATH) -> int:
    """Append (hash, source, day) rows, skipping (hash, source) pairs already present. Returns the number added.
    Existing rows are never removed. The file is replaced atomically and is owner-only (0600, folder 0700)."""
    path = Path(path)
    rows = _read_rows(path) if path.exists() else []
    seen = {(r[0], r[1]) for r in rows}
    new = [[h, source, day] for h in sorted(set(hashes)) if (h, source) not in seen]
    if not rows and not new:
        raise ExclusionError("nothing to write")
    for row in new:
        _check_row(row)                                     # validate everything before touching disk
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")   # created 0600
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            csv.writer(f, lineterminator="\n").writerows([HEADER] + rows + new)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return len(new)


def keep_mask(texts, excluded: set) -> list:
    """True for each narrative that may be sampled, False for each reviewed one. Apply to RAW text, before any sampling."""
    return [narrative_hash(t) not in excluded for t in texts]
