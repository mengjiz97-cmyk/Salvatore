#!/usr/bin/env python3
"""
Build bubble_data.json and update 5_三维气泡_真实.html SP array.

Data sources:
  体重 — PanTHERIA (mammals), EltonTraits (birds), FishBase API (fish)
  IUCN  — Red List API v3 (token required)

Usage:
  1. Put species.txt in same directory (one scientific name per line)
  2. Download data files:
       PanTHERIA: https://esapubs.org/archive/ecol/E090/184/PanTHERIA_1-0_WR05_Aug2008.txt
       EltonTraits: https://figshare.com/articles/dataset/EltonTraits_1_0/9628764
       (save as PanTHERIA.txt and EltonTraits.txt)
  3. pip install requests
  4. python3 fetch_bubble_data.py --token YOUR_IUCN_TOKEN

FishBase weight is fetched via rfishbase REST proxy (no key needed).
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
    sys.exit("请先安装：pip install requests")

IUCN_BASE = "https://apiv3.iucnredlist.org/api/v3"
FISHBASE_BASE = "https://fishbase.ropensci.org"

IUCN_COLOR = {
    "CR": "#D81E05", "EN": "#FC7F3F", "VU": "#F9E814",
    "NT": "#CCE226", "LC": "#60C659", "EW": "#542344",
    "DD": "#d3d3d3", "NE": "#aaaaaa",
}


# ── helpers ──────────────────────────────────────────────────────────────────

def load_species(path="species.txt"):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.startswith("#")]


def load_pantheria(path="PanTHERIA.txt"):
    """Return dict {scientific_name: weight_kg}"""
    result = {}
    with open(path, encoding="utf-8") as f:
        header = f.readline().strip().split("\t")
        try:
            name_col = header.index("MSW05_Binomial")
            mass_col = header.index("5-1_AdultBodyMass_g")
        except ValueError:
            # fallback: search loosely
            name_col = next(i for i, h in enumerate(header) if "Binomial" in h)
            mass_col = next(i for i, h in enumerate(header) if "BodyMass" in h and "_g" in h)
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) <= max(name_col, mass_col):
                continue
            name = parts[name_col].strip()
            mass_str = parts[mass_col].strip()
            try:
                mass_g = float(mass_str)
                if mass_g > 0:
                    result[name] = round(mass_g / 1000, 4)
            except ValueError:
                pass
    return result


def load_eltontraits(path="EltonTraits.txt"):
    """Return dict {scientific_name: weight_kg} for birds."""
    result = {}
    with open(path, encoding="utf-8") as f:
        header = f.readline().strip().split("\t")
        try:
            name_col = header.index("Scientific")
        except ValueError:
            name_col = next(i for i, h in enumerate(header) if "Scientific" in h)
        try:
            mass_col = header.index("BodyMass-Value")
        except ValueError:
            mass_col = next(i for i, h in enumerate(header) if "BodyMass" in h)
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) <= max(name_col, mass_col):
                continue
            name = parts[name_col].strip()
            mass_str = parts[mass_col].strip()
            try:
                mass_g = float(mass_str)
                if mass_g > 0:
                    result[name] = round(mass_g / 1000, 4)
            except ValueError:
                pass
    return result


def fetch_fishbase_weight(sci_name):
    """Query FishBase via rfishbase REST proxy. Returns kg or None."""
    genus, *sp = sci_name.split()
    if not sp:
        return None
    try:
        r = requests.get(
            f"{FISHBASE_BASE}/species",
            params={"Genus": genus, "Species": sp[0]},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if data and isinstance(data, list):
            # Weight field: Weight (g) in species table
            w = data[0].get("Weight")
            if w and float(w) > 0:
                return round(float(w) / 1000, 4)
    except Exception:
        pass
    return None


def iucn_get(path, token):
    r = requests.get(f"{IUCN_BASE}{path}", params={"token": token}, timeout=20)
    r.raise_for_status()
    return r.json()


def fetch_iucn(sci_name, token):
    """Return (category, population_str_or_None)"""
    try:
        name_enc = sci_name.replace(" ", "%20")
        data = iucn_get(f"/species/{name_enc}", token)
        result = data.get("result", [])
        if not result:
            return None, None
        sp = result[0]
        category = sp.get("category", "").upper()
        # population narrative — IUCN v3 doesn't expose numeric pop directly,
        # but population_size field exists in some assessments
        pop = sp.get("population_size") or sp.get("populationsize")
        return category, pop
    except Exception as e:
        print(f"    IUCN warn ({sci_name}): {e}")
        return None, None


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", required=True, help="IUCN API token")
    parser.add_argument("--species", default="species.txt")
    parser.add_argument("--pantheria", default="PanTHERIA.txt")
    parser.add_argument("--elton",     default="EltonTraits.txt")
    args = parser.parse_args()

    species_list = load_species(args.species)
    print(f"物种清单：{len(species_list)} 种\n")

    # Load trait databases
    pantheria = {}
    if Path(args.pantheria).exists():
        pantheria = load_pantheria(args.pantheria)
        print(f"PanTHERIA 加载：{len(pantheria)} 条")
    else:
        print(f"⚠ 未找到 {args.pantheria}，哺乳类体重将跳过文件查找")

    elton = {}
    if Path(args.elton).exists():
        elton = load_eltontraits(args.elton)
        print(f"EltonTraits 加载：{len(elton)} 条\n")
    else:
        print(f"⚠ 未找到 {args.elton}，鸟类体重将跳过文件查找\n")

    results = []
    missing_weight = []
    missing_pop = []

    for sci in species_list:
        print(f"Processing: {sci}")
        entry = {"name_cn": "", "name_sci": sci, "weight_kg": None, "population": None, "iucn": ""}

        # ── weight: try PanTHERIA → EltonTraits → FishBase ──
        w = pantheria.get(sci) or elton.get(sci)
        if w is None:
            w = fetch_fishbase_weight(sci)
            if w:
                print(f"  FishBase weight: {w} kg")
        entry["weight_kg"] = w

        # ── IUCN ──
        cat, pop = fetch_iucn(sci, args.token)
        entry["iucn"] = cat or "DD"
        if pop is not None:
            try:
                entry["population"] = int(float(str(pop)))
            except (ValueError, TypeError):
                entry["population"] = None

        if entry["weight_kg"] is None:
            missing_weight.append(sci)
        if entry["population"] is None:
            missing_pop.append(sci)

        results.append(entry)
        time.sleep(0.3)

    # Save JSON
    Path("bubble_data.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Report
    print("\n=== 结果汇总 ===")
    print(f"成功拼到：{len(results)} 种")
    print(f"缺体重（{len(missing_weight)} 种）：{', '.join(missing_weight) or '无'}")
    print(f"缺数量（{len(missing_pop)} 种）：{', '.join(missing_pop) or '无'}")

    # Update HTML SP array
    html_path = Path("5_三维气泡_真实.html")
    if html_path.exists():
        html = html_path.read_text(encoding="utf-8")
        new_sp = json.dumps(results, ensure_ascii=False)
        html = re.sub(
            r"(const SP\s*=\s*)(\[[\s\S]*?\])(;)",
            lambda m: m.group(1) + new_sp + m.group(3),
            html,
        )
        html_path.write_text(html, encoding="utf-8")
        print(f"\nHTML SP 数组已更新 → {html_path}")

    print("\nDone. bubble_data.json saved.")


if __name__ == "__main__":
    main()
