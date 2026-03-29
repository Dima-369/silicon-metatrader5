<div align="center">

# ⚡ SiliconMetaTrader5 🍏📈
**macOS Apple Silicon için Ultimate MetaTrader 5 & Python Çözümü**

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![Apple Silicon](https://img.shields.io/badge/Apple_Silicon-M1%2FM2%2FM3%2FM4&2FM5-black?style=for-the-badge&logo=apple&logoColor=white)]()
[![Version](https://img.shields.io/badge/Version-1.2.1-brightgreen.svg?style=for-the-badge)]()

**Geliştirici:** Bahadir Umut Iscimen | 🌍 **[Read in English](README.md)**

---

</div>

> [!NOTE]  
> 💡 **Açıklama:** Bu proje bilgisayarınızdaki native MetaTrader 5 uygulamasının **yerine geçmez**. macOS üzerinde Python iletişimi ve algoritmik işlem için Docker içinde ayrı, headless (arayüzsüz arka plan) bir MT5 instance’ı çalıştırır. Bu proje, MT5’i macOS Silicon cihazlarda (Docker) sorunsuz çalıştırmak ve Python (istemci) ile profesyonel algoritmik trading yapmak için uçtan uca geliştirilmiştir.

> [!CAUTION]  
> ⚠️ **Kullanım Amacı ve Üretim (Production) Uyarısı:** Bu altyapı, strateji geliştirme, backtesting ve forward-testing süreçlerini macOS ortamında son derece konforlu yönetmek için tasarlanmıştır. Ancak, milisaniye hassasiyeti gerektiren, kritik veya yüksek sermayeli **canlı (live/production) trading** için emülasyon katmanı içermeyen, native Windows kurulu fiziksel bir PC veya sunucu kullanmanız kesinlikle önerilir.

---

## 📦 Bu Repoda Neler Var?

* 🐳 **`docker/`** : Wine + QEMU üzerinde çalışan yüksek performanslı MT5 runtime.
* 🐍 **`client/`** : Özel Python istemci paketi (`siliconmetatrader5`).
* 🧪 **`tests/`** : Doğrulama ve bağlantı sağlığı scriptleri.

---

## 🏗 Sistem Mimari ve Akış Diyagramı

Apple Silicon, Docker Emülasyonu ve Python arasındaki köprünün görselleştirilmesi.

![Sistem Mimarisi](assets/system-arch.png)

### 📸 Ekran Görüntüleri
<div align="center">
  <img src="assets/localhost.png" width="45%" alt="Localhost VNC">
  <img src="assets/fetch_data.png" width="45%" alt="Veri Çekme">
  <br>
  <i>Solda: Localhost (VNC) Üzerinde Çalışma | Sağda: Python ile Veri Çekme</i>
</div>

---

## 📡 Veri Çekme Yöntemleri

Senaryonuza uygun doğru yöntemi seçin:

| 🎯 Senaryo | 🛠 Önerilen Yöntem |
| :--- | :--- |
| **Canlı (Live) Monitor / Güncel Bar** | `copy_rates_from_pos()` |
| **Backtest / Geçmiş Tarih Aralığı** | `copy_rates_from()` / `copy_rates_range()` |

**Örnek Uygulama:**
```python
# 🟢 Canlı Veri Çekme
live_rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_M5, 0, 500)

# 🕒 Geçmiş Veri (Backtest)
hist_rates = mt5.copy_rates_range("EURUSD", mt5.TIMEFRAME_M5, dt_from, dt_to)
```

---

## 🚀 Sıfırdan Kurulum (Zero-to-Hero)

Bu adımlarda bilgisayarınızda hiçbir şey kurulu değilmiş gibi ilerliyoruz.

### 1️⃣ Hazırlık
Terminali açın ve temel araçları kurun:

```bash
# 1. Homebrew kur (zaten kuruluysa atla)
/bin/bash -c "$(curl -fsSL [https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh](https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh))"

# 2. Gerekli emülasyon ve container paketlerini kur
brew install colima docker qemu lima lima-additional-guestagents
```

### 2️⃣ Emülasyon Motorunu Başlat (Colima)
Apple Silicon üzerinde MT5 runtime bileşenlerinin doğru çalışması için Colima'yı **x86_64 emülasyon** ile başlatıyoruz.

```bash
# Opsiyonel: Mevcut Colima durumu bozuksa sıfırlamak için
# colima delete -f

colima start --arch x86_64 --vm-type=qemu --cpu 4 --memory 8
```

### 3️⃣ MT5 Sunucusunu Kur ve Başlat 
```bash
cd docker

# Seçenek A: Foreground (İlk kurulumda önerilir, logları canlı görürsünüz)
docker compose up --build

# Seçenek B: Detached (Sistem stabil olduktan sonra arka planda çalıştırmak için)
# docker compose up --build -d
```

> [!IMPORTANT]
> **Başlatma İçin Önemli Notlar:**
> * ⏳ **Build Süresi:** İlk kurulum yaklaşık **5-10 dakika** sürebilir.
> * 🖥 **Arayüzün Açılması:** İlk açılışta siyah ekrandan MT5 arayüzüne geçiş **25-30 dakikayı** bulabilir.
> * 🌐 **Görsel Erişim:** [http://localhost:6081/vnc.html](http://localhost:6081/vnc.html) adresine gidin (Şifre: `123456`).
> * 🔑 **İlk İşlem:** MT5 açıldığında `File > Open an Account` yolunu izleyerek brokerınızı bulun ve bir kez manuel giriş yapın.
> * 📊 **Veri Senkron Uyarısı:** Broker girişinden sonra geçmiş bar verileri arka planda yüklenir. Test/bot başlatmadan önce **5-10 dakika** bekleyin; ilk dakikalarda `No data` görmek normaldir. `MaxBars` değeri ne kadar büyükse bu ilk senkron süresi o kadar uzayabilir.
> * ⚠️ **Uyarı:** Colima çalışıyor olsa bile container durdurulursa, yeniden başlatıldığında MT5 tekrar giriş (login) isteyebilir.

### 4️⃣ Python İstemcisini (Client) Kur
Python ortamınızı yeni Docker instance'ına bağlayın:
```bash
python3 -m pip install --upgrade siliconmetatrader5
```

### 5️⃣ Bağlantıyı Test Et
Veri akışının sorunsuz olduğunu doğrulamak için dahili testleri çalıştırın:
```bash
python tests/test_fetch.py
python tests/test_plot.py
```
*Terminalde başarılı bağlantı ve veri çıktıları görüyorsanız, botlarınızı yazmaya hazırsınız! 🎉*

---

## ⚙️ Gelişmiş Ayarlar

### 🌍 Zaman Dilimini (Timezone) Değiştirme
Varsayılan container zaman dilimi `Europe/Istanbul`'dur. Değiştirmek için `docker/compose.yaml` dosyasını düzenleyin:
```yaml
environment:
  - TZ=America/New_York  # Seçenekler: UTC, Asia/Tokyo vb.
```
*(Not: Bu ayar broker sunucu saatinizi **değiştirmez**. Yalnızca Linux/VNC katmanının saatini ayarlar.)*

### 🖥 Ekran Çözünürlüğü ve Performans
Görsel ayarları `docker/start.sh` dosyasından düzenleyebilirsiniz:
```bash
# Çözünürlük örneği
Xvfb :100 -ac -screen 0 1366x768x24 &

# Pencere yöneticisi (Opsiyonel - VNC akıcılığını bir miktar düşürebilir)
# openbox &
```
*Değişiklikleri uygulamak için:* `cd docker && docker compose up --build -d`

### 📊 MT5 Geçmiş Derinliği (MaxBars)
Ağır backtest işlemleri için daha derin bar geçmişine erişmek isterseniz `docker/mt5cfg.ini` dosyasını düzenleyin:
```ini
MaxBars=5000  # Seçenekler: 500000, 100000, 250000, 500000, 1000000
```
*(Trade-off: Daha yüksek bellek/depolama kullanımı ve senkronizasyon süresinde hafif uzama.)*

---

## 💻 Örnek Kullanım

Hemen veri çekmeye başlamak için hızlı bir taslak:

```python
import pandas as pd
from siliconmetatrader5 import MetaTrader5

# Bridge'i Başlat
mt5 = MetaTrader5(host="localhost", port=8001, keepalive=True)

if not mt5.initialize():
    raise RuntimeError("🚨 MT5 başlatılamadı!")

# Canlı Veri Çekimi
rates_live = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_M15, 0, 150)
print(pd.DataFrame(rates_live).tail())

# Güvenli Çıkış
mt5.close()  # Sadece bu sürecin bağlantısını kapatır
```

---

## 🆕 Client Güncellemeleri (Önemli)

Sürümünüzü kontrol edin: `python3 -m pip show siliconmetatrader5`

### 🛠 Temel İyileştirmeler
1. **Bağlantı Döngüsü (`close` vs `shutdown`):**
   * `close()` yalnızca mevcut sürecin bağlantısını koparır.
   * `shutdown()` / `close(remote_shutdown=True)` uzak MT5 terminalini tamamen kapatır (Çoklu bot senaryolarında dikkatli kullanın).
2. **Timeout Semantiği:** Aktif per-call (çağrı başı) timeout davranışı kaldırıldı. Uzun süreli çalışan botlar için `keepalive=True` kullanılması önerilir.
3. **Watchdog Desteği:** Donuk/yanıt vermeyen köprü durumlarını tespit etmek için `start_watchdog(...)`, `stop_watchdog()` ve `health_status()` eklendi.
4. **Güvenilirlik:** Wrapper'larda doğrudan uzak çağrı (remote call) yönlendirmesi, normalize edilmiş hata kodları (`TIMEOUT`, `CONNECTION_CLOSED`) ve `market_book_release(symbol)` argüman iletim düzeltmesi yapıldı.

---

## 🛡 Karşılaşılan Zorluklar ve Mimari Çözümler
* **Mimari Uyumsuzluk:** Rosetta tabanlı çökme sorunları (crash), tam **x86_64 emülasyonu (QEMU tabanlı Colima)** kullanılarak büyük ölçüde azaltıldı.
* **IPC Timeout Paternleri:** Emülasyon yükü altında oluşabilecek Python-MT5 kopmalarını önlemek için istemci (client) tarafına "retry" (yeniden deneme) odaklı stabilite mekanizmaları eklendi.
* **SSL/TLS Uyumu:** Broker bağlantı güvenilirliği, gerekli Windows/Wine bağımlılıklarının (winbind/sertifika bileşenleri) entegre edilmesiyle sağlandı.

---

## 🔁 Günlük Rutin

**▶️ Sistemi Başlatma:**
```bash
if colima status 2>/dev/null | grep -q "colima is running"; then
  echo "Colima zaten çalışıyor 🟢"
else
  colima start
fi
cd docker && docker compose up -d
```

**⏹ Sistemi Güvenle Durdurma:**
```bash
cd docker && docker compose down
colima stop
```

---

## ❓ SSS (Sıkça Sorulan Sorular)

**S: Mac'imi yeniden başlattım, ne çalıştırmalıyım?**
> Reponun kök dizininde günlük başlatma scriptini çalıştırın. Önce Colima'nın başladığından emin olun, ardından Docker compose'u tetikleyin.

**S: MT5 ekranı VNC üzerinden siyah kalıyor, ne yapmalıyım?**
> Colima'nın `QEMU/x86_64` modunda çalıştığını doğrulayın. Sistemi detached moddan çıkarıp terminalde `docker compose up --build` çalıştırarak olası başlatma hatalarını inceleyin.

**S: MT5’i güvenli bir şekilde nasıl tamamen kapatırım?**
> Container'ların düzgünce kapanması için `cd docker && docker compose down` çalıştırın.

---

## ☕ Projeye Destek Olun

Bu proje size zaman kazandırıyorsa veya trading workflow'unuza katkı sağlıyorsa, TRC20 ağında USDT ile destek olabilirsiniz.

**☕ USDT (TRC20) ile destek olun**
```text
TMh8eS5EPRL77Z7L4KhsKmccSNLgf6Rfta
```

---

<div align="center">
  <i>Apple Silicon algoritmik trade topluluğu için ☕ ve kod ile geliştirilmiştir.</i>
</div>
