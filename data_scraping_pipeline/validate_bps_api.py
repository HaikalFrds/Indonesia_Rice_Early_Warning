import os
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "data" / "processed" / "bps_padi_bulanan_provinsi.csv"
OUTPUT_PATH = ROOT / "data" / "interim" / "validasi_api_bps.csv"

load_dotenv(ROOT / ".env")
API_KEY = os.getenv("BPS_API_KEY")
HEADERS = {"User-Agent": "Mozilla/5.0"}
BASE_URL = "https://webapi.bps.go.id/v1/api/list/model/data/lang/ind/domain/0000"

TOLERANCE_PCT = 0.01  # selisih > 0,01% dianggap tidak cocok

# Nama provinsi di API yang berbeda dengan dataset kita
API_PROVINCE_NAMES = {
    "KEP. BANGKA BELITUNG": "KEPULAUAN BANGKA BELITUNG",
    "KEP. RIAU": "KEPULAUAN RIAU",
}


def fetch(var_id: int, year_ids: list) -> dict:
    """Ambil data satu variabel. API membatasi maksimal 3 tahun per request."""
    url = f"{BASE_URL}/var/{var_id}/th/{';'.join(map(str, year_ids))}/key/{API_KEY}/"
    body = requests.get(url, headers=HEADERS, timeout=60).json()
    if body.get("status") != "OK" or body.get("data-availability") != "available":
        raise RuntimeError(f"API BPS gagal (var {var_id}, th {year_ids}): {body.get('message')}")
    return body


def to_rows(body: dict, var_id: int) -> list:
    """Kunci datacontent = id_provinsi + id_variabel + id_turvar + id_tahun + id_turtahun."""
    rows = []
    for province in body["vervar"]:
        for turvar in body["turvar"]:
            for year in body["tahun"]:
                for period in body["turtahun"]:
                    key = f"{province['val']}{var_id}{turvar['val']}{year['val']}{period['val']}"
                    if key in body["datacontent"]:
                        rows.append({
                            "provinsi_api": province["label"],
                            "variabel": turvar["label"],
                            "tahun": int(year["label"]),
                            "periode": period["val"],  # 0 = tahunan, 1–12 = bulan, 13 = tahunan
                            "nilai": body["datacontent"][key],
                        })
    return rows


def fetch_annual() -> pd.DataFrame:
    rows = []
    for year_ids in ([118, 119, 120], [121, 122, 123], [124]):  # 2018–2024
        rows += to_rows(fetch(1498, year_ids), 1498)
    df = pd.DataFrame(rows)
    df = df[df["variabel"].isin(["Luas Panen (ha)", "Produksi (ton)"])]
    df["kolom"] = df["variabel"].map({
        "Luas Panen (ha)": "luas_panen_ha",
        "Produksi (ton)": "produksi_padi_ton_gkg",
    })
    return df


def fetch_monthly_2025() -> pd.DataFrame:
    frames = []
    for var_id, column in [(2504, "luas_panen_ha"), (2506, "produksi_padi_ton_gkg")]:
        df = pd.DataFrame(to_rows(fetch(var_id, [125]), var_id))
        df["kolom"] = column
        frames.append(df[df["periode"] == 13])  # kolom "Tahunan"
    return pd.concat(frames)


def main():
    if not API_KEY:
        raise SystemExit("BPS_API_KEY belum diisi di file .env")

    api = pd.concat([fetch_annual(), fetch_monthly_2025()])
    api = api[api["provinsi_api"] != "INDONESIA"]
    api["provinsi_api"] = api["provinsi_api"].replace(API_PROVINCE_NAMES)
    api = api.pivot_table(index=["tahun", "provinsi_api"], columns="kolom", values="nilai")

    dataset = pd.read_csv(DATASET_PATH)
    dataset["provinsi_api"] = dataset["provinsi"].str.upper()
    pdf = dataset.groupby(["tahun", "provinsi_api"])[["luas_panen_ha", "produksi_padi_ton_gkg"]].sum()

    merged = pdf.join(api, how="outer", lsuffix="_pdf", rsuffix="_api")

    only_pdf = merged[merged["produksi_padi_ton_gkg_api"].isna()]
    only_api = merged[merged["produksi_padi_ton_gkg_pdf"].isna() & (merged["produksi_padi_ton_gkg_api"] > 0)]
    print(f"Provinsi-tahun hanya ada di PDF: {len(only_pdf)}")
    print(f"Provinsi-tahun hanya ada di API (nilai > 0): {len(only_api)}")
    if len(only_pdf) or len(only_api):
        print(pd.concat([only_pdf, only_api]).index.tolist())
    # Provinsi pemekaran Papua sebelum 2023 hanya ada di API (kosong / 0): diabaikan
    merged = merged.dropna(subset=["produksi_padi_ton_gkg_pdf"])

    for column in ["luas_panen_ha", "produksi_padi_ton_gkg"]:
        diff = merged[f"{column}_pdf"] - merged[f"{column}_api"]
        merged[f"{column}_selisih_pct"] = (diff / merged[f"{column}_api"] * 100).round(4)

    merged.reset_index().to_csv(OUTPUT_PATH, index=False)

    summary = merged.groupby("tahun").agg(
        n_provinsi=("produksi_padi_ton_gkg_pdf", "size"),
        produksi_pdf=("produksi_padi_ton_gkg_pdf", "sum"),
        produksi_api=("produksi_padi_ton_gkg_api", "sum"),
        maks_selisih_luas_pct=("luas_panen_ha_selisih_pct", lambda s: s.abs().max()),
        maks_selisih_produksi_pct=("produksi_padi_ton_gkg_selisih_pct", lambda s: s.abs().max()),
    )
    print("\nRingkasan per tahun:")
    print(summary.round(2).to_string())

    bad = merged[
        (merged["luas_panen_ha_selisih_pct"].abs() > TOLERANCE_PCT)
        | (merged["produksi_padi_ton_gkg_selisih_pct"].abs() > TOLERANCE_PCT)
    ]
    print(f"\nProvinsi-tahun dengan selisih > {TOLERANCE_PCT}%: {len(bad)}")
    if len(bad):
        print(bad.round(2).to_string())

    print(f"\nTersimpan: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()