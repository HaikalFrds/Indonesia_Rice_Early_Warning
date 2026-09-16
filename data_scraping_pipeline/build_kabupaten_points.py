import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "data" / "raw" / "geoboundaries" / "idn_adm2.geojson"
PADI_PATH = ROOT / "data" / "processed" / "padi_bulanan_provinsi.csv"
OUTPUT_PATH = ROOT / "data" / "processed" / "titik_kabupaten.csv"

load_dotenv(ROOT / ".env")
API_KEY = os.getenv("BPS_API_KEY")
HEADERS = {"User-Agent": "Mozilla/5.0"}

GEOJSON_URL = (
    "https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/"
    "gbOpen/IDN/ADM2/geoBoundaries-IDN-ADM2_simplified.geojson"
)

# Nama provinsi di API BPS -> nama di dataset padi
PROVINCE_NAMES = {
    "Kep. Bangka Belitung": "Kepulauan Bangka Belitung",
    "Kep. Riau": "Kepulauan Riau",
    "Dki Jakarta": "DKI Jakarta",
    "Di Yogyakarta": "DI Yogyakarta",
}

# Kab/kota yang namanya berganti; geoBoundaries (2020) masih memakai nama lama
GEO_NAMES = {
    "Toba": "Toba Samosir",
    "Mahakam Ulu": "Mahakam Hulu",
    "Pasangkayu": "Mamuju Utara",
}

# Pemekaran 2022: API BPS masih memakai 34 provinsi, jadi kab/kota dipindahkan manual
# (UU 14, 15, 16, dan 29 Tahun 2022)
NEW_PROVINCES = {
    "Papua Selatan": ["Merauke", "Boven Digoel", "Mappi", "Asmat"],
    "Papua Tengah": ["Nabire", "Paniai", "Puncak Jaya", "Mimika", "Dogiyai", "Intan Jaya", "Deiyai", "Puncak"],
    "Papua Pegunungan": ["Jayawijaya", "Yahukimo", "Pegunungan Bintang", "Tolikara", "Nduga",
                         "Lanny Jaya", "Mamberamo Tengah", "Yalimo"],
    "Papua Barat Daya": ["Sorong", "Sorong Selatan", "Raja Ampat", "Tambrauw", "Maybrat", "Kota Sorong"],
}


def bps_domains(domain_type: str) -> list:
    url = f"https://webapi.bps.go.id/v1/api/domain/type/{domain_type}/key/{API_KEY}/"
    body = requests.get(url, headers=HEADERS, timeout=60).json()
    if body.get("status") != "OK":
        raise RuntimeError(f"API BPS gagal: {body.get('message')}")
    return body["data"][1]


def kab_name(item: dict) -> str:
    name = item["domain_name"]
    if re.fullmatch(r"(\w )+\w", name):  # "S I A K" -> "Siak"
        name = name.replace(" ", "").title()
    is_kota = item["domain_id"][2] == "7"  # kode 3578 = kota, 3501 = kabupaten
    return f"Kota {name}" if is_kota else name


def centroid(geometry: dict) -> tuple:
    """Titik tengah (berbobot luas) dari Polygon/MultiPolygon, dalam (lat, lon)."""
    polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    total_area, sum_x, sum_y = 0.0, 0.0, 0.0
    for polygon in polygons:
        ring = np.array(polygon[0])  # ring luar; lubang diabaikan
        x, y = ring[:, 0], ring[:, 1]
        cross = x[:-1] * y[1:] - x[1:] * y[:-1]
        area = cross.sum() / 2
        if area == 0:
            continue
        total_area += abs(area)
        sum_x += abs(area) * ((x[:-1] + x[1:]) * cross).sum() / (6 * area)
        sum_y += abs(area) * ((y[:-1] + y[1:]) * cross).sum() / (6 * area)
    return sum_y / total_area, sum_x / total_area


def load_geojson() -> dict:
    if not RAW_PATH.exists():
        RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
        resp = requests.get(GEOJSON_URL, timeout=120)
        resp.raise_for_status()
        RAW_PATH.write_bytes(resp.content)
    return json.loads(RAW_PATH.read_text(encoding="utf-8"))


def main():
    if not API_KEY:
        raise SystemExit("BPS_API_KEY belum diisi di file .env")

    provinces = {p["domain_id"][:2]: PROVINCE_NAMES.get(p["domain_name"], p["domain_name"])
                 for p in bps_domains("prov")}
    moved = {kab: province for province, kabs in NEW_PROVINCES.items() for kab in kabs}

    shapes = {f["properties"]["shapeName"]: f["geometry"] for f in load_geojson()["features"]}

    rows, unmatched = [], []
    for item in bps_domains("kab"):
        name = kab_name(item)
        geometry = shapes.get(GEO_NAMES.get(name, name))
        if geometry is None:
            unmatched.append(name)
            continue
        lat, lon = centroid(geometry)
        rows.append({
            "kode_bps": item["domain_id"],
            "kab_kota": name,
            "jenis": "Kota" if name.startswith("Kota ") else "Kabupaten",
            "provinsi": moved.get(name, provinces[item["domain_id"][:2]]),
            "lat": round(lat, 4),
            "lon": round(lon, 4),
        })

    df = pd.DataFrame(rows).sort_values(["provinsi", "kode_bps"])

    print(f"Kab/kota dari BPS: {len(rows) + len(unmatched)}, cocok dengan batas wilayah: {len(rows)}")
    print(f"Tidak cocok: {unmatched if unmatched else 'tidak ada'}")

    padi_provinces = set(pd.read_csv(PADI_PATH)["provinsi"])
    print(f"Provinsi: {df['provinsi'].nunique()}")
    print(f"Provinsi tidak ada di dataset padi: {sorted(set(df['provinsi']) - padi_provinces) or 'tidak ada'}")
    print(f"Provinsi dataset padi tanpa kab/kota: {sorted(padi_provinces - set(df['provinsi'])) or 'tidak ada'}")
    outside = df[~df["lat"].between(-11.5, 6.5) | ~df["lon"].between(94.5, 141.5)]
    print(f"Titik di luar kotak wilayah Indonesia: {len(outside)}")

    print("\nJumlah kab/kota per provinsi:")
    print(df.groupby("provinsi").size().to_string())

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"\nTersimpan: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()