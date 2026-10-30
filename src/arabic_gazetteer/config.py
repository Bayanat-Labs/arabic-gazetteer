"""Settings of the gazetteer build: scope, sources, name rules and thresholds."""
from __future__ import annotations

USER_AGENT = "BayanatLabs-OpenData/1.0 (+https://bayanatlabs.com/open; hello@bayanatlabs.com)"
MIN_REQUEST_GAP_S = 1.2  # at most one request per second to one host

GEONAMES_DUMP = "https://download.geonames.org/export/dump/"
GEONAMES_FILES = [
    "readme.txt",
    "countryInfo.txt",
    "featureCodes_en.txt",
    "admin1CodesASCII.txt",
    "admin2Codes.txt",
    "hierarchy.zip",
]

# The 22 member states of the League of Arab States, as GeoNames country codes, with the
# Wikidata item of each state.
STATES: dict[str, str] = {
    "DZ": "Q262", "BH": "Q398", "KM": "Q970", "DJ": "Q977", "EG": "Q79", "IQ": "Q796",
    "JO": "Q810", "KW": "Q817", "LB": "Q822", "LY": "Q1016", "MR": "Q1025", "MA": "Q1028",
    "OM": "Q842", "PS": "Q219060", "QA": "Q846", "SA": "Q851", "SO": "Q1045", "SD": "Q1049",
    "SY": "Q858", "TN": "Q948", "AE": "Q878", "YE": "Q805",
}
STATE_NAMES_EN: dict[str, str] = {
    "DZ": "Algeria", "BH": "Bahrain", "KM": "Comoros", "DJ": "Djibouti", "EG": "Egypt",
    "IQ": "Iraq", "JO": "Jordan", "KW": "Kuwait", "LB": "Lebanon", "LY": "Libya",
    "MR": "Mauritania", "MA": "Morocco", "OM": "Oman", "PS": "Palestine", "QA": "Qatar",
    "SA": "Saudi Arabia", "SO": "Somalia", "SD": "Sudan", "SY": "Syria", "TN": "Tunisia",
    "AE": "United Arab Emirates", "YE": "Yemen",
}
STATE_NAMES_AR: dict[str, str] = {
    "DZ": "الجزائر", "BH": "البحرين", "KM": "جزر القمر", "DJ": "جيبوتي", "EG": "مصر",
    "IQ": "العراق", "JO": "الأردن", "KW": "الكويت", "LB": "لبنان", "LY": "ليبيا",
    "MR": "موريتانيا", "MA": "المغرب", "OM": "عمان", "PS": "فلسطين", "QA": "قطر",
    "SA": "السعودية", "SO": "الصومال", "SD": "السودان", "SY": "سوريا", "TN": "تونس",
    "AE": "الإمارات", "YE": "اليمن",
}
QID_TO_STATE = {q: cc for cc, q in STATES.items()}

# GeoNames feature classes kept as places, and the feature codes kept from class S (spots and
# buildings). Other S codes and class R (roads, railroads) are not part of the gazetteer.
KEEP_CLASSES = {"A", "P", "H", "T", "L", "V", "U"}
KEEP_S_CODES = {"AIRP", "AIRF", "PRT", "UNIV", "HSP", "CSTL", "FT", "ANS", "RUIN", "MUS", "RSTN"}

# GeoNames language codes read as Arabic (Arabic and its varieties), and the codes of Latin-script
# names kept as name variants. Pseudo-codes are kept as codes or links, not as names.
ARABIC_LANGS = {"ar", "arb", "arz", "ary", "arq", "afb", "apc", "ajp", "acm", "aeb", "ars", "acq",
                "apd", "shu", "ayl", "ayh", "ayn"}
LATIN_LANGS = {"en", "fr", None}
CODE_PSEUDO_LANGS = {"iata": "iata", "icao": "icao", "faac": "faa", "unlc": "unlocode",
                     "post": "postcode", "abbr": "abbreviation"}
LINK_PSEUDO_LANG = "link"
WIKIDATA_PSEUDO_LANG = "wkdt"

# Wikidata label languages used.
WD_ARABIC_LANGS = ["ar", "arz", "ary"]
WD_LATIN_LANGS = ["en", "fr"]
# Monolingual-text name properties read from Wikidata.
WD_NAME_PROPS = {"P1448": "official_name", "P1705": "native_label", "P1813": "short_name"}

# Maximum distance (km) between the GeoNames and Wikidata coordinates for a link to be accepted,
# by GeoNames feature class.
LINK_MAX_KM = {"P": 10.0, "S": 10.0, "A": 50.0, "H": 50.0, "T": 50.0, "L": 50.0, "V": 50.0, "U": 50.0}
# Populated places with at least this GeoNames population allow a larger distance.
LARGE_PLACE_POPULATION = 100_000
LINK_MAX_KM_LARGE_PLACE = 30.0

# Wikidata classes: an item is given the family of the root it reaches in the fewest subclass-of
# (P279) steps from one of its instance-of (P31) classes; on a tie, the family listed first wins.
# The letters follow the GeoNames feature classes (P populated place, A administrative unit,
# S selected sites, H water, T terrain, V vegetation, L area). Family X (buildings, roads and
# other structures, organisations) is not kept.
WD_FAMILY_ROOTS: list[tuple[str, dict[str, str]]] = [
    ("S", {
        "Q1248784": "airport", "Q44782": "port", "Q3918": "university", "Q16917": "hospital",
        "Q23413": "castle", "Q57821": "fortification", "Q839954": "archaeological site",
        "Q109607": "ruins", "Q33506": "museum", "Q55488": "railway station",
    }),
    ("P", {"Q486972": "human settlement", "Q123705": "neighborhood"}),
    ("A", {"Q56061": "administrative territorial entity"}),
    ("H", {"Q15324": "body of water", "Q355304": "watercourse", "Q124714": "spring",
           "Q43483": "well", "Q187971": "wadi"}),
    ("T", {"Q271669": "landform", "Q8502": "mountain", "Q23442": "island"}),
    ("V", {"Q4421": "forest"}),
    ("L", {"Q82794": "geographic region", "Q473972": "protected area"}),
    ("X", {
        "Q811979": "architectural structure", "Q41176": "building", "Q1370598": "place of worship",
        "Q34442": "road", "Q121359": "infrastructure", "Q13226383": "facility",
        "Q4830453": "business", "Q43229": "organization", "Q2385804": "educational institution",
    }),
]
FAMILY_ORDER = [f for f, _ in WD_FAMILY_ROOTS]

# Generic words that can open an Arabic place name. They are removed only in the loose matching
# key of the baseline matcher, never from names.
AR_GENERIC_TERMS = ["مدينه", "محافظه", "منطقه", "قريه", "حي", "جزيره", "جبل", "وادي", "ولايه",
                    "مديريه", "بلديه", "مركز", "قضاء", "ناحيه", "عزبه", "نجع", "دوار", "اماره"]
LATIN_ARTICLES = ["al", "el", "ad", "ed", "adh", "ag", "ah", "aj", "ak", "an", "ar", "as", "ash",
                  "at", "ath", "az", "ez", "es", "esh", "et", "en", "er", "ul", "il", "l"]

# Split of the match examples: every example of one admin1 unit goes to the same split.
SPLIT_SALT = "arabic-gazetteer-v0.1"
SPLIT_BUCKETS = (("train", 70), ("dev", 10), ("test", 20))
