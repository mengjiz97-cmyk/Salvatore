#!/usr/bin/env python3
"""
Fetch GBIF occurrence records for 11 Chinese flagship endangered species.
Output: gbif_china_endangered.csv
No GBIF account needed — uses public occurrence search API.
"""

import csv
import time
import urllib.request
import urllib.parse
import json

SPECIES = [
    ("大熊猫",     "Ailuropoda melanoleuca"),
    ("朱鹮",       "Nipponia nippon"),
    ("长江江豚",   "Neophocaena asiaeorientalis"),
    ("滇金丝猴",   "Rhinopithecus bieti"),
    ("亚洲象",     "Elephas maximus"),
    ("雪豹",       "Panthera uncia"),
    ("东北虎",     "Panthera tigris"),
    ("藏羚羊",     "Pantholops hodgsonii"),
    ("海南长臂猿", "Nomascus hainanus"),
    ("扬子鳄",     "Alligator sinensis"),
    ("中华穿山甲", "Manis pentadactyla"),
]

BASE_URL = "https://api.gbif.org/v1/occurrence/search"
FIELDS = [
    "gbifID", "species", "chineseName",
    "decimalLatitude", "decimalLongitude",
    "stateProvince", "year", "month",
    "basisOfRecord", "iucnRedListCategory",
    "datasetName", "occurrenceID",
]


def fetch_species(cn_name, sci_name, page_size=300):
    records = []
    offset = 0
    while True:
        params = urllib.parse.urlencode({
            "scientificName": sci_name,
            "country": "CN",
            "hasCoordinate": "true",
            "hasGeospatialIssue": "false",
            "occurrenceStatus": "PRESENT",
            "basisOfRecord": ["HUMAN_OBSERVATION", "PRESERVED_SPECIMEN"],
            "limit": page_size,
            "offset": offset,
        }, doseq=True)
        url = f"{BASE_URL}?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())

        results = data.get("results", [])
        for r in results:
            records.append({
                "gbifID":             r.get("gbifID", ""),
                "species":            r.get("species", sci_name),
                "chineseName":        cn_name,
                "decimalLatitude":    r.get("decimalLatitude", ""),
                "decimalLongitude":   r.get("decimalLongitude", ""),
                "stateProvince":      r.get("stateProvince", ""),
                "year":               r.get("year", ""),
                "month":              r.get("month", ""),
                "basisOfRecord":      r.get("basisOfRecord", ""),
                "iucnRedListCategory": r.get("iucnRedListCategory", ""),
                "datasetName":        r.get("datasetName", ""),
                "occurrenceID":       r.get("occurrenceID", ""),
            })

        offset += page_size
        end_of_records = data.get("endOfRecords", True)
        total = data.get("count", 0)
        print(f"  {cn_name}: fetched {min(offset, total)}/{total}")
        if end_of_records or offset >= total:
            break
        time.sleep(0.5)  # be polite to GBIF

    return records


def main():
    out_file = "gbif_china_endangered.csv"
    all_records = []

    for cn_name, sci_name in SPECIES:
        print(f"Fetching {cn_name} ({sci_name}) ...")
        try:
            recs = fetch_species(cn_name, sci_name)
            all_records.extend(recs)
            print(f"  -> {len(recs)} records total")
        except Exception as e:
            print(f"  ERROR: {e}")
        time.sleep(1)

    with open(out_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(all_records)

    print(f"\nDone. {len(all_records)} records saved to {out_file}")


if __name__ == "__main__":
    main()
