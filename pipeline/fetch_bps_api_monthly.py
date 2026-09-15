import json
import os
import re
from datetime import date
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "data" / "processed" / "bps_padi_bulanan_provinsi.csv"
RAW_DIR = ROOT / "data" / "raw" / "bps_api"
OUTPUT_PATH = ROOT / "data" / "interim" / "bps_api_bulanan.csv"

load_dotenv(ROOT / ".env")
API_KEY = os.getenv("BPS_API_KEY")
HEADERS = {"User-Agent": "Mozilla/5.0"}
BASE_URL = "https://webapi.bps.go.id/v1/api/list/model"

VARIABLES = {2504: "luas_panen", 2506: "produksi"}
COLUMN_NAMES = {"luas_panen": "luas_panen_ha", "produksi": "produksi_padi_ton_gkg"}

MONTHS = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
    "Agustus", "September", "Oktober", "November", "Desember",
]
PROVINCE_NAMES = {
    "KEP. BANGKA BELITUNG": "Kepulauan Bangka Belitung",
    "KEP. RIAU": "Kepulauan Riau",
    "DKI JAKARTA": "DKI Jakarta",
    "DI YOGYAKARTA": "DI Yogyakarta",
}


def get_json(url: str) -> dict:
    body = requests.get(url, headers=HEADERS, timeout=60).json()
    if body.get("status") != "OK" or body.get("data-availability") != "available":
        raise RuntimeError(f"API BPS gagal: {body.get('message')} ({url.split('/key/')[0]})")
    return body


def available_years(var_id: int) -> dict:
    """{2025: 125, 2026: 126}"""
    body = get_json(f"{BASE_URL}/th/lang/ind/domain/0000/var/{var_id}/key/{API_KEY}/")
    return {int(item["th"]): item["th_id"] for item in body["data"][1]}


def month_status(note: str, n_months: int = 12) -> dict:
    """Baca catatan API, mis. 'Produksi padi Mei-Oktober adalah angka potensi'.

    Data dari API selalu lebih baru dari publikasi PDF, jadi belum ada yang berstatus
    angka tetap: default "sementara", lalu bulan yang disebut "potensi" ditimpa.
    """
    status = {month: "sementara" for month in range(1, n_months + 1)}
    for start, end in re.findall(r"(\w+)\s*-\s*(\w+) adalah angka potensi", note):
        for month in range(MONTHS.index(start) + 1, MONTHS.index(end) + 2):
            status[month] = "potensi"
    return status


def parse(body: dict, var_id: int, name: str) -> pd.DataFrame:
    status = month_status(body["var"][0]["note"])
    turvar = body["turvar"][0]["val"]
    rows = []
    for province in body["vervar"]:
        if province["label"] == "INDONESIA":
            continue
        for year in body["tahun"]:
            for period in body["turtahun"]:
                month = period["val"]
                key = f"{province['val']}{var_id}{turvar}{year['val']}{month}"
                if month > 12 or key not in body["datacontent"]:
                    continue  # periode 13 = tahunan
                rows.append({
                    "tahun": int(year["label"]),
                    "bulan": month,
                    "provinsi": PROVINCE_NAMES.get(province["label"], province["label"].title()),
                    COLUMN_NAMES[name]: body["datacontent"][key],
                    f"status_{name}": status[month],
                })
    return pd.DataFrame(rows)


def main():
    if not API_KEY:
        raise SystemExit("BPS_API_KEY belum diisi di file .env")

    last_pdf_year = int(pd.read_csv(DATASET_PATH)["tahun"].max())
    today = date.today().isoformat()
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    frames = []
    for var_id, name in VARIABLES.items():
        years = {y: th for y, th in available_years(var_id).items() if y > last_pdf_year}
        if not years:
            raise SystemExit(f"Variabel {var_id}: tidak ada tahun setelah {last_pdf_year}")

        body = get_json(
            f"{BASE_URL}/data/lang/ind/domain/0000/var/{var_id}"
            f"/th/{';'.join(map(str, years.values()))}/key/{API_KEY}/"
        )
        snapshot = RAW_DIR / f"{var_id}_{'_'.join(map(str, years))}_{today}.json"
        snapshot.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"Variabel {var_id} ({name}), tahun {list(years)}, update BPS: {body['last_update']}")
        print(f"  Catatan: {' | '.join(body['var'][0]['note'].splitlines()[:2])}")
        frames.append(parse(body, var_id, name))

    df = frames[0].merge(frames[1], on=["tahun", "bulan", "provinsi"], how="outer")
    df.insert(0, "tanggal", pd.to_datetime(dict(year=df["tahun"], month=df["bulan"], day=1)))
    df["tanggal_ambil"] = today
    df = df.sort_values(["tanggal", "provinsi"]).reset_index(drop=True)

    # Cek nama provinsi sama dengan dataset PDF
    pdf_provinces = set(pd.read_csv(DATASET_PATH)["provinsi"])
    unknown = sorted(set(df["provinsi"]) - pdf_provinces)
    print(f"\nProvinsi tidak dikenal: {unknown if unknown else 'tidak ada'}")
    print(f"Periode: {df['tanggal'].min():%Y-%m} s.d. {df['tanggal'].max():%Y-%m}, {len(df)} baris")

    national = df.groupby("bulan").agg(
        luas_panen_ha=("luas_panen_ha", "sum"),
        produksi_padi_ton_gkg=("produksi_padi_ton_gkg", "sum"),
        status_luas_panen=("status_luas_panen", "first"),
        status_produksi=("status_produksi", "first"),
    )
    print("\nNasional per bulan:")
    print(national.round(0).to_string())

    df.to_csv(OUTPUT_PATH, index=False, date_format="%Y-%m-%d")
    print(f"\nTersimpan: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()