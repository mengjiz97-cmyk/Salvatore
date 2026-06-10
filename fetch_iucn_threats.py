#!/usr/bin/env python3
"""
Fetch IUCN Red List threats for ALL threatened species in China (CR/EN/VU),
map to 5 major threat factors, generate threat_factors.json and update
4_致危因素_真实.html DATA array.

Prerequisites:
  pip install requests

IUCN API token (free): https://apiv3.iucnredlist.org/  → Register → My Account
Usage:
  python3 fetch_iucn_threats.py --token YOUR_TOKEN_HERE
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("请先安装 requests：pip install requests")

BASE = "https://apiv3.iucnredlist.org/api/v3"
THREATENED = {"CR", "EN", "VU"}

# IUCN top-level code → 5 major factors
FACTOR_MAP = {
    1: "栖息地破坏",
    2: "栖息地破坏",
    3: "栖息地破坏",
    4: "栖息地破坏",
    7: "栖息地破坏",
    5: "非法捕猎/过度利用",
    6: "非法捕猎/过度利用",
    9: "环境污染",
    11: "气候变化",
    8: "外来物种入侵",
}
FACTOR_ORDER = ["栖息地破坏", "非法捕猎/过度利用", "环境污染", "气候变化", "外来物种入侵"]


def get(url, token, **params):
    params["token"] = token
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_china_species(token):
    """Return list of {taxonid, scientific_name, category} for China."""
    page, results = 0, []
    while True:
        data = get(f"{BASE}/country/getspecies/CN", token, page=page)
        batch = data.get("result", [])
        results.extend(batch)
        print(f"  species page {page}: {len(batch)} records (total so far: {len(results)})")
        if len(batch) == 0:
            break
        page += 1
        time.sleep(0.3)
    return results


def fetch_threats(taxon_id, token):
    try:
        data = get(f"{BASE}/threats/species/id/{taxon_id}", token)
        return data.get("result", [])
    except Exception as e:
        print(f"    warn: threats for id={taxon_id} failed: {e}")
        return []


def parse_top_code(code_str):
    """'2.1.1' → 2, '11' → 11, '' → None"""
    try:
        return int(str(code_str).split(".")[0])
    except (ValueError, AttributeError):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", required=True, help="IUCN API token")
    args = parser.parse_args()
    token = args.token

    print("Step 1: fetching threatened species list for China ...")
    all_species = fetch_china_species(token)
    threatened = [s for s in all_species if s.get("category", "").upper() in THREATENED]
    print(f"  total species in China: {len(all_species)}")
    print(f"  threatened (CR/EN/VU): {len(threatened)}")

    print("\nStep 2: fetching threats for each species ...")
    species_factors: dict[str, set] = {}  # scientific_name → set of factor names
    unclassified_codes: list = []
    total_threat_rows = 0

    for i, sp in enumerate(threatened):
        sid = sp["taxonid"]
        name = sp["scientific_name"]
        threats = fetch_threats(sid, token)
        total_threat_rows += len(threats)
        factors = set()
        for t in threats:
            code = t.get("code", "")
            top = parse_top_code(code)
            if top in FACTOR_MAP:
                factors.add(FACTOR_MAP[top])
            elif top == 10:
                pass  # geological events — intentionally excluded
            else:
                unclassified_codes.append(code)
        species_factors[name] = factors
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(threatened)} done ...")
        time.sleep(0.2)

    print("\nStep 3: aggregating ...")
    n_species = len(species_factors)
    factor_counts = {f: 0 for f in FACTOR_ORDER}
    for factors in species_factors.values():
        for f in factors:
            if f in factor_counts:
                factor_counts[f] += 1

    rows = []
    for f in FACTOR_ORDER:
        cnt = factor_counts[f]
        pct = round(cnt / n_species * 100, 1) if n_species else 0
        rows.append({"factor": f, "count": cnt, "pct": pct})

    # Sort by count descending
    rows.sort(key=lambda x: x["count"], reverse=True)

    out = {
        "total_threatened_species": n_species,
        "total_threat_records": total_threat_rows,
        "unclassified_count": len(unclassified_codes),
        "unclassified_sample": list(set(unclassified_codes))[:20],
        "factors": rows,
    }

    Path("threat_factors.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\n=== 汇总 ===")
    print(f"受威胁物种总数: {n_species}")
    print(f"威胁记录总条数: {total_threat_rows}")
    print(f"无法归类的 code 数: {len(unclassified_codes)}")
    print(f"\n{'因素':<14}{'物种数':>8}{'占比%':>8}")
    print("-" * 32)
    for r in rows:
        print(f"{r['factor']:<14}{r['count']:>8}{r['pct']:>8}")

    # Update HTML DATA array
    html_path = Path("4_致危因素_真实.html")
    if html_path.exists():
        html = html_path.read_text(encoding="utf-8")
        new_data = json.dumps(rows, ensure_ascii=False)
        html = re.sub(
            r"(const DATA\s*=\s*)(\[.*?\])(;)",
            lambda m: m.group(1) + new_data + m.group(3),
            html,
            flags=re.DOTALL,
        )
        html_path.write_text(html, encoding="utf-8")
        print(f"\nHTML DATA 已更新 → {html_path}")

    print("\nDone. threat_factors.json saved.")


if __name__ == "__main__":
    main()
