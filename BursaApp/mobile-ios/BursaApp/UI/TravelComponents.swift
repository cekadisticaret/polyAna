import SwiftUI

enum TravelCategoryChip: String, CaseIterable {
    case all, visit, food, event

    var title: String {
        switch self {
        case .all: "Tümü"
        case .visit: "Gezi"
        case .food: "Lezzet"
        case .event: "Etkinlik"
        }
    }

    var emoji: String {
        switch self {
        case .all: "🏝️"
        case .visit: "⛰️"
        case .food: "🍽️"
        case .event: "🎭"
        }
    }

    var apiCategory: String {
        switch self {
        case .all: ""
        case .visit: "visit"
        case .food: "food"
        case .event: "event"
        }
    }
}

struct TravelTopBar: View {
    let location: String
    let notificationCount: Int
    let onNotificationsTap: () -> Void

    var body: some View {
        HStack {
            Label(location, systemImage: "mappin.and.ellipse")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(AppColors.muted)
            Spacer()
            Button(action: onNotificationsTap) {
                ZStack(alignment: .topTrailing) {
                    Image(systemName: "bell")
                        .font(.body.weight(.semibold))
                        .foregroundStyle(AppColors.ink)
                        .frame(width: 42, height: 42)
                        .background(Circle().fill(.white).shadow(color: .black.opacity(0.08), radius: 8, y: 3))
                    if notificationCount > 0 {
                        Text("\(min(notificationCount, 9))")
                            .font(.system(size: 10, weight: .heavy))
                            .foregroundStyle(.white)
                            .frame(width: 16, height: 16)
                            .background(Circle().fill(AppColors.coral))
                            .offset(x: 4, y: -2)
                    }
                }
            }
            .buttonStyle(.plain)
        }
    }
}

struct TravelHeroTitle: View {
    var highlight = "Sen"

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            (
                Text("Nereye 🏝️\n")
                    .foregroundColor(AppColors.ink)
                + Text("\(highlight) ")
                    .foregroundColor(AppColors.nav)
                + Text("gitmek\nistiyorsun?")
                    .foregroundColor(AppColors.ink)
            )
            .font(AppTypography.hero)
            .lineSpacing(2)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct TravelSearchCapsule: View {
    @Binding var query: String
    var placeholder = "Bursa | Mekan ara…"
    let onSearchTap: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "globe.europe.africa.fill")
                .foregroundStyle(AppColors.nav)
                .font(.subheadline)
            TextField(placeholder, text: $query)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .onSubmit { onSearchTap() }
            Button(action: onSearchTap) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(AppColors.muted)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .background(
            Capsule()
                .fill(Color.white)
                .shadow(color: .black.opacity(0.06), radius: 10, y: 4)
        )
    }
}

struct TravelCategoryChips: View {
    @Binding var selected: TravelCategoryChip

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Kategori")
                .font(.subheadline.weight(.bold))
                .foregroundStyle(AppColors.ink)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    ForEach(TravelCategoryChip.allCases, id: \.rawValue) { chip in
                        Button { selected = chip } label: {
                            HStack(spacing: 6) {
                                Text(chip.emoji)
                                Text(chip.title)
                                    .font(.subheadline.weight(.semibold))
                            }
                            .foregroundStyle(selected == chip ? AppColors.nav : AppColors.ink)
                            .padding(.horizontal, 16)
                            .padding(.vertical, 10)
                            .background(
                                Capsule().fill(selected == chip ? AppColors.chipSelected : AppColors.chipBg)
                            )
                            .overlay(
                                Capsule().stroke(AppColors.muted.opacity(selected == chip ? 0 : 0.15), lineWidth: 1)
                            )
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }
}

struct TravelSectionHeader: View {
    let title: String
    var onSeeAll: (() -> Void)?

    var body: some View {
        HStack {
            Text(title).font(.headline.weight(.bold)).foregroundStyle(AppColors.ink)
            Spacer()
            if let onSeeAll {
                Button("Tümü", action: onSeeAll)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(AppColors.muted)
            }
        }
    }
}

struct TravelInfoCard: View {
    let title: String
    let subtitle: String
    let imageUrl: String
    let timeLabel: String
    let tourLabel: String
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 12) {
                    RemoteImage(url: imageUrl, placeholder: "photo")
                        .frame(width: 52, height: 52)
                        .clipShape(Circle())
                    VStack(alignment: .leading, spacing: 4) {
                        Text(title).font(.headline.weight(.bold)).foregroundStyle(AppColors.ink)
                        Text(subtitle).font(.caption.weight(.semibold)).foregroundStyle(AppColors.muted)
                    }
                    Spacer()
                    Image(systemName: "arrow.up.right")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(AppColors.ink)
                        .frame(width: 32, height: 32)
                        .background(Circle().fill(AppColors.bgSoft))
                }
                HStack(spacing: 20) {
                    Label(timeLabel, systemImage: "clock")
                    Label(tourLabel, systemImage: "calendar")
                }
                .font(.caption.weight(.semibold))
                .foregroundStyle(AppColors.muted)
            }
            .padding(16)
            .background(
                RoundedRectangle(cornerRadius: AppRadii.lg, style: .continuous)
                    .fill(Color.white)
                    .shadow(color: .black.opacity(0.06), radius: 12, y: 5)
            )
        }
        .buttonStyle(.plain)
    }
}

struct TravelFeaturedCard: View {
    let place: PlaceItem
    @State private var isFav: Bool

