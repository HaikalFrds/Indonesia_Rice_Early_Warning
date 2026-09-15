from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = ROOT / "data" / "processed" / "bps_padi_bulanan_provinsi.csv"
API_PATH = ROOT / "data" / "interim" / "bps_api_bulanan.csv"
OUTPUT_PATH = ROOT / "data" / "processed" / "padi_bulanan_provinsi.csv"

# Produksi beras / produksi padi (GKG) di publikasi BPS 2020–2025.
# = rendemen giling 64,02% dikurangi susut, benih, pakan, dan penggunaan non-pangan
BERAS_PER_GKG = 0.5762

PARENT_PROVINCE = {
    "Papua Selatan": "Papua",
    "Papua Tengah": "Papua",
    "Papua Pegunungan": "Papua",
    "Papua Barat Daya": "Papua Barat",
}


def load_pdf() -> pd.DataFrame:
    df = pd.read_csv(PDF_PATH, parse_dates=["tanggal"])
    df["status_luas_panen"] = "tetap"
    df["status_produksi"] = "tetap"
    df["sumber"] = "publikasi"
    return df


def load_api(pdf: pd.DataFrame) -> pd.DataFrame:
    df = pd.read_csv(API_PATH, parse_dates=["tanggal"])
    new = df[df["tanggal"] > pdf["tanggal"].max()].copy()
    if len(new) < len(df):
        print(f"Baris API yang sudah ada di publikasi (dibuang): {len(df) - len(new)}")
    new["wilayah_34"] = new["provinsi"].replace(PARENT_PROVINCE)
    new["produksi_beras_ton"] = (new["produksi_padi_ton_gkg"] * BERAS_PER_GKG).round(2)
    new["sumber"] = "webapi"
    return new.drop(columns="tanggal_ambil")


def check(df: pd.DataFrame, pdf: pd.DataFrame):
    duplicates = df.duplicated(subset=["tanggal", "provinsi"]).sum()
    print(f"Duplikat tanggal-provinsi: {duplicates}")

    # Setiap provinsi harus punya deret bulan tanpa lubang sejak data pertamanya
    gaps = {}
    for province, group in df.groupby("provinsi"):
        expected = pd.date_range(group["tanggal"].min(), group["tanggal"].max(), freq="MS")
        if len(expected) != len(group):
            gaps[province] = len(expected) - len(group)
    print(f"Provinsi dengan bulan bolong: {gaps if gaps else 'tidak ada'}")

    ratio = pdf.groupby("tahun")[["produksi_beras_ton", "produksi_padi_ton_gkg"]].sum()
    ratio = (ratio["produksi_beras_ton"] / ratio["produksi_padi_ton_gkg"]).round(4)
    print(f"Rasio beras/GKG di publikasi 2020-2025: {sorted(float(r) for r in ratio.loc[2020:].unique())}")

    summary = df.groupby(["tahun", "sumber"]).agg(
        n_provinsi=("provinsi", "nunique"),
        n_bulan=("bulan", "nunique"),
        produksi_padi_juta_ton=("produksi_padi_ton_gkg", lambda s: s.sum() / 1e6),
    )
    print("\nRingkasan per tahun:")
    print(summary.round(2).to_string())

    status = df[df["sumber"] == "webapi"].groupby(["status_luas_panen", "status_produksi"])["bulan"]
    print("\nStatus data API (bulan):")
    print(status.agg(lambda s: f"{s.min()}-{s.max()}").to_string())


def main():
    pdf = load_pdf()
    api = load_api(pdf)

    df = pd.concat([pdf, api], ignore_index=True)
    first_columns = ["tanggal", "tahun", "bulan", "provinsi", "wilayah_34", "sumber",
                     "status_luas_panen", "status_produksi"]
    df = df[first_columns + [c for c in df.columns if c not in first_columns]]
    df = df.sort_values(["tanggal", "provinsi"]).reset_index(drop=True)

    check(df, pdf)

    df.to_csv(OUTPUT_PATH, index=False, date_format="%Y-%m-%d")
    print(f"\nTersimpan: {OUTPUT_PATH} ({len(df)} baris, {df.shape[1]} kolom)")


if __name__ == "__main__":
    main()