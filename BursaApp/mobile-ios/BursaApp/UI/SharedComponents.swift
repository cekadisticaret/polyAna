import SwiftUI

struct AppPage<Content: View>: View {
    let title: String
    @ViewBuilder let content: Content

    var body: some View {
        VStack(spacing: 0) {
            content
        }
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(AppColors.bg, for: .navigationBar)
        .background(AppColors.bg.ignoresSafeArea())
    }
}

struct LoadingStateView: View {
    let loading: Bool
    let error: String?
    let empty: Bool
    let emptyText: String

    var body: some View {
        if loading {
            ProgressView().frame(maxWidth: .infinity).padding(.vertical, 40)
        } else if let error, !error.isEmpty {
            Text(error).foregroundStyle(AppColors.coral).padding()
        } else if empty {
            Text(emptyText).foregroundStyle(AppColors.muted).padding(.vertical, 40)
        }
    }
}

struct PlaceListSection: View {
    let places: [PlaceItem]
    var eventStyle = false

    var body: some View {
        LazyVStack(spacing: 12) {
            ForEach(places) { place in
                NavigationLink(value: place.detailSlug) {
                    if eventStyle {
                        EventPlaceCard(place: place)
                    } else {
                        DestinationCard(place: place)
                    }
                }
                .buttonStyle(.plain)
            }
        }
    }
}
