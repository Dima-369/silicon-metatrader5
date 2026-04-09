# Release 1.2.3

## Summary

Release `1.2.3` fixes the packaged bridge server layout and adds the KasmVNC runtime variant.

## Changes

- packaged the bridge server module correctly in `siliconmetatrader5`
- pinned `siliconmetatrader5==1.2.3` in Docker requirements
- added `docker_kasm/` as the KasmVNC-based MT5 runtime
- kept `docker/` as the legacy `x11vnc + noVNC` runtime
- documented that KasmVNC usage must be started from the `docker_kasm/` directory

## Bridge Server Packaging Fix

### Problem
In some environments, `python -m siliconmetatrader5` could resolve the wrong `server` module. The package entrypoint expected the bridge server to be available as part of the installed package layout, but the old wheel layout could leave resolution dependent on the surrounding environment. That made the CLI bridge bootstrap fragile across different Docker/runtime setups.

### Fix
Release `1.2.3` fixes the package layout so the bridge server module is packaged correctly and the CLI bridge bootstrap resolves the intended module consistently.

## KasmVNC Usage

### Tradeoff
KasmVNC is heavier than the legacy `docker/` stack, but it provides a newer, more modern, and generally more stable desktop layer. Expect a larger image and longer build times in exchange for that improved GUI stack.

### Fresh setup or full reset
Use this if you are starting from scratch or intentionally want to reset the persistent MT5 state under `/config`.

```bash
cd docker_kasm
docker compose down -v
docker compose build
docker compose up
```

### Upgrade an existing running `docker_kasm` setup
If the Kasm container is already running and you just want to move to the latest image/config without wiping broker login, MT5 state, or downloaded history, use this flow instead:

```bash
cd docker_kasm
docker compose down
docker compose build
docker compose up
```

### Move from legacy `docker/` to `docker_kasm/`
If you currently have the old `docker/` stack running and want to switch to the new KasmVNC stack, stop the legacy stack first, then start the Kasm variant.

```bash
cd docker
docker compose down

cd ../docker_kasm
docker compose build
docker compose up
```

Why this order matters:
- both variants use the MT5 bridge on port `8001`
- running both at the same time is not valid
- `docker compose down` on the legacy stack stops it cleanly before Kasm starts

`down -v` removes volumes. That means:
- MT5 login/session is cleared
- persistent prefix is reset
- downloaded history is removed

Access:
- UI: `http://localhost:3000`
- Bridge: `localhost:8001`

## Client Upgrade

```bash
python3 -m pip install --upgrade siliconmetatrader5==1.2.3
```

## Known Issues

- While MetaTrader 5 is loading bars, synchronizing deeper history, or pulling large amounts of historical data for backtesting, the system can become unstable if the machine does not have enough RAM.
- In these cases, users may see crashes, freezes, or severe slowdowns.
- GUI freezes can also appear on the VNC/KasmVNC side while MT5 is downloading or processing a large amount of bar data in the background.


## Türkçe

## Özet

`1.2.3` sürümü, paketlenmiş bridge server yerleşimini düzeltir ve KasmVNC runtime varyantını ekler.

## Değişiklikler

- `siliconmetatrader5` içinde bridge server modülü doğru şekilde paketlendi
- Docker requirements dosyalarında `siliconmetatrader5==1.2.3` sabitlendi
- KasmVNC tabanlı MT5 runtime olarak `docker_kasm/` eklendi
- legacy `x11vnc + noVNC` runtime olarak `docker/` korunmaya devam etti
- KasmVNC kullanımına `docker_kasm/` klasörü içinden başlanması gerektiği dokümante edildi

## Bridge Server Paketleme Düzeltmesi

### Sorun
Bazı ortamlarda `python -m siliconmetatrader5`, yanlış `server` modülünü resolve edebiliyordu. Paket entrypoint'i bridge server modülünün kurulu paket yapısının bir parçası olmasını bekliyordu, ancak eski wheel yerleşimi bu çözümlemeyi çevreye bağımlı hale getirebiliyordu. Bu da CLI bridge bootstrap akışını farklı Docker/runtime kurulumlarında kırılgan yapıyordu.

### Fix
`1.2.3` sürümünde paket yerleşimi düzeltildi. Bridge server modülü doğru şekilde paketleniyor ve CLI bridge bootstrap artık hedeflenen modülü tutarlı biçimde resolve ediyor.

## KasmVNC Kullanımı

### Trade-off
KasmVNC, legacy `docker/` stack'inden daha ağırdır; ancak daha güncel, daha modern ve genel olarak daha stabil bir masaüstü katmanı sunar. Bu iyileşmiş GUI stack karşılığında daha büyük image ve daha uzun build süreleri beklenmelidir.

### Temiz kurulum veya tam sıfırlama
Sıfırdan başlıyorsanız veya `/config` altındaki kalıcı MT5 durumunu bilinçli şekilde sıfırlamak istiyorsanız bu akışı kullanın.

```bash
cd docker_kasm
docker compose down -v
docker compose build
docker compose up
```

### Hâlihazırda çalışan `docker_kasm` kurulumunu güncelleme
Kasm container'ı zaten çalışıyorsa ve broker login, MT5 state veya indirilen history'yi silmeden sadece güncel image/config'e geçmek istiyorsanız bu akışı kullanın:

```bash
cd docker_kasm
docker compose down
docker compose build
docker compose up
```

### Legacy `docker/` stack'inden `docker_kasm/`e geçiş
Eski `docker/` stack'i çalışıyorsa ve yeni KasmVNC stack'ine geçmek istiyorsanız önce legacy stack'i durdurun, sonra Kasm varyantını başlatın.

```bash
cd docker
docker compose down

cd ../docker_kasm
docker compose build
docker compose up
```

Bu sıra neden önemli:
- iki varyant da MT5 bridge için `8001` portunu kullanır
- ikisini aynı anda çalıştırmak doğru değildir
- legacy stack üzerindeki `docker compose down` onu temiz şekilde kapatır, sonra Kasm başlar

`down -v` volume'leri siler. Bunun anlamı:
- MT5 login/session sıfırlanır
- persistent prefix sıfırlanır
- indirilen history silinir

Erişim:
- Arayüz: `http://localhost:3000`
- Bridge: `localhost:8001`

## Client Güncelleme

```bash
python3 -m pip install --upgrade siliconmetatrader5==1.2.3
```

## Bilinen Sorunlar

- MetaTrader 5 bar yüklerken, daha derin history senkronize ederken veya backtest için büyük miktarda geçmiş veri indirirken, makinede yeterli RAM yoksa sistem kararsız hale gelebilir.
- Bu durumlarda çökme, donma veya ciddi yavaşlama görülebilir.
- MT5 arka planda yoğun bar verisi indirirken ya da işlerken VNC/KasmVNC arayüzünde de donmalar görülebilir.

