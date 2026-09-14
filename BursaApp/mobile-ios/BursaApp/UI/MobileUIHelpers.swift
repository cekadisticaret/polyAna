import SwiftUI

struct CardShadow: ViewModifier {
    func body(content: Content) -> some View {
        content.shadow(color: AppColors.ink.opacity(0.06), radius: 12, y: 6)
    }
}

extension View {
    func cardShadow() -> some View { modifier(CardShadow()) }
}

struct SectionHeader: View {
    let title: String
    var subtitle: String?
    var actionTitle: String?
    var action: (() -> Void)?

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title).font(.headline.weight(.black))
                if let subtitle, !subtitle.isEmpty {
                    Text(subtitle).font(.caption).foregroundStyle(AppColors.muted)
                }
            }
            Spacer()
            if let actionTitle, let action {
                Button(actionTitle, action: action)
                    .font(.caption.weight(.heavy))
                    .foregroundStyle(AppColors.accentDeep)
            }
        }
    }
}

struct HeroBanner: View {
    let imageUrl: String
    var height: CGFloat = 160
    var title: String?
    var subtitle: String?

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            RemoteImage(url: imageUrl, placeholder: "photo")
                .frame(height: height)
                .frame(maxWidth: .infinity)
                .clipped()
            LinearGradient(colors: [.clear, AppColors.ink.opacity(0.65)], startPoint: .top, endPoint: .bottom)
            if title != nil || subtitle != nil {
                VStack(alignment: .leading, spacing: 4) {
                    if let title { Text(title).font(.title3.weight(.black)).foregroundStyle(.white) }
                    if let subtitle { Text(subtitle).font(.caption).foregroundStyle(.white.opacity(0.9)) }
                }
                .padding(14)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: AppRadii.lg, style: .continuous))
    }
}

struct MetaChip: View {
    let text: String
    var color: Color = AppColors.accentDeep

    var body: some View {
        Text(text)
            .font(.caption2.weight(.bold))
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(color.opacity(0.15))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }
}

struct PhoneLink: View {
    let phone: String

    var body: some View {
        if let url = URL(string: "tel:\(phone.filter { $0.isNumber || $0 == "+" })") {
            Link(destination: url) {
                Label(phone, systemImage: "phone.fill")
                    .font(.subheadline.weight(.semibold))
            }
        }
    }
}

struct MapsLink: View {
    let urlString: String
    let label: String

    var body: some View {
        if let url = URL(string: urlString) {
            Link(destination: url) {
                Label(label, systemImage: "map.fill")
                    .font(.subheadline.weight(.semibold))
            }
        }
    }
}

struct GroupedJSONPlaces: View {
    let groups: [[String: Any]]

