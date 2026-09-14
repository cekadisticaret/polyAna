import SwiftUI

struct VisitView: View {
    @EnvironmentObject private var auth: AuthStore
    @EnvironmentObject private var shellNav: ShellNavigator
    @Environment(\.dismiss) private var dismiss

    @State private var places: [PlaceItem] = []
    @State private var meta: [String: Any] = [:]
    @State private var loading = true
    @State private var error: String?
    @State private var query = ""
    @State private var sort = "featured"
    @State private var ilce = ""
    @State private var kinds: Set<String> = []
    @State private var fees: Set<String> = []
    @State private var tags: Set<String> = []
    @State private var page = 1

    private let sortChips = [("featured", "Öne çıkan"), ("rating", "Puan"), ("name", "A–Z")]

    private var heroPlaces: [PlaceItem] {
        MobileJSON.maps(meta["hero"]).compactMap { PlaceItem.decode(from: $0) }
    }

    private var heroImage: String {
        heroPlaces.first?.imgUrl ?? meta["hero_img"] as? String ?? ""
    }

    private var districts: [String] { MobileJSON.strings(meta["districts"]) }
    private var kindItems: [(String, String)] { MobileJSON.chipItems(from: meta["kinds"], allLabel: "Tümü") }
    private var feeItems: [(String, String)] {
        MobileJSON.maps(meta["fees"]).compactMap { row in
            guard let key = row["key"] as? String, let label = row["label"] as? String else { return nil }
            return (key, label)
        }
    }
    private var tagItems: [(String, String)] {
        MobileJSON.maps(meta["tags"]).compactMap { row in
            guard let key = row["key"] as? String, let label = row["label"] as? String else { return nil }
            return (key, label)
        }
    }

    private var total: Int { JSONValue.int(meta["total"], default: places.count) }
    private var currentPage: Int { JSONValue.int(meta["page"], default: page) }
    private var totalPages: Int { JSONValue.int(meta["pages"], default: 1) }
    private var hasMore: Bool { currentPage < totalPages }

    private var hasFilters: Bool {
        !query.isEmpty || !ilce.isEmpty || !kinds.isEmpty || !fees.isEmpty || !tags.isEmpty || sort != "featured"
    }

