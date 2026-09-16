import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
POINTS_PATH = ROOT / "data" / "processed" / "titik_kabupaten.csv"
RAW_DIR = ROOT / "data" / "raw" / "nasa_power"
OUTPUT_PATH = ROOT / "data" / "processed" / "cuaca_bulanan_provinsi.csv"

API_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
START_DATE = "20160101"  # 2 tahun sebelum data padi (2018) untuk fitur lag
FILL_VALUE = -999.0

# Resolusi grid asli NASA POWER (MERRA-2)
GRID_LAT, GRID_LON = 0.5, 0.625

COLUMNS = {
    "PRECTOTCORR": "curah_hujan_mm",
    "T2M": "suhu_rata_c",
    "T2M_MAX": "suhu_maks_c",
    "T2M_MIN": "suhu_min_c",
}


def fetch_daily(lat: float, lon: float) -> pd.DataFrame:
    params = {
        "parameters": ",".join(COLUMNS),
        "community": "AG",
        "latitude": lat,
        "longitude": lon,
        "start": START_DATE,
        "end": date.today().strftime("%Y%m%d"),
        "format": "JSON",
    }
    for attempt in range(3):
        try:
            resp = requests.get(API_URL, params=params, timeout=180)
            resp.raise_for_status()
            break
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(10 * (attempt + 1))
    df = pd.DataFrame(resp.json()["properties"]["parameter"]).rename(columns=COLUMNS)
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df.index.name = "tanggal"
    return df.replace(FILL_VALUE, float("nan"))  # -999 = belum ada data


def load_cell(lat: float, lon: float) -> pd.DataFrame:
    path = RAW_DIR / f"sel_{lat}_{lon}.csv"
    # ponytail: file yang sudah diambil hari ini dipakai ulang (untuk melanjutkan kalau terputus)
    if path.exists() and date.fromtimestamp(path.stat().st_mtime) == date.today():
        return pd.read_csv(path, index_col="tanggal", parse_dates=["tanggal"])
    daily = fetch_daily(lat, lon)
    daily.to_csv(path)
    time.sleep(1)  # jeda antar-request
    return daily


def to_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    monthly = daily.resample("MS").agg({
        "curah_hujan_mm": lambda s: s.sum(min_count=1),  # hujan: dijumlah
        "suhu_rata_c": "mean",                            # suhu: dirata-rata
        "suhu_maks_c": "mean",
        "suhu_min_c": "mean",
    })
    monthly["hari_data"] = daily["curah_hujan_mm"].resample("MS").count()
    return monthly


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    points = pd.read_csv(POINTS_PATH)
    points["sel_lat"] = (points["lat"] / GRID_LAT).round() * GRID_LAT
    points["sel_lon"] = (points["lon"] / GRID_LON).round() * GRID_LON

    cells = points[["sel_lat", "sel_lon"]].drop_duplicates().itertuples(index=False)
    cells = list(cells)
    print(f"{len(points)} kab/kota -> {len(cells)} sel grid")

    monthly_by_cell = {}
    for i, (lat, lon) in enumerate(cells, start=1):
        monthly_by_cell[(lat, lon)] = to_monthly(load_cell(lat, lon))
        if i % 25 == 0 or i == len(cells):
            print(f"  {i}/{len(cells)} sel selesai")

    # Setiap kab/kota mendapat cuaca sel grid-nya, lalu dirata-rata per provinsi
    frames = []
    for row in points.itertuples(index=False):
        monthly = monthly_by_cell[(row.sel_lat, row.sel_lon)].copy()
        monthly["provinsi"] = row.provinsi
        frames.append(monthly)

    df = (
        pd.concat(frames)
        .reset_index()
        .groupby(["tanggal", "provinsi"])
        .agg(
            curah_hujan_mm=("curah_hujan_mm", "mean"),
            suhu_rata_c=("suhu_rata_c", "mean"),
            suhu_maks_c=("suhu_maks_c", "mean"),
            suhu_min_c=("suhu_min_c", "mean"),
            n_kab_kota=("provinsi", "size"),
            hari_data=("hari_data", "min"),
        )
        .round(2)
        .reset_index()
    )

    print(f"\nPeriode: {df['tanggal'].min():%Y-%m} s.d. {df['tanggal'].max():%Y-%m}, "
          f"{df['provinsi'].nunique()} provinsi, {len(df)} baris")
    partial = df[df["hari_data"] < df["tanggal"].dt.days_in_month]["tanggal"].dt.strftime("%Y-%m").unique()
    print(f"Bulan belum lengkap: {list(partial)}")
    print(f"Sel kosong: {df[['curah_hujan_mm', 'suhu_rata_c']].isna().sum().to_dict()}")

    complete = df[(df["tanggal"] >= "2018-01-01") & (df["tanggal"] < "2026-01-01")]
    yearly = complete.groupby("provinsi").agg(
        hujan_tahunan_mm=("curah_hujan_mm", lambda s: s.sum() / 8),
        suhu_rata_c=("suhu_rata_c", "mean"),
    ).sort_values("hujan_tahunan_mm")
    print("\nRata-rata 2018-2025 per provinsi (terkering ke terbasah):")
    print(yearly.round(1).to_string())

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False, date_format="%Y-%m-%d")
    print(f"\nTersimpan: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()