    init(place: PlaceItem) {
        self.place = place
        _isFav = State(initialValue: place.isFav)
    }

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            RemoteImage(url: place.imgUrl, placeholder: "photo")
                .frame(height: 220)
                .frame(maxWidth: .infinity)
                .clipped()
            LinearGradient(colors: [.clear, .black.opacity(0.55)], startPoint: .center, endPoint: .bottom)
            VStack {
                HStack {
                    Label(place.ilce.isEmpty ? "Bursa" : place.ilce, systemImage: "mappin.and.ellipse")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(Capsule().fill(.black.opacity(0.25)))
                    Spacer()
                    Image(systemName: isFav ? "heart.fill" : "heart")
                        .font(.body.weight(.semibold))
                        .foregroundStyle(isFav ? AppColors.coral : AppColors.ink)
                        .frame(width: 36, height: 36)
                        .background(Circle().fill(.white))
                }
                .padding(14)
                Spacer()
                HStack(alignment: .bottom) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(place.title)
                            .font(.title3.weight(.bold))
                            .foregroundStyle(.white)
                            .lineLimit(2)
                        HStack(spacing: 8) {
                            Text(place.categoryLabel.isEmpty ? "Keşfet" : place.categoryLabel)
                                .font(.caption.weight(.heavy))
                                .foregroundStyle(.white)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 6)
                                .background(Capsule().fill(AppColors.nav))
                            HStack(spacing: 4) {
                                Image(systemName: "star.fill").foregroundStyle(AppColors.amber)
                                Text(travelRating(seed: place.title.hashValue))
                                    .font(.caption.weight(.heavy))
                                    .foregroundStyle(.white)
                            }
                        }
                    }
                    Spacer()
                }
                .padding(14)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: AppRadii.lg, style: .continuous))
        .shadow(color: .black.opacity(0.08), radius: 12, y: 6)
    }
}

struct TravelPrimaryButton: View {
    let title: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.headline.weight(.bold))
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
                .background(Capsule().fill(AppColors.nav))
        }
        .buttonStyle(.plain)
    }
}

struct TravelGhostButton: View {
    let icon: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.body.weight(.semibold))
                .foregroundStyle(AppColors.ink)
                .frame(width: 42, height: 42)
                .background(Circle().fill(.white).shadow(color: .black.opacity(0.10), radius: 8, y: 3))
        }
        .buttonStyle(.plain)
    }
}

struct TravelDetailTabs: View {
    @Binding var selected: Int
    let titles: [String]

    var body: some View {
        HStack(spacing: 8) {
            ForEach(Array(titles.enumerated()), id: \.offset) { idx, title in
                Button { selected = idx } label: {
                    Text(title)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(selected == idx ? AppColors.nav : AppColors.muted)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 10)
                        .background(
                            Capsule().fill(selected == idx ? AppColors.chipSelected : Color.clear)
                        )
                }
                .buttonStyle(.plain)
            }
            Spacer()
        }
    }
}

struct TravelInfoPod: View {
    let icon: String
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Image(systemName: icon)
                .font(.caption)
                .foregroundStyle(AppColors.muted)
            Text(label).font(.caption2).foregroundStyle(AppColors.muted)
            Text(value).font(.caption.weight(.bold)).foregroundStyle(AppColors.ink).lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(RoundedRectangle(cornerRadius: AppRadii.sm).fill(AppColors.bgSoft))
    }
}

struct TravelBottomActionBar: View {
    let leftTitle: String
    let leftValue: String
    let buttonTitle: String
    let action: () -> Void

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(leftTitle).font(.caption).foregroundStyle(AppColors.muted)
                Text(leftValue).font(.headline.weight(.bold)).foregroundStyle(AppColors.ink)
            }
            Spacer()
            Button(action: action) {
                Text(buttonTitle)
                    .font(.headline.weight(.bold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 28)
                    .padding(.vertical, 14)
                    .background(Capsule().fill(AppColors.nav))
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 14)
        .background(Color.white)
        .shadow(color: .black.opacity(0.08), radius: 12, y: -4)
    }
}

func travelRating(seed: Int) -> String {
    String(format: "%.1f", 4.6 + Double(abs(seed) % 5) * 0.1)
}

func travelJoinCount(seed: Int) -> Int {
    12 + abs(seed) % 320
}

struct TravelLeaderCard: View {
    let leader: LeaderRow

    var body: some View {
        VStack(spacing: 8) {
            ZStack(alignment: .bottomTrailing) {
                Group {
                    if leader.avatarUrl.isEmpty {
                        Text(String(leader.name.prefix(1)).uppercased())
                            .font(.headline.weight(.bold))
                            .foregroundStyle(.white)
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                            .background(AppColors.nav)
                    } else {
                        RemoteImage(url: leader.avatarUrl, placeholder: "person.fill")
                    }
                }
                .frame(width: 64, height: 64)
                .clipShape(Circle())
                Text("#\(leader.rank)")
                    .font(.system(size: 9, weight: .heavy))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 3)
                    .background(Capsule().fill(AppColors.nav))
                    .offset(x: 4, y: 4)
            }
            Text(leader.name)
                .font(.caption.weight(.bold))
                .foregroundStyle(AppColors.ink)
                .lineLimit(1)
            Text("\(leader.points) puan")
                .font(.caption2)
                .foregroundStyle(AppColors.muted)
        }
        .frame(width: 88)
    }
}

struct TravelLocalAvatar: View {
    let place: PlaceItem

    var body: some View {
        VStack(spacing: 6) {
            RemoteImage(url: place.imgUrl, placeholder: "photo")
                .frame(width: 56, height: 56)
                .clipShape(Circle())
                .overlay(Circle().stroke(AppColors.chipSelected, lineWidth: 2))
            Text(place.title)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(AppColors.ink)
                .lineLimit(1)
                .frame(width: 64)
        }
    }
}