    var body: some View {
        LazyVStack(alignment: .leading, spacing: 16) {
            ForEach(Array(groups.enumerated()), id: \.offset) { _, group in
                if let label = group["label"] as? String, !label.isEmpty {
                    Text(label).font(.subheadline.weight(.black)).foregroundStyle(AppColors.muted)
                }
                let places = PlaceItem.list(from: group)
                ForEach(places) { place in
                    NavigationLink(value: place.detailSlug) {
                        EventPlaceCard(place: place)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }
}

struct JSONPlaceRows: View {
    let rows: [[String: Any]]
    var useEventCard = true

    var body: some View {
        LazyVStack(spacing: 12) {
            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                if let place = PlaceItem.decode(from: row) {
                    NavigationLink(value: place.detailSlug) {
                        if useEventCard {
                            EventPlaceCard(place: place)
                        } else {
                            DestinationCard(place: place)
                        }
                    }
                    .buttonStyle(.plain)
                } else {
                    jsonRowCard(row)
                }
            }
        }
    }

    @ViewBuilder
    private func jsonRowCard(_ row: [String: Any]) -> some View {
        let slug = (row["slug"] as? String ?? PlaceItem.slugFromPath(row["path"] as? String ?? "")).trimmingCharacters(in: .whitespacesAndNewlines)
        let content = VStack(alignment: .leading, spacing: 6) {
            Text(row["title"] as? String ?? row["name"] as? String ?? "Kayıt")
                .font(.headline)
            if let sub = row["address"] as? String ?? row["blurb"] as? String {
                Text(sub).font(.caption).foregroundStyle(AppColors.muted).lineLimit(+2)
            }
            HStack {
                if let phone = row["phone"] as? String ?? row["tel"] as? String, !phone.isEmpty {
                    PhoneLink(phone: phone)
                }
                if let maps = row["maps"] as? String, !maps.isEmpty {
                    MapsLink(urlString: maps, label: "Yol tarifi")
                }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: AppRadii.md).fill(AppColors.card))

        if slug.isEmpty {
            content
        } else {
            NavigationLink(value: slug) { content }.buttonStyle(.plain)
        }
    }
}

enum MobileJSON {
    static func maps(_ value: Any?) -> [[String: Any]] {
        (value as? [[String: Any]]) ?? []
    }

    static func strings(_ value: Any?) -> [String] {
        (value as? [String] ?? []).filter { !$0.isEmpty }
    }

    static func chipItems(from value: Any?, allLabel: String = "Tümü") -> [(String, String)] {
        var items: [(String, String)] = [("", allLabel)]
        if let rows = value as? [[String: Any]] {
            for row in rows {
                let key = row["key"] as? String ?? row["slug"] as? String ?? ""
                let label = row["label"] as? String ?? row["title"] as? String ?? key
                if !label.isEmpty { items.append((key, label)) }
            }
        } else if let rows = value as? [String] {
            for s in rows where !s.isEmpty { items.append((s, s)) }
        }
        return items
    }

    static func stripHtml(_ text: String) -> String {
        text.replacingOccurrences(of: "<[^>]+>", with: "", options: .regularExpression)
    }
}

struct GroupHeaderRow: View {
    let label: String
    let count: Int
    var unit: String = "kayıt"

    var body: some View {
        HStack {
            Text(label).font(.headline.weight(.black))
            Spacer()
            Text("\(count) \(unit)").font(.caption.weight(.bold)).foregroundStyle(AppColors.muted)
        }
    }
}

struct FilterDropdown: View {
    let title: String
    let items: [(String, String)]
    let selected: String
    let onSelect: (String) -> Void

    var body: some View {
        Menu {
            ForEach(items, id: \.0) { key, label in
                Button(label) { onSelect(key) }
            }
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                Text(title).font(.caption2.weight(.heavy)).foregroundStyle(AppColors.muted)
                HStack {
                    Text(items.first(where: { $0.0 == selected })?.1 ?? selected)
                        .font(.caption.weight(.bold))
                        .lineLimit(1)
                    Image(systemName: "chevron.down").font(.caption2)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(AppColors.bgSoft)
            .clipShape(RoundedRectangle(cornerRadius: AppRadii.sm))
        }
    }
}

struct ActionChipButton: View {
    let label: String
    var ghost = false
    var tint: Color = AppColors.accentDeep
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(label)
                .font(.caption2.weight(.heavy))
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(ghost ? AppColors.bgSoft : tint.opacity(0.12))
                .foregroundStyle(ghost ? AppColors.ink : tint)
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }
}

struct IlcePicker: View {
    let districts: [String]
    @Binding var selected: String

    var body: some View {
        if !districts.isEmpty {
            Menu {
                Button("Tüm ilçeler") { selected = "" }
                ForEach(districts, id: \.self) { d in
                    Button(d) { selected = d }
                }
            } label: {
                HStack {
                    Text(selected.isEmpty ? "İlçe seç" : selected)
                        .font(.caption.weight(.semibold))
                    Image(systemName: "chevron.down")
                        .font(.caption2)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(AppColors.card)
                .clipShape(Capsule())
            }
        }
    }
}
