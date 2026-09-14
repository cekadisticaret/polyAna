import SwiftUI

/// FireVibe / BursaApp ortak tipografi token’ları.
enum AppTypography {
    static let hero = Font.system(size: 30, weight: .bold)
    static let screenTitle = Font.system(size: 28, weight: .bold)
    static let section = Font.headline.weight(.bold)
    static let cardTitle = Font.title3.weight(.bold)
    static let body = Font.body
    static let caption = Font.caption.weight(.semibold)
    static let chip = Font.subheadline.weight(.semibold)
    static let tabIcon = Font.system(size: 18, weight: .semibold)
}

enum AppSpacing {
    static let screenX: CGFloat = 18
    static let section: CGFloat = 22
    static let card: CGFloat = 16
    static let chip: CGFloat = 10
}
