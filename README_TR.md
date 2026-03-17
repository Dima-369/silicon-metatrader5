# SiliconMetaTrader5 🍏📈
**Professional MetaTrader 5 Solution for macOS Silicon M Series**

🌍 **[Read in English](README.md)**

**Developer:** Bahadir Umut Iscimen


> [!NOTE]
> **Açıklama:** Bu proje bilgisayarınızda yüklü olan ana MetaTrader 5 uygulamasının **yerini almaz**. Sadece Docker üzerinden ayrı bir MT5 çalıştırarak **Python ile haberleşmeyi** ve algoritmik ticareti mümkün kılar.

Bu proje, macOS Silicon cihazlarda MetaTrader 5'i sorunsuz çalıştırmak (`docker`) ve Python ile profesyonel algoritmik trading yapmak (`client`) için geliştirilmiş uçtan uca bir çözümdür.

> [!CAUTION]
> **Kullanım Amacı Hakkında Önemli Not:**
> Bu altyapı, macOS ortamında **strateji geliştirme, backtest ve forward-test** süreçlerinizi konforla yönetmeniz için tasarlanmıştır.
>
> Kritik öneme sahip, milisaniye hassasiyeti gerektiren veya yüksek sermayeli **Canlı (Production)** işlemleriniz için; emülasyon katmanı içermeyen, doğal Windows altyapısına sahip bir Fiziksel PC veya Sunucu kiralanması tavsiye edilir.

> [!WARNING]
> **MetaTrader5 Kaynaklı Bilinen Sorunlar**
>
> MetaTrader5 uygulamasının iç davranışı nedeniyle, tarih tabanlı sorgular kullanıldığında bazı MT5 Python fonksiyonları eski veri döndürebilmektedir:
>
> | Yöntem | Beklenen | Gerçek | Durum |
> |--------|----------|--------|--------|
> | `copy_rates_from_pos()` | Güncel veri | ✅ Güncel veri | **Önerilen** |
> | `copy_rates_from()` | Güncel veri | ❌ Eski veri (1-3 saat geride) | Önerilmez |
> | `copy_rates_range()` | Güncel veri | ❌ Eski veri (1-3 saat geride) | Önerilmez |
>
> **Temel Neden:** MetaTrader5 terminal uygulaması, tarih tabanlı veri isteklerini dahili olarak cache'lemektedir. Pozisyon tabanlı istekler (`copy_rates_from_pos`) her zaman "bar 0" yani canlı güncel bar'ı referans aldığı için MT5 cache'ini atlatmaktadır.
>
> **En İyi Uygulama:** Her zaman yeterli bar sayısı ile `copy_rates_from_pos()` kullanın:
> ```python
> # ✅ Doğru - Her zaman güncel veri döner
> rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_M5, 0, 500)
>
> # ❌ Kaçının - MT5 cache nedeniyle eski veri dönebilir
> rates = mt5.copy_rates_range("EURUSD", mt5.TIMEFRAME_M5, dt_from, dt_to)
> ```

---

## 📂 Proje Yapısı

*   **`docker/`**: MT5'i çalıştıran sanallaştırılmış ortam (Wine + QEMU).
    *   *Kullanılan İmaj (`bahadirumutiscimen/pysiliconwine`), gereksiz yüklerden arındırılmış ve bu proje için özel olarak derlenmiştir.*
*   **`client/`**: MT5 ile haberleşen Python kütüphanesi (`siliconmetatrader5`).
    *   *Bu kütüphane, standart `MetaTrader5` paketinin macOS Silicon mimarisindeki iletişim sorunlarını çözmek için uyarlanmıştır.*
    *   *Tüm fonksiyonlar ve komut yapısı, orijinal `MetaTrader5` Python kütüphanesine %100 sadık kalmıştır. Mevcut kodlarınızı değiştirmeden kullanabilirsiniz.*
*   **`tests/`**: Test dosyaları.
    *   *Bu dosyalar, MT5 ile haberleşen Python kütüphanesinin doğru çalıştığını test etmek için kullanılır.*

## 🏗 Sistem İşleyiş Diyagramı

![System Architecture](assets/system-arch.png)

### 📸 Ekran Görüntüleri
**Localhost Üzerinde Çalışma (VNC):**
![Localhost VNC](assets/localhost.png)

**Python Veri Çekme Testi:**
![Data Fetch](assets/fetch_data.png)

---

## 🚀 Sıfırdan Kurulum

Bilgisayarınızda hiçbir şey kurulu olmadığını varsayarak ilerliyoruz.

### 1. Hazırlık
Terminali açın ve aşağıdaki komutu çalıştırarak gerekli araçları kurun:

