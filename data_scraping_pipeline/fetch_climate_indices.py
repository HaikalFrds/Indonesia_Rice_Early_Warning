import io
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "noaa"
OUTPUT_PATH = ROOT / "data" / "processed" / "indeks_iklim_bulanan.csv"

ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
DMI_URL = "https://psl.noaa.gov/data/timeseries/month/data/dmi.had.long.data"

START_YEAR = 2016  # 2 tahun sebelum data padi (2018) untuk fitur lag

# ONI = rata-rata 3 bulan bergulir. Nilai "DJF" baru diketahui setelah Februari selesai,
# jadi dipetakan ke bulan TERAKHIR musimnya (bukan bulan tengah) supaya fitur lag
# tidak memakai informasi dari masa depan.
SEASON_LAST_MONTH = {
    "DJF": 2, "JFM": 3, "FMA": 4, "MAM": 5, "AMJ": 6, "MJJ": 7,
    "JJA": 8, "JAS": 9, "ASO": 10, "SON": 11, "OND": 12, "NDJ": 1,
}

ENSO_THRESHOLD = 0.5  # NOAA
IOD_THRESHOLD = 0.4   # Biro Meteorologi Australia


def download(url: str, filename: str) -> str:
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    (RAW_DIR / filename).write_text(resp.text, encoding="utf-8")
    return resp.text


def parse_oni(text: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(text), sep=r"\s+")
    df["bulan"] = df["SEAS"].map(SEASON_LAST_MONTH)
    # "NDJ 2020" = Nov 2020–Jan 2021, jadi bulan terakhirnya ada di tahun berikutnya
    df["tahun"] = df["YR"] + (df["SEAS"] == "NDJ").astype(int)
    df["tanggal"] = pd.to_datetime(dict(year=df["tahun"], month=df["bulan"], day=1))
    return df[["tanggal", "ANOM"]].rename(columns={"ANOM": "oni"})


def parse_dmi(text: str) -> pd.DataFrame:
    rows = []
    for line in text.splitlines()[1:]:  # baris pertama: rentang tahun
        parts = line.split()
        if len(parts) != 13:
            break  # bagian keterangan di akhir file
        for month, value in enumerate(parts[1:], start=1):
            if float(value) > -999:  # -9999 = belum ada data
                rows.append((pd.Timestamp(int(parts[0]), month, 1), float(value)))
    return pd.DataFrame(rows, columns=["tanggal", "dmi"])


def phase(value: float, threshold: float, positive: str, negative: str) -> str:
    # ponytail: ambang per bulan; definisi resmi NOAA butuh 5 musim berturut-turut
    if pd.isna(value):
        return None
    if value >= threshold:
        return positive
    if value <= -threshold:
        return negative
    return "Netral"


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    oni = parse_oni(download(ONI_URL, "oni.ascii.txt"))
    dmi = parse_dmi(download(DMI_URL, "dmi.had.long.data"))

    df = oni.merge(dmi, on="tanggal", how="outer").sort_values("tanggal")
    df = df[df["tanggal"].dt.year >= START_YEAR].reset_index(drop=True)
    df["fase_enso"] = df["oni"].map(lambda v: phase(v, ENSO_THRESHOLD, "El Nino", "La Nina"))
    df["fase_iod"] = df["dmi"].map(lambda v: phase(v, IOD_THRESHOLD, "IOD Positif", "IOD Negatif"))

    expected = pd.date_range(df["tanggal"].min(), df["tanggal"].max(), freq="MS")
    print(f"Periode: {df['tanggal'].min():%Y-%m} s.d. {df['tanggal'].max():%Y-%m}")
    print(f"Bulan hilang: {len(expected) - len(df)}")
    print(f"ONI terakhir: {df.dropna(subset=['oni'])['tanggal'].max():%Y-%m}")
    print(f"DMI terakhir: {df.dropna(subset=['dmi'])['tanggal'].max():%Y-%m}")

    yearly = df.assign(tahun=df["tanggal"].dt.year).groupby("tahun").agg(
        oni_maks=("oni", "max"), oni_min=("oni", "min"), dmi_maks=("dmi", "max"), dmi_min=("dmi", "min"))
    print("\nRingkasan per tahun:")
    print(yearly.round(2).to_string())

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False, date_format="%Y-%m-%d")
    print(f"\nTersimpan: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()