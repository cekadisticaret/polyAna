# CoptC

B1#03 MUM, B1#05 ve A1 defterlerinin ana projeden bağımsız kopyası. Her
defterin sanal karşılığı ve gerçek Polymarket defteri var; dashboard üçünü de
ayrı sekmede gösterir.

| Defter | Sanal | Gerçek PM | Semboller | Live nasıl karar veriyor |
|---|---|---|---|---|
| B1#05 | `b1_05` | `b1_05_live` | BTC · ETH · SOL | sanalı **aynalar** (:06) |
| B1#03 MUM | `b1_mum` | `b1_mum_live` | BTC · ETH · SOL | sanalı **aynalar** (:06) |
| A1 | `analiz1` | `analiz5` | BTC · SOL | **kendi** sinyalini çözer (:05) |

A1'in canlısı bir ayna değil, bağımsız bir trader — bu yüzden :06'yı beklemez,
sanalla aynı turda koşar. Kademesi de ayrı: sanal sabit $12/16/20, gerçek PM
dashboard'daki `a1_amount_*` alanlarından ($10/12/14 kurulur).

## Kurulum

```bash
pip install -r requirements.txt
cp .env.example .env          # cüzdan + panel parolası
python3 runner.py status      # defterler görünüyor mu
crontab -e                    # deploy/crontab.txt içeriğini ekle
```

Dashboard: `python3 web/dashboard.py` → `http://sunucu:5060`
Servis olarak: `deploy/coptc-dashboard.service` → `/etc/systemd/system/`

## Yapı

| Yol | Ne yapar |
|---|---|
| `runner.py` | Tek giriş noktası — `close` · `open` · `live-open` · `settle` · `status` |
| `poly/` | Sinyal motorları, defter trader'ları, state/history JSON'ları |
| `poly/pool_tracker.py` | B1#05'in aday havuzundaki 22 defteri her saat gölge olarak notlar |
| `poly/poly_predictor_analysis.py` | A1'in motoru — akış (CVD, emir defteri) + türev (funding, likidasyon) |
| `web/dashboard.py` | Panel (Flask) |
| `web/api.py` | Panelin veri katmanı |

## Gerçek para

Üç Live defteri de **kapalı** kurulur. Açmak için dashboard'daki
`Live aç` düğmesi tek yetkilidir (`poly/pm_system_control.json`).
`.env`'de `POLY_DRY_RUN=true` kaldığı sürece emir gönderilmez.

Ana projede `analiz5` (A1 Live) grubu *varsayılan açık* geliyordu — kontrol
dosyası silinse yeni sunucuda kendiliğinden gerçek para açardı. CoptC'de
`_DEFAULT_OPEN_GROUPS` boşaltıldı: anahtar yoksa cevap **kapalı**.

## Telegram

Kapalı. `COPTC_TELEGRAM` varsayılanı `off` ve 11 gönderim noktasının hepsinde
ilk kontrol bu — `.env` hiç olmasa bile bildirim gitmez. Açmak istersen
`COPTC_TELEGRAM=on` yap ve kanal/token değişkenlerini doldur; ana projeyle
aynı kanalı kullanma.

## Para çekme

Dashboard'un altındaki **Polymarket'ten para çek** kartı, proxy cüzdandan
Polymarket relayer'ı üzerinden gasless ERC-20 gönderimi yapar
(`poly/pm_transfer.py::relay_send_erc20`). Çalışması için gerekenler:

- `COPTC_PASSWORD` — parolasız panelde çekim ucu **403** döner
- `COPTC_WITHDRAW_CODE` — her gönderimde istenir, 5 hatada 15 dk kilit
- `POLY_BUILDER_API_KEY` / `SECRET` / `PASSPHRASE` — polymarket.com/settings?tab=builder

Gönderim öncesi kontrol edilenler: adres biçimi, tutar ≤ bakiye ve
proxy adresinin `POLY_FUNDER` ile eşleşmesi. Her deneme
`poly/withdraw_log.jsonl`'a yazılır — kod **hiçbir zaman** kaydedilmez.

pUSD doğrudan bir borsaya gönderilemez; başka zincire gerçek USDC olarak
çekmek için `python3 poly/pm_transfer.py withdraw --to 0x… --chain 1` ile
bridge adresi üret.