```bash
# 1. Homebrew'i kurun (Eğer zaten kuruluysa bu adımı atlayın)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. Gerekli paketleri yükleyin:
brew install colima docker qemu lima lima-additional-guestagents
```

### 2. Motoru Başlatma
Docker'ın macOS Silicon üzerinde x86 (Windows) uygulamalarını çalıştırabilmesi için Colima'yı özel ayarlarla başlatmalıyız.

```bash
# Varsa eski ayarları temizle
colima delete -f

# Performanslı x86 emülasyonu ile başlat
colima start --arch x86_64 --vm-type=qemu --cpu 4 --memory 8
```

### 3. MT5 Sunucusunu Kurma

```bash
cd docker

# Konteyneri başlat (İlk kurulumda 5-10 dk sürebilir)
```bash
# Seçenek 1: Logları görerek başlatma (Önerilen - Sorun varsa görürsünüz)
docker compose up --build

# Seçenek 2: Arka planda sessiz başlatma (Sistem oturduktan sonra)
# docker compose up --build -d
```
*   Terminalde loglar akmaya başladığında işlem tamamdır.
*   Logları durdurmak için `Ctrl+C` yapabilirsiniz (Container kapanır).
*   **Görsel Erişim:** Tarayıcıdan [http://localhost:6081/vnc.html](http://localhost:6081/vnc.html) adresine gidin (Şifre: `123456`).
*   **⏳ Sabırlı Olun:** Docker kurulumu tamamlanma aşamasıyla birlikte, siyah ekrandan MetaTrader 5 ekranına geçiş işlemi (ilk kurulum nedeniyle) **25-30 dakika** sürebilir. Lütfen kapatmadan bekleyiniz.
*   **İlk İşlem:** VNC ekranında MT5 açılınca, **File > Open an Account** diyerek Broker'ınızı aratın ve bir kez manuel giriş yapın.

*(Bu terminal penceresini açık bırakın veya yeni bir terminal sekmesi açın)*

### 4. Python İstemcisini Kurma

Apple Silicon (M1/M2/M3) mimarisi için özel olarak optimize ettiğimiz istemci kütüphanesini kurun:

```bash
pip install siliconmetatrader5
```

### 5. Bağlantıyı Test Etme

Her şeyin çalıştığını doğrulamak için örnek scriptimizi çalıştıralım:

```bash
python tests/test_fetch.py 
python tests/test_plot.py
```
*Çıktı olarak "Connected" veya terminal bilgilerini görüyorsanız başardınız!* 🎉

---

## 📊 Örnek Kullanım

Artık kendi Python botunuzu yazabilirsiniz. İşte basit bir örnek:

```python
from siliconmetatrader5 import MetaTrader5
import pandas as pd

# Bağlan
mt5 = MetaTrader5(host="localhost", port=8001)

# Veri Çek
print("EURUSD M15 Verisi çekiliyor...")
rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_M15, 0, 100)
df = pd.DataFrame(rates)
print(df.tail())

# İşin bitince kapat
mt5.shutdown()
```

### 🆕 Versiyon 1.1.0 Yeni Özellikler

#### Keepalive Desteği (Uzun Süreli Uygulamalar İçin)
Saatlerce bağlı kalması gereken monitor/bot scriptleri çalıştırıyorsanız, bağlantı timeout'unu önlemek için keepalive'ı aktif edin:

```python
# Uzun süreli monitor/botlar için - bağlantı timeout'unu önler
mt5 = MetaTrader5(host="localhost", port=8001, keepalive=True)
```

| Parametre | Varsayılan | Açıklama |
|-----------|------------|----------|
| `keepalive` | `False` | Bağlantıyı canlı tutmak için arka plan thread'i başlatır |

> **Not:** `keepalive` parametresini yazmazsanız, varsayılan olarak `False` değeri kullanılır. Mevcut kodlarınız değişiklik yapmadan çalışmaya devam eder.

#### Bağlantı Sağlık Kontrolü
Artık bağlantının canlı olup olmadığını kontrol edebilirsiniz:

```python
mt5 = MetaTrader5(host="localhost", port=8001)

# Bağlantı sağlık kontrolü
if mt5.ping():
    print("Bağlantı canlı!")
else:
    print("Bağlantı kopmuş, yeniden bağlanılıyor...")
    mt5.initialize()
