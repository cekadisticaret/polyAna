import SwiftUI

struct FeedSearchBar: View {
    let onSearchTap: () -> Void
    let onFilterTap: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            Button(action: onSearchTap) {
                HStack(spacing: 10) {
                    Image(systemName: "globe.europe.africa.fill").foregroundStyle(AppColors.nav)
                    Text("Bursa | Mekan, etkinlik ara…")
                        .foregroundStyle(AppColors.muted)
                        .fontWeight(.semibold)
                    Spacer()
                    Image(systemName: "magnifyingglass").foregroundStyle(AppColors.muted)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 14)
            }
            .buttonStyle(.plain)
            Button(action: onFilterTap) {
                Image(systemName: "line.3.horizontal.decrease")
                    .font(.body.weight(.semibold))
                    .foregroundStyle(AppColors.nav)
                    .frame(width: 44, height: 44)
                    .background(Circle().fill(AppColors.chipSelected))
            }
        }
        .background(
            Capsule()
                .fill(Color.white)
                .shadow(color: .black.opacity(0.06), radius: 10, y: 4)
        )
    }
}

struct FeedFilterSheet: View {
    @Environment(\.dismiss) private var dismiss
    let onPick: (String, String) -> Void
    let onHotels: () -> Void

    private let options: [(String, String, String)] = [
        ("Etkinlikler", "event", "calendar"),
        ("Yeme-içme", "food", "fork.knife"),
        ("Gezilecek", "visit", "mountain.2.fill"),
        ("Konserler", "concert", "music.note"),
        ("Tiyatro", "theater", "theatermasks.fill"),
        ("Sinema", "cinema", "film"),
        ("Oteller", "hotel", "bed.double.fill"),
        ("Eğlence", "fun", "party.popper.fill"),
        ("Gece hayatı", "nightlife", "moon.stars.fill"),
    ]

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text("Mekan listesine git")
                        .font(.caption)
                        .foregroundStyle(AppColors.muted)
                }
                ForEach(options, id: \.0) { label, key, icon in
                    Button {
                        dismiss()
                        if key == "hotel" { onHotels() }
                        else { onPick(label, key) }
                    } label: {
                        Label(label, systemImage: icon)
                            .font(.body.weight(.bold))
                            .foregroundStyle(AppColors.ink)
                    }
                }
            }
            .navigationTitle("Kategori filtrele")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Kapat") { dismiss() }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }
}
