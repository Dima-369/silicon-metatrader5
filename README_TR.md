# SiliconMetaTrader5 🍏📈
**macOS Apple Silicon için MetaTrader 5 çözümü**

🌍 **[Read in English](README.md)**

**Developer:** Bahadir Umut Iscimen

> [!NOTE]
> Açıklama: Bu proje bilgisayarınızdaki native MetaTrader 5 uygulamasının yerine geçmez.
> macOS üzerinde Python iletişimi ve algoritmik işlem için Docker içinde ayrı, headless bir MT5 instance’ı çalıştırır.
> Bu proje, MetaTrader 5’i macOS Silicon cihazlarda (Docker) sorunsuz çalıştırmak ve Python (client) ile profesyonel algoritmik trading yapmak için uçtan uca geliştirilmiştir.

> [!CAUTION]
> Kullanım amacı notu: Bu altyapı, strateji geliştirme, backtesting ve forward-testing süreçlerini macOS ortamında konforlu yönetmek için tasarlanmıştır.
> Milisaniye hassasiyeti gerektiren, kritik veya yüksek sermayeli live (production) trading için emülasyon katmanı içermeyen native Windows fiziksel PC/server kiralamanız önerilir.

---

## Bu repoda neler var?

- `docker/`: Wine + QEMU üzerinde MT5 runtime
- `client/`: Python istemci paketi (`siliconmetatrader5`)
- `tests/`: doğrulama scriptleri

---


## Sistem Akış Diyagramı

![Sistem Mimarisi](assets/system-arch.png)

### Ekran Görüntüleri
**Localhost (VNC) Üzerinde Çalışma:**
![Localhost VNC](assets/localhost.png)

**Python Veri Çekme:**
![Veri Çekme](assets/fetch_data.png)

---

## Veri yöntemleri: senaryoya göre seçin

| Senaryo | Önerilen yöntem |
|---|---|
| Live monitor / güncel bar | `copy_rates_from_pos()` |
| Backtest/history tarih aralığı | `copy_rates_from()` / `copy_rates_range()` |

```python
# live
live_rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_M5, 0, 500)

# backtest/history
hist_rates = mt5.copy_rates_range("EURUSD", mt5.TIMEFRAME_M5, dt_from, dt_to)
```

---

## Sıfırdan Kurulum (Zero-to-Hero)

Bu adımlarda bilgisayarınızda hiçbir şey kurulu değilmiş gibi ilerliyoruz.

### 1) Hazırlık

Terminal açın ve gerekli araçları kurun:

```bash
# 1) Homebrew kur (zaten kuruluysa atla)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2) Gerekli paketleri kur
brew install colima docker qemu lima lima-additional-guestagents
```

### 2) Motoru başlat (Colima)

Apple Silicon üzerinde MT5 runtime bileşenlerinin doğru çalışması için Colima'yı x86_64 emülasyon ile başlatıyoruz.

```bash
# Opsiyonel reset (yalnızca daha önce siliconmetatrader5 için colima kurduysanız
# veya mevcut Colima durumu bozuk görünüyorsa)
# colima delete -f

colima start --arch x86_64 --vm-type=qemu --cpu 4 --memory 8
```

### 3) MT5 server'ı kur ve başlat

```bash
cd docker

# Seçenek 1: Foreground (ilk kurulumda önerilir, logları canlı görürsünüz)
docker compose up --build

# Seçenek 2: Detached (sistem stabil olduktan sonra)
# docker compose up --build -d
```

