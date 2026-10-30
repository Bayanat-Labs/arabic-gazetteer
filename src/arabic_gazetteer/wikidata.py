"""Read the Arab-World Wikidata Slice (Hugging Face dataset Bayanat-Labs/arab-world-wikidata) and
map Wikidata classes to place families."""
from __future__ import annotations

import csv
import glob
import io
import json
import os
from dataclasses import dataclass, field

from .config import FAMILY_ORDER, WD_ARABIC_LANGS, WD_FAMILY_ROOTS, WD_LATIN_LANGS, WD_NAME_PROPS

SLICE_REPO = "Bayanat-Labs/arab-world-wikidata"


@dataclass
class Item:
    qid: str
    class_group: str
    p31: list
    lat: float | None
    lon: float | None
    countries: list           # ISO2 codes of the states the item is tied to (any path)
    p17_states: list          # ISO2 codes from truthy P17 statements
    lastrevid: int | None
    n_sitelinks: int = 0
    labels: dict = field(default_factory=dict)    # lang -> label
    aliases: dict = field(default_factory=dict)   # lang -> [alias]
    names: list = field(default_factory=list)     # (property, lang, value)
    p131: list = field(default_factory=list)
    p1566: list = field(default_factory=list)
    population: int | None = None


def _files(folder: str, config: str) -> list[str]:
    files = sorted(glob.glob(os.path.join(folder, "data", config, "*.parquet")))
    if not files:
        raise FileNotFoundError(f"no parquet files for config {config!r} under {folder}")
    return files


def read(folder: str, qid_to_state: dict) -> dict:
    """Read entities, labels_long and triples of the slice into Items (people are skipped)."""
    import duckdb

    con = duckdb.connect()
    ent = _files(folder, "entities")
    lab = _files(folder, "labels_long")
    tri = _files(folder, "triples")
    items: dict[str, Item] = {}
    rows = con.execute(
        "select qid, class_group, p31, lat, lon, countries_iso2, lastrevid, n_sitelinks "
        "from read_parquet(?) where class_group <> 'human'", [ent]).fetchall()
    for qid, group, p31, lat, lon, cc, rev, nsl in rows:
        items[qid] = Item(qid=qid, class_group=group, p31=list(p31 or []), lat=lat, lon=lon,
                          countries=list(cc or []), p17_states=[], lastrevid=rev, n_sitelinks=nsl or 0)
    langs = WD_ARABIC_LANGS + WD_LATIN_LANGS
    rows = con.execute(
        "select qid, lang, kind, value from read_parquet(?) where kind in ('label', 'alias') "
        "and lang in (select unnest(?)) order by qid, lang, kind, value", [lab, langs]).fetchall()
    for qid, lang, kind, value in rows:
        it = items.get(qid)
        if it is None:
            continue
        if kind == "label":
            it.labels[lang] = value
        else:
            it.aliases.setdefault(lang, []).append(value)
    props = ["P17", "P131", "P1566", "P1082"] + list(WD_NAME_PROPS)
    rows = con.execute(
        "select qid, pid, value_qid, value_string, value_lang, value_amount, value_time "
        "from read_parquet(?) where truthy and pid in (select unnest(?)) "
        "order by qid, pid, value_time nulls first, value_qid, value_string", [tri, props]).fetchall()
    pops: dict[str, list] = {}
    for qid, pid, vq, vs, vl, va, vt in rows:
        it = items.get(qid)
        if it is None:
            continue
        if pid == "P17":
            if vq in qid_to_state and qid_to_state[vq] not in it.p17_states:
                it.p17_states.append(qid_to_state[vq])
        elif pid == "P131":
            if vq and vq not in it.p131:
                it.p131.append(vq)
        elif pid == "P1566":
            if vs and vs.strip().isdigit() and int(vs) not in it.p1566:
                it.p1566.append(int(vs))
        elif pid == "P1082":
            try:
                pops.setdefault(qid, []).append((vt or "", float(va)))
            except (TypeError, ValueError):
                pass
        elif pid in WD_NAME_PROPS and vs and vl in langs:
            it.names.append((pid, vl, vs))
    for qid, vals in pops.items():
        # the value with the latest point in time, or the largest when no time is given
        vals.sort(key=lambda x: (x[0], x[1]))
        items[qid].population = int(vals[-1][1])
    return items


