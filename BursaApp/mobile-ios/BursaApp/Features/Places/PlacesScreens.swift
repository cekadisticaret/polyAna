import SwiftUI

struct CategoryPlacesView: View {
    @EnvironmentObject private var auth: AuthStore
    let title: String
    let category: String
    @State private var places: [PlaceItem] = []
    @State private var loading = true
    @State private var error: String?

    var body: some View {
        AppPage(title: title) {
            ScrollView {
                VStack(spacing: 12) {
                    LoadingStateView(loading: loading, error: error, empty: !loading && places.isEmpty, emptyText: "Sonuç yok")
                    PlaceListSection(places: places)
                }
                .padding(16)
            }
            .refreshable { await load() }
            .task { await load() }
        }
    }

    @MainActor
    private func load() async {
        loading = true
        error = nil
        defer { loading = false }
        do {
            places = try await auth.apiClient().places(category: category, limit: 40)
        } catch {
            self.error = error.localizedDescription
        }
    }
}