Notlar:
- İlk build süresi yaklaşık 5-10 dakika sürebilir.
- İlk açılışta siyah ekrandan MT5 ekranına geçiş 25-30 dakikayı bulabilir.
- `docker compose up` foreground çalışıyorsa, `Ctrl+C` compose oturumunu ve container'ları durdurur.
- Detached modda çalışıyorsanız `docker compose logs -f` kullanın; burada `Ctrl+C` sadece log akışını kapatır.
- Görsel erişim: [http://localhost:6081/vnc.html](http://localhost:6081/vnc.html) (şifre: `123456`).
- İlk aksiyon: MT5 açılınca `File > Open an Account` ile brokerınızı bulun ve bir kez manuel login olun.
- Uyarı: Bilgisayarınızda Colima çalışıyor olsa bile Docker/MT5 container'ı durmuşsa, container'ı tekrar başlattığınızda MT5 yeniden login isteyebilir.
- Bu terminali açık bırakın (veya yeni terminal sekmesinden devam edin).

### 4) Python client kur

Client paketini kur/güncelle:

```bash
python3 -m pip install --upgrade "siliconmetatrader5==1.2.0"
```

### 5) Bağlantıyı test et

```bash
python tests/test_fetch.py
python tests/test_plot.py
```

Terminalde bağlantı/veri akışı başarılı görünüyorsa kurulum tamamdır.

---

## Karşılaşılan Zorluklar ve Çözümler

Bu proje, macOS Silicon üzerinde x86 iş yükü çalıştırmanın pratik zorluklarını yönetmek için tasarlandı.

- Mimari uyumsuzluk: çökme sorunları, Rosetta-only davranışına güvenmek yerine QEMU tabanlı tam x86_64 emülasyon (Colima) ile azaltıldı.
- IPC timeout paternleri: emülasyon yükü altında Python-MT5 kopmaları yaşanabilir; istemci tarafında stabilite için retry odaklı davranış bulunur.
- SSL/TLS uyumu: broker bağlantı güvenilirliği, gerekli Windows/Wine bağımlılıkları (winbind/sertifika bileşenleri gibi) dahil edilerek iyileştirildi.

---

## Gelişmiş Ayarlar (Timezone & Ekran)

### Zaman dilimini değiştirme

Varsayılan `Europe/Istanbul`. Değiştirmek için `docker/compose.yaml` dosyasını düzenleyin:

```yaml
# docker/compose.yaml
environment:
  - TZ=America/New_York  # veya UTC, Asia/Tokyo vb.
```

Referans: [Wikipedia Time Zone List](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)

### Ekran çözünürlüğü ve pencere davranışı

`docker/start.sh` dosyasını düzenleyin:

```bash
# docker/start.sh
# Çözünürlük örneği
Xvfb :100 -ac -screen 0 1366x768x24 &

# Pencere yöneticisi (opsiyonel)
# openbox &
```

Performans uyarısı: pencere yöneticisini (Openbox) açmak ek grafik yükü oluşturur; VNC akıcılığını bir miktar düşürebilir (gecikme artışı).

Değişiklikleri uygulamak için:

```bash
cd docker && docker compose up --build -d
```

---

## MT5 Geçmiş Derinliği (MaxBars)

Dosya: `docker/mt5cfg.ini`

Aşağıdaki değeri:

```ini
MaxBars=5000
```

şu seçeneklerden birine çıkarabilirsiniz:

- `100000`
- `250000`
- `500000`
- `1000000`

Etkisi:
- Backtest/history akışlarında daha derin bar geçmişine erişim sağlanır.
- Uzun lookback kullanan live hesaplamalarda da daha geniş veri penceresi elde edilir.

Trade-off:
- Daha yüksek bellek/depolama kullanımı ve daha yavaş başlangıç/senkron süresi olabilir.

`MaxBars` değişiminden sonra container'ları yeniden build/restart edin:

```bash
cd docker && docker compose up --build -d
```

## Örnek kullanım

```python
from siliconmetatrader5 import MetaTrader5

mt5 = MetaTrader5(host="localhost", port=8001, keepalive=True)

if not mt5.initialize():
    raise RuntimeError("MT5 initialize failed")

rates_live = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_M15, 0, 150)
print(len(rates_live))

mt5.close()  # sadece bu sürecin bağlantısını kapatır
```

---

## Client v1.2.0 (Önemli)

### Python istemci güncelleme

Bu sürümü almak için:

```bash
python3 -m pip install --upgrade "siliconmetatrader5==1.2.0"
python3 -m pip show siliconmetatrader5
```

Beklenen: `Version: 1.2.0`

---

### Ana davranış değişiklikleri

1. `close()` ve `shutdown()` ayrımı
- `close()` yalnızca bu sürecin bağlantısını kapatır.
- `shutdown()` / `close(remote_shutdown=True)` uzak MT5 terminalini global kapatır.

Bot1/Bot2/Bot3 pratik senaryosu:

- Bot1 = monitor
- Bot2 = trade
- Bot3 = history/backtest

Bot1/Bot2/Bot3 normal çıkışta sadece `close()` kullanmalıdır.
Global kapatma sadece orchestrator süreç tarafından `shutdown()` (veya `close(remote_shutdown=True)`) ile yapılmalıdır.

2. Timeout semantiği
- `timeout` geriye uyumluluk için kabul edilir.
- Aktif per-call timeout davranışı kaldırılmıştır.
- Uzun süreli botlarda `keepalive=True` önerilir.

3. Watchdog desteği
- `start_watchdog(...)`, `stop_watchdog()`, `health_status()`
- Donuk/yanıt vermeyen bridge durumunu tespit eder.

4. Güvenilirlik iyileştirmeleri
- wrapper’larda doğrudan remote call dispatch
- normalize hata kodları (`TIMEOUT`, `RESULT_EXPIRED`, `CONNECTION_CLOSED`, `RPC_ERROR`)
- `market_book_release(symbol)` argüman iletim düzeltmesi

---

## Günlük rutin

Başlat:

```bash
if colima status 2>/dev/null | grep -q "colima is running"; then
  echo "Colima already running"
else
  colima start
fi
cd docker && docker compose up -d
```

Durdur:

```bash
cd docker && docker compose down
colima stop
```

---

## SSS

**S: Bilgisayarı yeniden başlattım, ne çalıştırmalıyım?**

Not: Aşağıdaki komutu repo kök dizininde çalıştırın; `cd docker` göreli yol kullanır.

```bash
if colima status 2>/dev/null | grep -q "colima is running"; then
  echo "Colima already running"
else
  colima start
fi
cd docker && docker compose up -d
```

**S: MT5 ekranı siyah kalıyor, ne yapmalıyım?**

C: Colima'nın QEMU/x86_64 modunda çalıştığını doğrulayın. Ayrıca hatayı görmek için detached `-d` yerine foreground debug modda başlatın:

```bash
colima status
cd docker && docker compose up --build
```

**S: MT5’i güvenli nasıl durdururum?**

```bash
cd docker && docker compose down
```
