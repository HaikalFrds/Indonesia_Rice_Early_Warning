from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "data" / "processed"
OUTPUT_PATH = DIR / "dataset_gabungan.csv"

# Cuaca dan ONI mulai 2016, produksi baru 2018. Selisih dua tahun sengaja disimpan
# supaya nanti tersedia bahan lag untuk baris produksi paling awal (Januari 2018).
AWAL = "2016-01-01"


def main():
    padi = pd.read_csv(DIR / "padi_bulanan_provinsi.csv", parse_dates=["tanggal"])
    cuaca = pd.read_csv(DIR / "cuaca_bulanan_provinsi.csv", parse_dates=["tanggal"])
    iklim = pd.read_csv(DIR / "indeks_iklim_bulanan.csv", parse_dates=["tanggal"])

    assert set(padi.provinsi) == set(cuaca.provinsi), "daftar provinsi padi dan cuaca berbeda"
    for nama, df, kunci in (("padi", padi, ["tanggal", "provinsi"]),
                            ("cuaca", cuaca, ["tanggal", "provinsi"]),
                            ("iklim", iklim, ["tanggal"])):
        assert not df.duplicated(kunci).any(), f"{nama} punya baris ganda"

    akhir = max(padi.tanggal.max(), cuaca.tanggal.max(), iklim.tanggal.max())
    bulan = pd.date_range(AWAL, akhir, freq="MS")
    kerangka = pd.MultiIndex.from_product(
        [bulan, sorted(padi.provinsi.unique())], names=["tanggal", "provinsi"]
    ).to_frame(index=False)

    df = (kerangka
          .merge(padi.drop(columns=["tahun", "bulan"]), on=["tanggal", "provinsi"], how="left")
          .merge(cuaca, on=["tanggal", "provinsi"], how="left")
          .merge(iklim, on="tanggal", how="left"))

    df.insert(1, "tahun", df.tanggal.dt.year)
    df.insert(2, "bulan", df.tanggal.dt.month)
    df = df.sort_values(["provinsi", "tanggal"]).reset_index(drop=True)

    df.to_csv(OUTPUT_PATH, index=False)

    print(f"{len(df)} baris, {df.provinsi.nunique()} provinsi, "
          f"{df.tanggal.min():%Y-%m} s.d. {df.tanggal.max():%Y-%m}\n")

    ada = df.notna().groupby(df.tahun).sum()
    ringkas = pd.DataFrame({
        "produksi": ada["produksi_padi_ton_gkg"],
        "fase_tanam": ada["generatif_ha"],
        "cuaca": ada["curah_hujan_mm"],
        "oni": ada["oni"],
    })
    print("jumlah baris terisi per tahun (dari 38 provinsi x 12 bulan = 456):")
    print(ringkas.to_string())
    print(f"\nTersimpan: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()