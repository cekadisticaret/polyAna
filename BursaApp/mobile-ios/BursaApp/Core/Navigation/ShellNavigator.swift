import SwiftUI

@MainActor
final class ShellNavigator: ObservableObject {
    var onSelectTab: ((ShellTab) -> Void)?

    func selectTab(_ tab: ShellTab) {
        onSelectTab?(tab)
    }

    func openExplore() {
        selectTab(.explore)
    }
}
