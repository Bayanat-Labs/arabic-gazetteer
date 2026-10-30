"""Parquet schemas and writers for the released configs."""
from __future__ import annotations

import os

import pyarrow as pa
import pyarrow.parquet as pq

_link = pa.struct([("qid", pa.string()), ("method", pa.string()), ("distance_km", pa.float64()),
                   ("status", pa.string()), ("reason", pa.string())])
_node = pa.struct([("level", pa.int8()), ("code", pa.string()), ("geoname_id", pa.int64()),
                   ("record_id", pa.string()), ("name_ar", pa.string()), ("name_en", pa.string()),
                   ("status", pa.string()), ("source", pa.string())])
_code = pa.struct([("type", pa.string()), ("value", pa.string())])
_ref = pa.struct([("source", pa.string()), ("source_record_id", pa.string()), ("url", pa.string()),
                  ("version", pa.string())])

PLACES = pa.schema([
    ("record_id", pa.string()), ("source", pa.string()),
    ("geoname_id", pa.int64()), ("wikidata_qid", pa.string()), ("wikidata_links", pa.list_(_link)),
    ("name_ar", pa.string()), ("name_ar_norm", pa.string()), ("name_ar_rule", pa.string()),
    ("name_en", pa.string()), ("name_en_rule", pa.string()), ("geonames_name", pa.string()),
    ("names_ar", pa.list_(pa.string())), ("names_latin", pa.list_(pa.string())),
    ("n_names_ar", pa.int32()), ("n_names_latin", pa.int32()),
    ("n_clusters_ar", pa.int32()), ("n_clusters_latin", pa.int32()),
    ("name_family_id", pa.string()),
    ("feature_class", pa.string()), ("feature_code", pa.string()), ("feature_class_source", pa.string()),
    ("wikidata_classes", pa.list_(pa.string())),
    ("country_code", pa.string()), ("other_country_codes", pa.list_(pa.string())),
    ("latitude", pa.float64()), ("longitude", pa.float64()), ("coordinates_source", pa.string()),
    ("population", pa.int64()), ("population_source", pa.string()),
    ("admin_path", pa.list_(_node)), ("admin_path_source", pa.string()),
    ("admin_levels", pa.int8()), ("admin_levels_resolved", pa.int8()),
    ("parent_place_ids", pa.list_(pa.string())),
    ("hierarchy_check", pa.string()), ("hierarchy_conflict", pa.bool_()),
    ("codes", pa.list_(_code)), ("wikipedia_links", pa.list_(pa.string())),
    ("possible_duplicate_of", pa.string()), ("geonames_modified", pa.string()),
    ("license_partition", pa.string()), ("source_refs", pa.list_(_ref)),
    ("label_origin", pa.string()), ("review_status", pa.string()),
])

NAMES = pa.schema([
    ("name_id", pa.string()), ("record_id", pa.string()), ("name", pa.string()),
    ("script", pa.string()), ("lang", pa.string()), ("is_arabic", pa.bool_()), ("is_latin", pa.bool_()),
    ("source", pa.string()), ("source_field", pa.string()),
    ("preferred", pa.bool_()), ("short", pa.bool_()), ("colloquial", pa.bool_()), ("historic", pa.bool_()),
    ("valid_from", pa.string()), ("valid_to", pa.string()),
    ("name_norm", pa.string()), ("match_key", pa.string()), ("cluster_id", pa.string()),
    ("name_family_id", pa.string()), ("is_canonical_ar", pa.bool_()), ("name_issue", pa.string()),
    ("source_license", pa.string()),
])

ADMIN_UNITS = pa.schema([
    ("geoname_id", pa.int64()), ("record_id", pa.string()), ("country_code", pa.string()),
    ("level", pa.int8()), ("code", pa.string()), ("feature_code", pa.string()),
    ("parent_geoname_id", pa.int64()), ("name_ar", pa.string()), ("name_en", pa.string()),
    ("geonames_name", pa.string()), ("n_places", pa.int32()),
    ("latitude", pa.float64()), ("longitude", pa.float64()),
])

MATCH_EXAMPLES = pa.schema([
    ("example_id", pa.string()), ("input", pa.string()), ("input_script", pa.string()),
    ("input_kind", pa.string()), ("rule", pa.string()), ("target_record_id", pa.string()),
    ("distractor_ids", pa.list_(pa.string())), ("n_distractors", pa.int32()),
    ("jurisdiction_hint", pa.string()), ("label_origin", pa.string()), ("split", pa.string()),
])

SCHEMAS = {"places": PLACES, "names": NAMES, "admin_units": ADMIN_UNITS, "match_examples": MATCH_EXAMPLES}
ROWS_PER_FILE = {"places": 150_000, "names": 700_000, "admin_units": 100_000}


def name_ids(names) -> None:
    for n in names:
        n["name_id"] = f"{n['record_id']}~{n['source_name_id']}"


def write_table(rows, schema, path) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cols = {f.name: [r.get(f.name) for r in rows] for f in schema}
    table = pa.table(cols, schema=schema)
    pq.write_table(table, path, compression="zstd", compression_level=9, row_group_size=50_000,
                   write_statistics=True, use_dictionary=True)


def write_config(rows, config, out_dir) -> list[str]:
    """Write one config as data/<config>/train-0000k-of-0000n.parquet; returns the paths."""
    schema = SCHEMAS[config]
    step = ROWS_PER_FILE[config]
    chunks = [rows[i:i + step] for i in range(0, len(rows), step)] or [[]]
    paths = []
    for i, chunk in enumerate(chunks):
        p = os.path.join(out_dir, "data", config, f"train-{i:05d}-of-{len(chunks):05d}.parquet")
        write_table(chunk, schema, p)
        paths.append(p)
    return paths


def write_match_examples(rows, out_dir) -> list[str]:
    paths = []
    for split in ("train", "dev", "test"):
        p = os.path.join(out_dir, "data", "match_examples", f"{split}.parquet")
        write_table([r for r in rows if r["split"] == split], MATCH_EXAMPLES, p)
        paths.append(p)
    return paths
