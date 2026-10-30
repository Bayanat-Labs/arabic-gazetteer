"""Download and read the GeoNames dump files (https://download.geonames.org/export/dump/)."""
from __future__ import annotations

import datetime
import hashlib
import io
import json
import os
import time
import zipfile
from dataclasses import dataclass, field

from .config import GEONAMES_DUMP, GEONAMES_FILES, MIN_REQUEST_GAP_S, STATES, USER_AGENT


def fetch(out_dir: str, states=None, log=print) -> list[dict]:
    """Download the GeoNames files once each, one at a time, at most one request per second.
    Writes <file>.meta.json next to each file (Last-Modified, size, SHA-256) and returns the
    metadata rows. Files that already have a .meta.json are skipped. Stops on HTTP 403 or 429."""
    import requests

    states = list(states or STATES)
    rels = list(GEONAMES_FILES) + [f"{cc}.zip" for cc in states] + [f"alternatenames/{cc}.zip" for cc in states]
    os.makedirs(os.path.join(out_dir, "alternatenames"), exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    rows, last = [], 0.0
    for rel in rels:
        dest = os.path.join(out_dir, rel)
        if os.path.exists(dest + ".meta.json"):
            with open(dest + ".meta.json", encoding="utf-8") as fh:
                rows.append(json.load(fh))
            continue
        wait = MIN_REQUEST_GAP_S - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        url = GEONAMES_DUMP + rel
        last = time.time()
        r = session.get(url, stream=True, timeout=120)
        if r.status_code in (403, 429):
            raise RuntimeError(f"HTTP {r.status_code} for {url}: stopping")
        r.raise_for_status()
        h, n = hashlib.sha256(), 0
        with open(dest + ".part", "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
                h.update(chunk)
                n += len(chunk)
        os.replace(dest + ".part", dest)
        meta = {
            "source_url": url,
            "retrieved_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "http_status": r.status_code,
            "last_modified": r.headers.get("Last-Modified"),
            "bytes": n,
            "sha256": h.hexdigest(),
        }
        with open(dest + ".meta.json", "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=1)
        rows.append(meta)
        log(f"{rel} {n} bytes, Last-Modified {meta['last_modified']}")
    return rows


@dataclass
class Feature:
    geonameid: int
    name: str
    asciiname: str
    lat: float
    lon: float
    fclass: str
    fcode: str
    cc: str
    cc2: list
    admin: tuple  # (admin1, admin2, admin3, admin4); '' when empty
    population: int | None
    modified: str


@dataclass
class AltName:
    alt_id: int
    geonameid: int
    lang: str | None
    name: str
    preferred: bool
    short: bool
    colloquial: bool
    historic: bool
    valid_from: str | None
    valid_to: str | None


@dataclass
class GeoNames:
    features: dict = field(default_factory=dict)        # geonameid -> Feature
    alternates: dict = field(default_factory=dict)      # geonameid -> [AltName]
    admin1: dict = field(default_factory=dict)          # 'SA.02' -> (name, asciiname, geonameid)
    admin2: dict = field(default_factory=dict)          # 'SA.02.123' -> (name, asciiname, geonameid)
    countries: dict = field(default_factory=dict)       # 'SA' -> (name, geonameid)
    feature_codes: dict = field(default_factory=dict)   # 'P.PPL' -> (name, description)
    hierarchy: list = field(default_factory=list)       # (parent, child, type)


def _lines(path: str, member: str | None = None):
    if path.endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            name = member or os.path.basename(path)[:-4] + ".txt"
            with z.open(name) as fh:
                for line in io.TextIOWrapper(fh, encoding="utf-8", newline="\n"):
                    yield line.rstrip("\n")
    else:
        with open(path, encoding="utf-8", newline="\n") as fh:
            for line in fh:
                yield line.rstrip("\n")


def _int(s: str) -> int | None:
    s = s.strip()
    return int(s) if s else None


def read(folder: str, states=None) -> GeoNames:
    """Read the files written by fetch() for the given states."""
    states = list(states or STATES)
    g = GeoNames()
    for cc in states:
        for line in _lines(os.path.join(folder, f"{cc}.zip")):
            c = line.split("\t")
            if len(c) < 19:
                continue
            pop = _int(c[14])
            g.features[int(c[0])] = Feature(
                geonameid=int(c[0]), name=c[1], asciiname=c[2], lat=float(c[4]), lon=float(c[5]),
                fclass=c[6], fcode=c[7], cc=c[8], cc2=[x for x in c[9].split(",") if x],
                admin=(c[10], c[11], c[12], c[13]), population=pop if pop else None, modified=c[18])
        for line in _lines(os.path.join(folder, "alternatenames", f"{cc}.zip")):
            c = line.split("\t")
            if len(c) < 8:
                continue
            c += [""] * (10 - len(c))
            a = AltName(alt_id=int(c[0]), geonameid=int(c[1]), lang=c[2] or None, name=c[3],
                        preferred=c[4] == "1", short=c[5] == "1", colloquial=c[6] == "1",
                        historic=c[7] == "1", valid_from=c[8] or None, valid_to=c[9] or None)
            g.alternates.setdefault(a.geonameid, []).append(a)
    for line in _lines(os.path.join(folder, "admin1CodesASCII.txt")):
        c = line.split("\t")
        if len(c) >= 4 and c[0][:2] in states:
            g.admin1[c[0]] = (c[1], c[2], _int(c[3]))
    for line in _lines(os.path.join(folder, "admin2Codes.txt")):
        c = line.split("\t")
        if len(c) >= 4 and c[0][:2] in states:
            g.admin2[c[0]] = (c[1], c[2], _int(c[3]))
    for line in _lines(os.path.join(folder, "countryInfo.txt")):
        if line.startswith("#") or not line.strip():
            continue
        c = line.split("\t")
        if c[0] in states:
            g.countries[c[0]] = (c[4], _int(c[16]))
    for line in _lines(os.path.join(folder, "featureCodes_en.txt")):
        c = line.split("\t")
        if len(c) >= 3:
            g.feature_codes[c[0]] = (c[1], c[2])
    for line in _lines(os.path.join(folder, "hierarchy.zip"), "hierarchy.txt"):
        c = line.split("\t")
        if len(c) >= 2:
            p, ch = int(c[0]), int(c[1])
            if ch in g.features or p in g.features:
                g.hierarchy.append((p, ch, c[2] if len(c) > 2 else ""))
    return g
