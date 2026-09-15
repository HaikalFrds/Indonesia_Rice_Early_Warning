from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT / "data" / "interim" / "bps_tabel_bulanan.csv"
OUTPUT_PATH = ROOT / "data" / "processed" / "bps_padi_bulanan_provinsi.csv"

MONTHS = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
    "Agustus", "September", "Oktober", "November", "Desember",
]

# Nama di PDF -> nama lengkap resmi
PROVINCE_NAMES = {
    "Kep. Bangka Belitung": "Kepulauan Bangka Belitung",
    "Kep. Riau": "Kepulauan Riau",
    "NTB": "Nusa Tenggara Barat",
    "NTT": "Nusa Tenggara Timur",
}

# Provinsi hasil pemekaran 2022 -> provinsi induk (supaya bisa dibandingkan dengan 2018–2022)
PARENT_PROVINCE = {
    "Papua Selatan": "Papua",
    "Papua Tengah": "Papua",
    "Papua Pegunungan": "Papua",
    "Papua Barat Daya": "Papua Barat",
}

# "Puso" (edisi 2019–2020) dan "Potensi Gagal Panen" (edisi 2021+) berisi angka yang sama
# untuk tahun 2020, jadi dianggap satu variabel
TOPIC_RENAMES = {"puso": "potensi_gagal_panen"}

# Nama kolom akhir, dengan satuan
COLUMN_NAMES = {
    "luas_panen": "luas_panen_ha",
    "produksi_padi": "produksi_padi_ton_gkg",
    "produksi_beras": "produksi_beras_ton",
    "standing_crop": "standing_crop_ha",
    "vegetatif_awal": "vegetatif_awal_ha",
    "vegetatif_akhir": "vegetatif_akhir_ha",
    "generatif": "generatif_ha",
    "persiapan_lahan": "persiapan_lahan_ha",
    "potensi_gagal_panen": "potensi_gagal_panen_ha",
    "lahan_bera": "lahan_bera_ha",
    "tanaman_selain_padi": "tanaman_selain_padi_ha",
}


def to_long(df: pd.DataFrame) -> pd.DataFrame:
    long = df.melt(
        id_vars=["edisi", "tahun", "topik", "provinsi"],
        value_vars=MONTHS,
        var_name="nama_bulan",
        value_name="nilai",
    )
    long["bulan"] = long["nama_bulan"].map({name: i for i, name in enumerate(MONTHS, start=1)})
    return long.drop(columns="nama_bulan")


def pick_latest_edition(long: pd.DataFrame) -> pd.DataFrame:
    # Edisi terbaru dipakai; sel yang kosong di edisi terbaru diisi dari edisi lebih lama
    return (
        long.dropna(subset=["nilai"])
        .sort_values("edisi", ascending=False)
        .drop_duplicates(subset=["tahun", "bulan", "topik", "provinsi"], keep="first")
    )


def check(wide: pd.DataFrame):
    expected = wide["tahun"].map(lambda year: 34 if year <= 2022 else 38)
    counts = wide.groupby("tanggal")["provinsi"].transform("count")
    print(f"Periode: {wide['tanggal'].min():%Y-%m} s.d. {wide['tanggal'].max():%Y-%m}")
    print(f"Baris: {len(wide)}")
    print(f"Bulan dengan jumlah provinsi tidak sesuai: {(counts != expected).sum()}")

    value_columns = [c for c in COLUMN_NAMES.values() if c in wide.columns]
    missing = wide[value_columns].isna().sum()
    print("\nSel kosong per kolom:")
    print(missing.to_string())

    print("\nProduksi padi nasional per tahun (ton GKG):")
    print(wide.groupby("tahun")["produksi_padi_ton_gkg"].sum().round(0).to_string())


def main():
    raw = pd.read_csv(INPUT_PATH)
    raw = raw[raw["provinsi"].str.upper() != "INDONESIA"]
    raw["provinsi"] = raw["provinsi"].replace(PROVINCE_NAMES)
    raw["topik"] = raw["topik"].replace(TOPIC_RENAMES)

    long = pick_latest_edition(to_long(raw))

    wide = (
        long.pivot_table(index=["tahun", "bulan", "provinsi"], columns="topik", values="nilai")
        .rename(columns=COLUMN_NAMES)
        .reset_index()
    )
    wide.columns.name = None
    wide.insert(0, "tanggal", pd.to_datetime(dict(year=wide["tahun"], month=wide["bulan"], day=1)))
    wide.insert(4, "wilayah_34", wide["provinsi"].replace(PARENT_PROVINCE))
    wide = wide[["tanggal", "tahun", "bulan", "provinsi", "wilayah_34"]
                + [c for c in COLUMN_NAMES.values() if c in wide.columns]]
    wide = wide.sort_values(["tanggal", "provinsi"]).reset_index(drop=True)

    check(wide)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    wide.to_csv(OUTPUT_PATH, index=False, date_format="%Y-%m-%d")
    print(f"\nTersimpan: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()