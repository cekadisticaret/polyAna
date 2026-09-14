# BursaApp — FireVibe tasarım brief’i

FireVibe projesi: **BursaVibe** · Kod hedefi: **BursaApp** (`mobile-ios/` SwiftUI)

## MCP prompt (Cursor / Claude Code)

```
FireVibe'daki "BursaVibe" projemi aç.
get_design_system ile token'ları al.
"Anasayfa" ekranı için get_screen çağır.
Export'u SwiftUI olarak mobile-ios/BursaApp/Features/Feed/FeedView.swift gövdesine merge et;
BursaAPIClient + FeedViewModel wiring korunacak. iOS 16.
```

## Ürün

Bursa şehir rehberi. API: `https://bursaapp.com/api/v1`.

## Platform

- SwiftUI, iOS **16.0+**
- `SWIFT_STRICT_CONCURRENCY: complete`
- Export dili: **SwiftUI** (React/TSX değil)

## Marka (BursaVibe / FireVibe)

| Token | Değer |
|-------|--------|
| Nav / primary | `#1B4332` → `AppColors.nav` |
| Arka plan | `#FAFAFB` → `AppColors.bg` |
| Kart | beyaz, radius 22–28 |
| Chip seçili | `#EDE0CC` → `AppColors.chipSelected` |

## Sekmeler

Ana sayfa · Harita · Lezzet · Profil

## Ekran eşlemesi (FireVibe → SwiftUI)

| FireVibe | Dosya |
|----------|--------|
| Anasayfa | `Features/Feed/FeedView.swift` |
| Harita | `Features/Explore/ExploreView.swift` |
| Lezzet | `Features/Food/FoodView.swift` |
| Mekan detay | `Features/PlaceDetail/PlaceDetailView.swift` |
| Auth | `Features/Auth/AuthFlowView.swift` |
| Profil | `Features/Profile/ProfileView.swift` |

## Merge kuralları

- API/auth/navigation dosyalarına dokunma
- Statik mock yok — `PlaceItem`, `FeedViewModel`, `AuthStore`
- `Text + Text` → `.foregroundColor` (iOS 16)
- `.navigationBarHidden(true)` kullan
- `Link` → View struct veya `@MainActor`

## MCP kurulum

1. `.env` → `FIREVIBE_API_KEY=fv_sk_...` (kaydet)
2. `.cursor/mcp.json.example` → `mcp.json` kopyala veya env referansı kullan
3. Cursor yeniden başlat → **firevibe MCP** yeşil
