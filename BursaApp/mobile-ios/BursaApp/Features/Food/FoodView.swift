import SwiftUI

struct FoodView: View {
    @EnvironmentObject private var auth: AuthStore
    @StateObject private var vm = FoodViewModel()
    @State private var path = NavigationPath()
    @State private var showSearch = false
    @State private var showFilter = false
    @State private var showAuth = false
    @State private var query = ""

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView(showsIndicators: false) {
                VStack(alignment: .leading, spacing: AppSpacing.section) {
                    TravelTopBar(location: "Bursa, Türkiye", notificationCount: 0, onNotificationsTap: {})
                    foodHeroTitle
                    TravelSearchCapsule(query: $query, placeholder: "Restoran, kafe ara…", onSearchTap: { showSearch = true })
                        .onChange(of: query) { _ in vm.applyFilters() }

                    TravelSectionHeader(title: "Önerilen", onSeeAll: { showSearch = true })
                    if vm.suggested.isEmpty {
                        travelSkeleton(height: 190)
                    } else {
                        TabView {
                            ForEach(vm.suggested) { place in
                                NavigationLink(value: place.detailSlug) {
                                    TravelFeaturedCard(place: place)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        .tabViewStyle(.page(indexDisplayMode: .always))
                        .frame(height: 230)
                    }

                    TravelSectionHeader(title: "Popüler mekanlar", onSeeAll: { showSearch = true })
                    LazyVGrid(columns: [GridItem(.flexible(), spacing: 12), GridItem(.flexible())], spacing: 12) {
                        ForEach(vm.featured) { place in
                            NavigationLink(value: place.detailSlug) {
                                foodGridCard(place)
                            }
                            .buttonStyle(.plain)
                        }
                    }

                    TravelSectionHeader(title: "Topluluk paylaşımları")
                    ForEach(vm.posts) { post in
                        foodPostCard(post)
                    }
                    ForEach(vm.placePosts) { place in
                        NavigationLink(value: place.detailSlug) {
                            TravelFeaturedCard(place: place)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, AppSpacing.screenX)
                .padding(.bottom, 100)
            }
            .background(AppColors.bg.ignoresSafeArea())
            .refreshable { await vm.load(auth: auth) }
            .task { await vm.load(auth: auth) }
            .navigationDestination(for: String.self) { slug in PlaceDetailView(slug: slug) }
            .sheet(isPresented: $showSearch) { NavigationStack { PlaceSearchView(initialQuery: vm.query) } }
            .sheet(isPresented: $showFilter) {
                foodFilterSheet
            }
            .sheet(isPresented: $showAuth) { AuthFlowView() }
        }
    }

    private var foodHeroTitle: some View {
        (
            Text("Lezzet\n")
                .foregroundColor(AppColors.ink)
            + Text("durakları ")
                .foregroundColor(AppColors.nav)
            + Text("keşfet")
                .foregroundColor(AppColors.ink)
        )
        .font(AppTypography.screenTitle)
    }

    private func foodGridCard(_ place: PlaceItem) -> some View {
        ZStack(alignment: .bottomLeading) {
            RemoteImage(url: place.imgUrl, placeholder: "fork.knife")
                .frame(height: 150).frame(maxWidth: .infinity).clipped()
            LinearGradient(colors: [.clear, .black.opacity(0.6)], startPoint: .center, endPoint: .bottom)
            Text(place.title).font(.caption.weight(.heavy)).foregroundStyle(.white).padding(10).lineLimit(2)
        }
        .clipShape(RoundedRectangle(cornerRadius: AppRadii.md))
    }

    private func foodPostCard(_ item: FeedItem) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(item.user.name).font(.subheadline.weight(.bold))
                Spacer()
                HStack(spacing: 4) {
                    Image(systemName: "star.fill").foregroundStyle(AppColors.amber).font(.caption2)
                    Text(travelRating(seed: item.id)).font(.caption.weight(.heavy))
                }
            }
            if let first = item.images.first {
                RemoteImage(url: first, placeholder: "photo")
                    .frame(height: 180).frame(maxWidth: .infinity).clipped()
                    .clipShape(RoundedRectangle(cornerRadius: AppRadii.md))
            }
            if !item.body.isEmpty {
                Text(item.body).font(.subheadline).foregroundStyle(AppColors.muted)
            }
        }
        .padding(14)
        .background(RoundedRectangle(cornerRadius: AppRadii.md).fill(.white).shadow(color: .black.opacity(0.05), radius: 8, y: 3))
    }

    private var foodFilterSheet: some View {
        NavigationStack {
            List {
                Button("Restoran & kafe") { vm.categoryFilter = "food"; Task { await vm.load(auth: auth) }; showFilter = false }
                Button("Canlı müzik") { vm.categoryFilter = "live"; Task { await vm.load(auth: auth) }; showFilter = false }
                Button("Eğlence") { vm.categoryFilter = "fun2"; Task { await vm.load(auth: auth) }; showFilter = false }
            }
            .navigationTitle("Filtrele")
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Kapat") { showFilter = false } } }
        }
        .presentationDetents([.medium])
    }
}

@MainActor
final class FoodViewModel: ObservableObject {
    @Published var query = ""
    @Published var categoryFilter = "food"
    @Published private(set) var allPlaces: [PlaceItem] = []
    @Published private(set) var suggested: [PlaceItem] = []
    @Published private(set) var featured: [PlaceItem] = []
    @Published private(set) var posts: [FeedItem] = []
    @Published private(set) var placePosts: [PlaceItem] = []
    @Published private(set) var loading = false

    func load(auth: AuthStore) async {
        loading = true
        defer { loading = false }
        do {
            let api = auth.apiClient()
            async let feedRes = api.feed(offset: 0)
            var rows: [PlaceItem]
            switch categoryFilter {
            case "live":
                let funRows = try await api.places(category: "fun", spec: "Canlı müzik", limit: 20)
                let barRows = try await api.places(category: "nightlife", sub: "canli-muzik", limit: 20)
                var seen = Set<String>()
                rows = (funRows + barRows).filter { p in
                    guard !p.slug.isEmpty, !seen.contains(p.slug) else { return false }
                    seen.insert(p.slug)
                    return true
                }
            case "fun2":
                rows = try await api.places(category: "fun", limit: 30)
            default:
                rows = try await api.places(category: "food", limit: 40)
            }
            allPlaces = rows
            posts = try await feedRes.feed
            applyFilters()
        } catch {
            allPlaces = []
            posts = []
            applyFilters()
        }
    }

    func applyFilters() {
        var rows = allPlaces
        if !query.isEmpty {
            rows = rows.filter {
                $0.title.localizedCaseInsensitiveContains(query)
                    || $0.ilce.localizedCaseInsensitiveContains(query)
                    || $0.blurb.localizedCaseInsensitiveContains(query)
            }
        }
        suggested = Array(rows.prefix(5))
        featured = Array(rows.dropFirst(5).prefix(4))
        placePosts = Array(rows.dropFirst(9).prefix(8))
    }
}

private func travelSkeleton(height: CGFloat) -> some View {
    RoundedRectangle(cornerRadius: AppRadii.md).fill(AppColors.bgSoft).frame(height: height)
}