    var body: some View {
        AppPage(title: "Gezilecek yerler") {
            ScrollView {
                VStack(spacing: 0) {
                    visitHero
                    if !heroPlaces.isEmpty {
                        featuredCarousel
                            .padding(.top, 14)
                    }
                    VStack(alignment: .leading, spacing: 12) {
                        searchRow
                        if kindItems.count > 1 {
                            MultiFilterChips(label: "Tür", items: kindItems, selected: kinds, onToggle: toggleKind)
                        }
                        if !feeItems.isEmpty {
                            MultiFilterChips(label: "Giriş", items: feeItems, selected: fees, onToggle: toggleFee)
                        }
                        if !tagItems.isEmpty {
                            MultiFilterChips(label: "Öne çıkan", items: tagItems, selected: tags, onToggle: toggleTag)
                        }
                        FilterChips(items: sortChips, selected: sort) { sort = $0; Task { await load(refresh: true) } }
                        IlcePicker(districts: districts, selected: $ilce)
                            .onChange(of: ilce) { _ in Task { await load(refresh: true) } }
                        HStack {
                            Text("\(total) sonuç\(query.isEmpty ? "" : " · “\(query)”")")
                                .font(.caption.weight(.bold))
                                .foregroundStyle(AppColors.muted)
                            Spacer()
                            if hasFilters {
                                Button("Temizle") { clearFilters() }
                                    .font(.caption.weight(.heavy))
                            }
                        }
                        visitFeatureRow
                        LoadingStateView(
                            loading: loading && places.isEmpty,
                            error: error,
                            empty: !loading && places.isEmpty,
                            emptyText: "Bu filtrede yer yok."
                        )
                        LazyVStack(spacing: 12) {
                            ForEach(places) { place in
                                NavigationLink(value: place.detailSlug) {
                                    EventPlaceCard(place: place)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        if hasMore && !loading {
                            Button("Daha fazla yükle") { Task { await loadMore() } }
                                .buttonStyle(.bordered)
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .padding(16)
                }
            }
            .refreshable { await load(refresh: true) }
            .task { await load(refresh: true) }
        }
    }

    private var visitHero: some View {
        ZStack(alignment: .bottomLeading) {
            if heroImage.isEmpty {
                LinearGradient(colors: [AppColors.bgDeep, AppColors.accentDeep], startPoint: .bottomLeading, endPoint: .topTrailing)
            } else {
                RemoteImage(url: heroImage, placeholder: "photo")
                    .scaledToFill()
            }
            LinearGradient(
                colors: [AppColors.nav.opacity(0.92), AppColors.nav.opacity(0.45)],
                startPoint: .bottomLeading,
                endPoint: .topTrailing
            )
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Gezilecek yerler")
                            .font(.title2.weight(.black))
                            .foregroundStyle(.white)
                        Text("Tarih · doğa · müze · manzara")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.white.opacity(0.85))
                    }
                    Spacer()
                    Button {
                        dismiss()
                        shellNav.openExplore()
                    } label: {
                        Label("Harita", systemImage: "map.fill")
                            .font(.caption.weight(.heavy))
                            .foregroundStyle(AppColors.nav)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                            .background(Capsule().fill(AppColors.lime))
                    }
                }
            }
            .padding(20)
        }
        .frame(height: 200)
        .clipped()
    }

    private var featuredCarousel: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 12) {
                ForEach(heroPlaces) { place in
                    NavigationLink(value: place.detailSlug) {
                        VStack(alignment: .leading, spacing: 0) {
                            RemoteImage(url: place.imgUrl, placeholder: "photo")
                                .frame(width: 200, height: 120)
                                .clipped()
                            Text(place.title)
                                .font(.caption.weight(.heavy))
                                .foregroundStyle(AppColors.ink)
                                .lineLimit(2)
                                .padding(10)
                                .frame(width: 200, alignment: .leading)
                        }
                        .background(RoundedRectangle(cornerRadius: AppRadii.md).fill(AppColors.card).cardShadow())
                        .clipShape(RoundedRectangle(cornerRadius: AppRadii.md))
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 16)
        }
    }

    private var searchRow: some View {
        HStack {
            TextField("Ara…", text: $query)
                .textFieldStyle(.roundedBorder)
                .submitLabel(.search)
                .onSubmit { Task { await load(refresh: true) } }
            Button("Ara") { Task { await load(refresh: true) } }
                .buttonStyle(.borderedProminent)
                .tint(AppColors.accentDeep)
        }
    }

    private var visitFeatureRow: some View {
        HStack(spacing: 8) {
            MetaChip(text: "Ücretsiz seçenekler")
            MetaChip(text: "Aile dostu", color: AppColors.sky)
            MetaChip(text: "Fotoğraf", color: AppColors.pink)
        }
    }

    private func toggleKind(_ key: String) {
        if kinds.contains(key) { kinds.remove(key) } else { kinds.insert(key) }
        Task { await load(refresh: true) }
    }

    private func toggleFee(_ key: String) {
        if fees.contains(key) { fees.remove(key) } else { fees.insert(key) }
        Task { await load(refresh: true) }
    }

    private func toggleTag(_ key: String) {
        if tags.contains(key) { tags.remove(key) } else { tags.insert(key) }
        Task { await load(refresh: true) }
    }

    private func clearFilters() {
        query = ""
        ilce = ""
        kinds.removeAll()
        fees.removeAll()
        tags.removeAll()
        sort = "featured"
        Task { await load(refresh: true) }
    }

    @MainActor
    private func load(refresh: Bool) async {
        if refresh { page = 1 }
        loading = true
        error = nil
        defer { loading = false }
        do {
            let json = try await auth.apiClient().visitPlaces(
                page: page, q: query, ilce: ilce, sort: sort,
                kinds: Array(kinds), fees: Array(fees), tags: Array(tags)
            )
            meta = json
            let next = PlaceItem.list(from: json)
            places = refresh ? next : places + next
        } catch {
            self.error = error.localizedDescription
        }
    }

    @MainActor
    private func loadMore() async {
        page += 1
        await load(refresh: false)
    }
}