```

#### Genişletilmiş Timeout
Bağlantı timeout süresi 5 dakikadan 10 dakikaya çıkarıldı. `keepalive=False` (varsayılan) durumunda, bağlantı 10 dakika işlem yapılmazsa otomatik kapanır.

---

## 🛠 Günlük Kullanım Rutini

Bilgisayarı kapattınız, sabah tekrar açtığınızda yapmanız gerekenler sadece şunlardır:

1.  **Motoru Aç:** `colima start` (Ayarları hatırlar)
2.  **MT5'i Başlat:** `cd docker && docker compose up` (veya sessiz mod için `-d` ekleyin)

### 🛑 Durdurma ve Kapatma

*   **Sadece MT5'i Durdur:** `Ctrl+C` (veya `docker compose down`)
*   **Komple Sistemi Kapat (RAM boşaltır):** `colima stop`

### ♻️ Sıfırlama (Fabrika Ayarlarına Dönüş)
Eğer her şeyi silip en baştan başlamak isterseniz (Tüm veriler silinir!):

```bash
colima delete
colima start --arch x86_64 --vm-type=qemu --cpu 4 --memory 8
```

---

## 🛑 Karşılaşılan Zorluklar ve Çözümleri
Bu proje, macOS Silicon üzerinde x86 uygulaması çalıştırmanın zorluklarını aşmak için özel olarak tasarlanmıştır.

1.  **Architecture Mismatch:** Mac'in Rosetta 2'si yerine **QEMU** tabanlı tam x86_64 emülasyonu (Colima) kullanılarak çökme sorunları çözülmüştür.
2.  **IPC Timeout:** Emülasyonun doğal yavaşlığı nedeniyle Python bağlantılarında kopmalar yaşanabilir. Bu yüzden kodlarımızda özel "Retry" (tekrar deneme) mekanizmaları bulunur.
3.  **SSL/TLS:** Wine ortamına `winbind` ve sertifika kütüphaneleri eklenerek broker sunucularıyla güvenli iletişim sağlanmıştır.

## ⚙️ Gelişmiş Ayarlar (Timezone & Ekran)

### 🌍 Saat Dilimi (Timezone) Değiştirme
Varsayılan olarak "Europe/Istanbul" ayarlıdır. Değiştirmek için `docker/compose.yaml` dosyasını düzenleyin:

```yaml
# docker/compose.yaml
environment:
  - TZ=America/New_York  # Veya UTC, Asia/Tokyo vb.
```
ℹ️ **Dünya Saatleri Listesi:** [Wikipedia Timezone List](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)

### 🖥 Ekran Çözünürlüğü ve Pencere
Ekran boyutunu (şu an 1366x768) değiştirmek veya **Pencere Çerçevelerini (Openbox)** açmak için `docker/start.sh` dosyasını düzenleyin:

```bash
# docker/start.sh
# Çözünürlük Değiştirme (Satır 11)
Xvfb :100 -ac -screen 0 1366x768x24 &

# Çerçeve ve Pencere Yönetimi (Satır 18)
# openbox &  <-- Başındaki # işaretini kaldırırsanız pencereleri sürükleyebilirsiniz.
```
*⚠️ **Performans Uyarısı:** Pencere yöneticisinin (Openbox) açılması, ek grafik işlemi gerektirdiği için VNC akıcılığını bir miktar düşürebilir (Latency artışı).*

*Not: Bu değişikliklerden sonra `docker compose up --build` ile yeniden kurmalısınız.*

## 🛠 Sık Sorulan Sorular

**S: Bilgisayarımı kapattım, tekrar nasıl açacağım?**
C: Sırasıyla:
1.  `colima start --arch x86_64 --vm-type=qemu --cpu 4 --memory 8`
2.  `cd docker && docker compose up` (Sessiz mod için `-d` ekleyebilirsiniz)

**S: Docker'ı (MT5'i) nasıl durdururum?**
C: Çalışan terminalde `Ctrl+C` tuş kombinasyonunu kullanabilir veya (başka bir terminalden) şu komutu verebilirsiniz:
`cd docker && docker compose down`

**S: Sadece MT5'i (Docker'ı) durdurdum, nasıl tekrar başlatırım?**
C: Colima zaten çalışıyorsa iki seçeneğiniz vardır:
*   **Hızlı Başlatma:** Eğer ayarlarda (start.sh, Dockerfile vb.) hiçbir değişiklik yapmadıysanız:
    `cd docker && docker compose up`
*   **Güncelleyerek Başlatma:** Eğer bir ayar değiştirdiyseniz veya emin değilseniz (Önerilen):
    `cd docker && docker compose up --build`

**S: MT5 ekranı siyah kalıyor?**
C: Colima'nın QEMU modunda başlatıldığından emin olun (Adım 2'deki komut).

**S: Ping n/a yazıyor / Bağlanmıyor?**
C: VNC ile bağlanın (`http://localhost:6081/vnc.html`), `File > Open an Account` diyerek Broker isminizi aratın ve bir kereye mahsus giriş yapın.

**Web Arabirimi Şifresi:** `123456`