def read_slice_meta(folder: str) -> dict:
    path = os.path.join(folder, "meta", "dump.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def _sha256(path: str) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


READ_CONFIGS = ("entities", "labels_long", "triples")


def verify_slice(folder: str) -> dict:
    """Check the slice files that the build reads against the SHA256SUMS file shipped with the
    slice. Raises ValueError when a file is missing from SHA256SUMS or its SHA-256 differs.
    Returns the number of files checked and the SHA-256 of the slice's MANIFEST.json (None when
    the folder has no SHA256SUMS, as in the test fixtures)."""
    sums_path = os.path.join(folder, "SHA256SUMS")
    if not os.path.exists(sums_path):
        return {"sha256sums_checked": False, "files_checked": 0, "manifest_sha256": None}
    sums = {}
    with open(sums_path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                digest, rel = line.rstrip("\n").split(None, 1)
                sums[rel.lstrip("*")] = digest
    n = 0
    for cfg in READ_CONFIGS:
        for f in _files(folder, cfg):
            rel = os.path.relpath(f, folder).replace(os.sep, "/")
            if rel not in sums:
                raise ValueError(f"{rel} is not listed in the slice's SHA256SUMS")
            if _sha256(f) != sums[rel]:
                raise ValueError(f"{rel}: SHA-256 differs from the slice's SHA256SUMS")
            n += 1
    man = os.path.join(folder, "MANIFEST.json")
    return {"sha256sums_checked": True, "files_checked": n,
            "manifest_sha256": _sha256(man) if os.path.exists(man) else None}


# --- class families -------------------------------------------------------------------------

def load_p279(folder: str) -> dict:
    """class QID -> list of P279 parents, from jsonl.zst files with rows {"id", "p279"}."""
    import zstandard

    parents: dict[str, list] = {}
    for path in sorted(glob.glob(os.path.join(folder, "classes_*.jsonl.zst"))):
        with open(path, "rb") as fh:
            reader = io.TextIOWrapper(zstandard.ZstdDecompressor().stream_reader(fh), encoding="utf-8")
            for line in reader:
                if line.strip():
                    row = json.loads(line)
                    parents[row["id"]] = row.get("p279") or []
    return parents


def class_families(parents: dict, classes) -> dict:
    """For each class, the family whose root it reaches in the fewest P279 steps, with the step
    count: {class: (family, steps, root)}. Classes that reach no root get ('-', None, None)."""
    roots = {}
    for fam, rs in WD_FAMILY_ROOTS:
        for r in rs:
            roots[r] = fam
    rank = {f: i for i, f in enumerate(FAMILY_ORDER)}
    out = {}
    for c in classes:
        best = None
        seen = {c: 0}
        frontier = [c]
        depth = 0
        while frontier and depth <= 12:
            for x in frontier:
                if x in roots:
                    cand = (depth, rank[roots[x]], roots[x], x)
                    if best is None or cand < best:
                        best = cand
            if best is not None and best[0] <= depth:
                break
            nxt = []
            for x in frontier:
                for p in parents.get(x, ()):
                    if p not in seen:
                        seen[p] = depth + 1
                        nxt.append(p)
            frontier = nxt
            depth += 1
        out[c] = (best[2], best[0], best[3]) if best else ("-", None, None)
    return out


def write_class_map(path: str, families: dict) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["class_qid", "family", "steps", "root_qid"])
        for c in sorted(families, key=lambda q: int(q[1:]) if q[1:].isdigit() else 0):
            fam, steps, root = families[c]
            w.writerow([c, fam, "" if steps is None else steps, root or ""])


def read_class_map(path: str) -> dict:
    out = {}
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            out[row["class_qid"]] = (row["family"], int(row["steps"]) if row["steps"] else None,
                                     row["root_qid"] or None)
    return out


def item_family(item: Item, class_map: dict) -> str:
    """Family of an item: the closest family over its P31 classes (ties: X first, then the
    family order). '-' when no class reaches a root."""
    rank = {f: i for i, f in enumerate(FAMILY_ORDER)}
    best = None
    for c in item.p31:
        fam, steps, _ = class_map.get(c, ("-", None, None))
        if fam == "-" or steps is None:
            continue
        cand = (steps, rank[fam], fam)
        if best is None or cand < best:
            best = cand
    return best[2] if best else "-"
