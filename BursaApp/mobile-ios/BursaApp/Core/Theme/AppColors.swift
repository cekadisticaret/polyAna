import SwiftUI

enum AppColors {
    // ── BursaVibe FireVibe Palette ──────────────────────────────────────────
    // primary: Bursa Mavisi
    static let primary    = Color(red: 7/255,   green: 87/255,  blue: 217/255)  // #0757D9
    static let secondary  = Color(red: 231/255, green: 238/255, blue: 252/255)  // #E7EEFC
    static let accent     = Color(red: 245/255, green: 184/255, blue: 61/255)   // #F5B83D (Safran Altını)
    static let success    = Color(red: 0/255,   green: 133/255, blue: 114/255)  // #008572
    static let destructive = Color(red: 201/255, green: 54/255, blue: 59/255)  // #C9363B (Nar Kırmızısı)

    // Surfaces
    static let bg         = Color(red: 248/255, green: 247/255, blue: 242/255)  // #F8F7F2 (Kireçtaşı Beyazı)
    static let card       = Color.white                                          // #FFFFFF
    static let surface    = Color(red: 238/255, green: 237/255, blue: 232/255)  // #EEEDE8 (muted bg)
    static let border     = Color(red: 217/255, green: 222/255, blue: 229/255)  // #D9DEE5

    // Text
    static let ink        = Color(red: 23/255,  green: 35/255,  blue: 59/255)   // #17233B (foreground)
    static let muted      = Color(red: 93/255,  green: 104/255, blue: 120/255)  // #5D6878 (mutedForeground)

    // ── Legacy aliases (backward compat) ───────────────────────────────────
    static let nav        = primary
    static let bgSoft     = Color(red: 243/255, green: 244/255, blue: 246/255)  // #F3F4F6
    static let bgDeep     = primary
    static let mutedFg    = muted
    static let amber      = accent
    static let coral      = destructive
    static let chipBg     = card
    static let chipSelected = secondary
    static let accentDeep = primary
    static let lime       = success
    static let peach      = accent
    static let sky        = primary
    static let pink       = destructive
}

enum AppRadii {
    static let sm: CGFloat = 12
    static let md: CGFloat = 16
    static let lg: CGFloat = 20
    static let xl: CGFloat = 26
}
