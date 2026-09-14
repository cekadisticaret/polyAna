import SwiftUI

struct DestinationCard: View {
    @EnvironmentObject private var auth: AuthStore
    let place: PlaceItem
    @State private var isFav: Bool
    @State private var favBusy = false
    @State private var showAuth = false

    init(place: PlaceItem) {
        self.place = place
        _isFav = State(initialValue: place.isFav)
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            RemoteImage(url: place.imgUrl, placeholder: "photo")
                .frame(width: 88, height: 88)
                .clipShape(RoundedRectangle(cornerRadius: AppRadii.sm, style: .continuous))
            VStack(alignment: .leading, spacing: 6) {
                Text(place.title)
                    .font(.headline.weight(.bold))
                    .foregroundStyle(AppColors.ink)
                    .multilineTextAlignment(.leading)
                if !place.categoryLabel.isEmpty {
                    Text(place.categoryLabel)
                        .font(.caption2.weight(.heavy))
                        .foregroundStyle(AppColors.nav)
                } else if !place.ilce.isEmpty {
                    Text(place.ilce)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(AppColors.muted)
                }
                if !place.blurb.isEmpty {
                    Text(place.blurb)
                        .font(.caption)
                        .foregroundStyle(AppColors.muted)
                        .lineLimit(2)
                }
            }
            Spacer(minLength: 0)
            Button { Task { await toggleFavorite() } } label: {
                if favBusy {
                    ProgressView().scaleEffect(0.8)
                } else {
                    Image(systemName: isFav ? "heart.fill" : "heart")
                        .foregroundStyle(isFav ? AppColors.coral : AppColors.muted)
                }
            }
            .buttonStyle(.plain)
            .disabled(favBusy || place.detailSlug.isEmpty)
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: AppRadii.lg, style: .continuous)
                .fill(AppColors.card)
                .shadow(color: .black.opacity(0.05), radius: 8, y: 3)
        )
        .sheet(isPresented: $showAuth) { AuthFlowView() }
    }

    @MainActor
    private func toggleFavorite() async {
        guard auth.isLoggedIn else { showAuth = true; return }
        guard !place.detailSlug.isEmpty else { return }
        favBusy = true
        defer { favBusy = false }
        if let result = try? await auth.apiClient().togglePlaceFavorite(slug: place.detailSlug) {
            isFav = result.0
        }
    }
}

struct EventPlaceCard: View {
    let place: PlaceItem

    private var meta: String {
        [place.whenLabel, !place.venueName.isEmpty ? place.venueName : place.ilce]
            .filter { !$0.isEmpty }
            .joined(separator: " · ")
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            RemoteImage(url: place.imgUrl, placeholder: categoryIcon)
                .frame(width: 72, height: 72)
                .clipShape(RoundedRectangle(cornerRadius: AppRadii.sm))
            VStack(alignment: .leading, spacing: 4) {
                Text(place.title)
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(AppColors.ink)
                    .lineLimit(2)
                if !place.categoryLabel.isEmpty {
                    Text(place.categoryLabel)
                        .font(.caption2.weight(.heavy))
                        .foregroundStyle(AppColors.nav)
                }
                if !meta.isEmpty {
                    Text(meta).font(.caption).foregroundStyle(AppColors.muted).lineLimit(2)
                } else if !place.blurb.isEmpty {
                    Text(place.blurb).font(.caption).foregroundStyle(AppColors.muted).lineLimit(2)
                }
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.right")
                .foregroundStyle(AppColors.muted)
                .padding(.top, 24)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(
            RoundedRectangle(cornerRadius: AppRadii.lg)
                .fill(AppColors.card)
                .shadow(color: .black.opacity(0.05), radius: 8, y: 3)
        )
    }

    private var categoryIcon: String {
        switch place.category {
        case "cinema": return "film"
        case "theater": return "theatermasks.fill"
        case "concert": return "music.note"
        case "camp": return "leaf.fill"
        case "hotel": return "bed.double.fill"
        default: return "calendar"
        }
    }
}

struct VisitHitCard: View {
    let row: [String: Any]

    var body: some View {
        if let place = PlaceItem.decode(from: row) {
            EventPlaceCard(place: place)
        }
    }
}
