# Indonesia Rice Price Forecasting

Proyeksi harga beras bulanan per provinsi menggunakan Spatio-Temporal Graph
Neural Network, dengan data produksi padi dan iklim sebagai variabel penjelas
yang diuji sumbangannya.

## Masalah

Harga beras adalah harga pangan paling berpengaruh di Indonesia. Beras menjadi
bahan pangan pokok bagi 95 persen penduduk (Rafidah, 2024), dan pergerakannya
terbukti memiliki hubungan kausalitas dengan laju inflasi nasional (Pangesti
dkk., 2023).

Data harga tersedia terbuka dan harian melalui PIHPS Bank Indonesia, tetapi
hanya menampilkan harga yang sudah terjadi. Tidak ada proyeksi terbuka untuk
harga beras per provinsi, dan tidak ada yang menjelaskan mengapa harga bergerak.

## Untuk siapa

Publik umum. Tampilan dasar tidak memerlukan isian apa pun dan dapat dibaca
siapa saja. Tersedia lapisan opsional: pengguna yang membeli dalam volume besar
dapat mengisi konsumsi per bulan untuk melihat perbandingan biaya antara membeli
bulanan dan membeli sekaligus.

Aplikasi ini tidak mengklaim menghemat uang pengguna, mencegah kelangkaan,
maupun mendukung ketahanan pangan nasional.

## Metode

Target: harga beras kualitas medium bulanan per provinsi.

Model yang dibandingkan:

| Model | Menangkap |
|---|---|
| Pembanding naif | Harga bulan sebelumnya |
| Transformers | Pola antarwaktu |
| ST-GNN | Pola antarwaktu dan antarprovinsi |

Dua ablasi:

1. Transformers versus ST-GNN, menjawab apakah hubungan antarprovinsi membantu
2. Tanpa versus dengan fitur produksi dan iklim, menjawab apakah data panen membantu

Evaluasi memakai backtest berurutan waktu, bukan pembagian acak, mengikuti
Cerqueira dkk. (2020).

## Dasar empiris pemilihan rancangan

Struktur graf dipilih setelah diukur, bukan diasumsikan:

| Korelasi antarprovinsi | Harga | Produksi |
|---|---|---|
| Pasangan di bawah 300 km | 0,547 | 0,287 |
| Rata-rata seluruh pasangan | 0,321 | 0,112 |
| Hubungan jarak dengan kemiripan | −0,406 | −0,347 |

Harga tiga kali lebih terhubung antarprovinsi daripada produksi, sehingga
memberi dasar yang jauh lebih kuat bagi pendekatan berbasis graf.

## Data

| Sumber | Isi | Cakupan |
|---|---|---|
| PIHPS Bank Indonesia | Harga beras 6 kelas mutu per provinsi | 2017-03 s.d. 2026-09 |
| BPS (Kerangka Sampel Area) | Luas panen, produksi, fase tanam | 2018-01 s.d. 2026-10 |
| NASA POWER (MERRA-2) | Curah hujan dan suhu per provinsi | 2016-01 s.d. 2026-09 |
| NOAA CPC | Indeks ONI (El Nino / La Nina) | 2016-01 s.d. 2026-08 |

Seluruh pipeline pengambilan data ada di `data_scraping_pipeline/` dan dapat
dijalankan ulang dari nol.

## Yang diuji dan ditolak

Bagian ini sengaja dicantumkan agar keputusan rancangan dapat ditelusuri.

**Neraca beras nasional.** Ditolak karena komponen kebutuhan tidak memiliki
sumber resmi yang dapat dipertanggungjawabkan dan data stok tidak terbuka.

**Harga sebagai alat validasi status produksi.** Diuji di tingkat nasional dan
tidak ditemukan hubungan (korelasi sekitar −0,04). Di tingkat provinsi hubungan
muncul namun lemah (−0,111 pada horizon satu bulan, bertanda negatif di 25 dari
34 provinsi).

**Dugaan bahwa hubungan produksi-harga lebih kuat di provinsi terpencil.**
Diuji dan ditolak; korelasinya justru melemah seiring jarak dari Jakarta (+0,284).

**Fase tanam sebagai fitur model operasional.** Sangat kuat pada lag 1 sampai 3
(korelasi 0,72 hingga 0,77) namun hanya terbit setahun sekali, sehingga pada lag
yang benar-benar tersedia sinyalnya sudah hilang.

## Keterbatasan

- Publikasi produksi BPS terlambat sekitar lima bulan, sehingga fitur produksi
  hanya tersedia pada lag 6 ke atas
- Cakupan 32 provinsi; empat provinsi hasil pemekaran Papua serta DKI Jakarta
  dan Kepulauan Riau dikecualikan karena riwayat terlalu pendek atau bukan
  daerah produksi
- Graf berbasis korelasi dibekukan pada batas periode latih, bukan dihitung
  ulang pada setiap lipatan backtest
- Titik pusat provinsi dihitung dari rata-rata koordinat kabupaten, bukan dari
  batas wilayah sebenarnya

## Struktur
