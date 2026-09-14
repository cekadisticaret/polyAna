import SwiftUI

struct FilterChips: View {
    let items: [(String, String)]
    let selected: String
    let onSelect: (String) -> Void

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                ForEach(items, id: \.0) { key, label in
                    Button(label) { onSelect(key) }
                        .font(.subheadline.weight(.semibold))
                        .padding(.horizontal, 16)
                        .padding(.vertical, 10)
                        .background(Capsule().fill(selected == key ? AppColors.chipSelected : AppColors.chipBg))
                        .foregroundStyle(selected == key ? AppColors.nav : AppColors.ink)
                        .overlay(Capsule().stroke(AppColors.muted.opacity(selected == key ? 0 : 0.15), lineWidth: 1))
                }
            }
        }
    }
}

struct MultiFilterChips: View {
    let label: String
    let items: [(String, String)]
    let selected: Set<String>
    let onToggle: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label)
                .font(.caption.weight(.bold))
                .foregroundStyle(AppColors.muted)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(items.filter { !$0.0.isEmpty && !$0.1.isEmpty }, id: \.0) { key, title in
                        Button(title) { onToggle(key) }
                            .font(.caption.weight(.semibold))
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                            .background(selected.contains(key) ? AppColors.chipSelected : AppColors.chipBg)
                            .foregroundStyle(selected.contains(key) ? AppColors.nav : AppColors.ink)
                            .clipShape(Capsule())
                    }
                }
            }
        }
    }
}

struct GroupedPlaceList: View {
    let groups: [[String: Any]]

    var body: some View {
        LazyVStack(alignment: .leading, spacing: 16) {
            ForEach(Array(groups.enumerated()), id: \.offset) { _, group in
                if let label = group["label"] as? String, !label.isEmpty {
                    Text(label).font(.subheadline.weight(.bold)).foregroundStyle(AppColors.muted)
                }
                PlaceListSection(places: PlaceItem.list(from: group))
            }
        }
    }
}
