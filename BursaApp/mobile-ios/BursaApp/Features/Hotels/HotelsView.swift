import SwiftUI

struct HotelsView: View {
    @EnvironmentObject private var auth: AuthStore
    @State private var payload: [String: Any] = [:]
    @State private var loading = true
    @State private var error: String?

    @State private var queryText = ""
    @State private var q = ""
    @State private var band = ""
    @State private var price = ""
    @State private var sort = "rating"
    @State private var ilce = ""
    @State private var sub = ""

    private let bandChips: [(String, String)] = [
        ("", "Tümü"), ("termal", "Termal"), ("uludag", "Uludağ"),
        ("sehir", "Şehir"), ("butik", "Butik"),
    ]
    private let priceChips: [(String, String)] = [
        ("", "Tümü"), ("lt10", "10K altı"), ("10-18", "10–18K"), ("18plus", "18K+"),
    ]
    private let sortItems: [(String, String)] = [
        ("rating", "Puana göre"), ("price_asc", "Fiyat ↑"), ("price_desc", "Fiyat ↓"),
    ]

    var body: some View {
        AppPage(title: "Oteller") {
            ScrollView {
                VStack(spacing: 0) {
                    if let hero = payload["hero_img"] as? String, !hero.isEmpty {
                        HeroBanner(
                            imageUrl: hero,
                            height: 220,
                            title: "Bursa otelleri",
                            subtitle: "Termal Çekirge, şehir otelleri ve Uludağ — rezervasyon siteden yapılmaz."
                        )
                    }
                    VStack(alignment: .leading, spacing: 12) {
                        searchBox
                        FilterChips(items: bandChips, selected: band) { applyBand($0) }
                        FilterChips(items: priceChips, selected: price) { key in
                            price = key
                            Task { await load() }
                        }
                        HStack(spacing: 10) {
                            FilterDropdown(title: "Sırala", items: sortItems, selected: sort) { key in
                                sort = key
                                Task { await load() }
                            }
                            FilterDropdown(
                                title: "İlçe",
                                items: [("", "Tümü")] + districts.map { ($0, $0) },
                                selected: ilce
                            ) { key in
                                ilce = key
                                Task { await load() }
                            }
                        }
                        Text(metaNote)
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(AppColors.muted)
                            .frame(maxWidth: .infinity, alignment: .center)
                        featureGrid
                        SectionHeader(title: sectionTitle, subtitle: sort.starts(with: "price") ? "Fiyata göre" : "Öne çıkanlar")
                        if loading && placeMaps.isEmpty && featuredMaps.isEmpty {
                            ProgressView().frame(maxWidth: .infinity).padding(.vertical, 32)
                        } else if placeMaps.isEmpty && featuredMaps.isEmpty {
                            Text("Bu filtrede otel yok.").foregroundStyle(AppColors.muted).frame(maxWidth: .infinity).padding(.vertical, 32)
                        } else {
                            hotelGrid(featuredMaps.isEmpty ? Array(placeMaps.prefix(8)) : featuredMaps)
                        }
                        if !restMaps.isEmpty {
                            SectionHeader(title: "Bursa otelleri", subtitle: "Tüm liste")
                            hotelGrid(restMaps)
                        }
                        campCta
                        whyBlock
                    }
                    .padding(16)
                }
            }
            .refreshable { await load() }
            .task { await load() }
        }
    }

    private var districts: [String] {
        MobileJSON.strings(payload["districts"])
    }

    private var placeMaps: [[String: Any]] {
        MobileJSON.maps(payload["places"])
    }

    private var featuredMaps: [[String: Any]] {
        MobileJSON.maps(payload["featured"])
    }

    private var featuredSlugs: Set<String> {
        Set((payload["featured_slugs"] as? [String] ?? []).map { $0.trimmingCharacters(in: .whitespacesAndNewlines) })
    }

    private var restMaps: [[String: Any]] {
        placeMaps.filter { row in
            let slug = (row["slug"] as? String ?? PlaceItem.slugFromPath(row["path"] as? String ?? "")).trimmingCharacters(in: .whitespacesAndNewlines)
            return !featuredSlugs.contains(slug)
        }
    }

    private var total: Int {
        JSONValue.int(payload["total"], default: placeMaps.count)
    }

    private var sectionTitle: String {
        switch sort {
        case "price_asc": return "En uygun oteller"
        case "price_desc": return "En yüksek fiyatlı oteller"
        default: return "Beğeneceğin oteller"
        }
    }

    private var metaNote: String {
        var parts = ["\(total) otel"]
        let meta = payload["price_meta"] as? [String: Any] ?? [:]
        let cin = meta["check_in"] as? String ?? ""
        let cout = meta["check_out"] as? String ?? ""
        if !cin.isEmpty, !cout.isEmpty {
            parts.append("gecelik fiyat (\(cin) → \(cout))")
        } else {
            parts.append("gecelik fiyat")
        }
        if sort == "price_asc" { parts.append("en ucuz üstte") }
        else if sort == "price_desc" { parts.append("en pahalı üstte") }
        if !price.isEmpty { parts.append("fiyat filtresi aktif") }
        return parts.joined(separator: " · ")
    }

    private var searchBox: some View {
        HStack {
            TextField("Otel, semt, ilçe…", text: $queryText)
                .textFieldStyle(.plain)
                .submitLabel(.search)
                .onSubmit { submitSearch() }
            Button(action: submitSearch) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(AppColors.accentDeep)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(RoundedRectangle(cornerRadius: AppRadii.md).fill(AppColors.card))
        .overlay(RoundedRectangle(cornerRadius: AppRadii.md).stroke(AppColors.muted.opacity(0.12)))
    }

    private var featureGrid: some View {
        let items: [(String, String, String)] = [
            ("🏨", "Doğru oteli bul", "Termal, Uludağ, şehir"),
            ("📍", "İlçe ilçe", "Gerçek konum bilgisi"),
            ("★", "Misafir puanı", "Skora göre sırala"),
            ("💸", "Örnek fiyat", "Kesin teklif otelden"),
        ]
        return LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
            ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                VStack(alignment: .leading, spacing: 4) {
                    Text(item.0).font(.title2)
                    Text(item.1).font(.caption.weight(.heavy))
                    Text(item.2).font(.caption2).foregroundStyle(AppColors.muted)
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: AppRadii.sm).fill(AppColors.card))
            }
        }
    }

    private var campCta: some View {
        NavigationLink {
            CategoryPlacesView(title: "Kamp alanları", category: "camp")
        } label: {
            VStack(alignment: .leading, spacing: 8) {
                Text("Doğa mı, termal mi? Kamp da listede.")
                    .font(.headline.weight(.black))
                    .foregroundStyle(.white)
                Text("Uludağ koyları, gölet kenarı ve ücretsiz alanlar — otel istemeyenler için.")
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.75))
                Text("Kamp yerlerine git →")
                    .font(.caption.weight(.heavy))
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .background(Color.white)
                    .foregroundStyle(AppColors.nav)
                    .clipShape(Capsule())
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: AppRadii.md).fill(AppColors.nav))
        }
        .buttonStyle(.plain)
    }

    private var whyBlock: some View {
        let items: [(String, String, String)] = [
            ("🗺", "Yerel liste", "Bursa odaklı — şehir, termal ve dağ bir arada."),
            ("📷", "Gerçek fotoğraflar", "Otel sayfalarında galeri; mekanı önce gör."),
            ("🔒", "Rezervasyon yok", "Kart bilgisi istemeyiz; oteli sen ararsın."),
            ("🌿", "Gezi + yemek", "Konaklamanın yanına rota ve restoran ekle."),
        ]
        return VStack(alignment: .leading, spacing: 12) {
            SectionHeader(title: "Konaklamayı sade tutuyoruz", subtitle: "Neden BursaApp")
            ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                HStack(alignment: .top, spacing: 12) {
                    Text(item.0).font(.title3)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(item.1).font(.subheadline.weight(.heavy))
                        Text(item.2).font(.caption).foregroundStyle(AppColors.muted)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func hotelGrid(_ rows: [[String: Any]]) -> some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                if let place = PlaceItem.decode(from: row) {
                    NavigationLink(value: place.detailSlug) {
                        HotelCard(place: place, raw: row)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private func applyBand(_ key: String) {
        band = key
        if key == "butik" {
            sub = "butik"
        } else if sub == "butik" {
            sub = ""
        }
        Task { await load() }
    }

    private func submitSearch() {
        q = queryText.trimmingCharacters(in: .whitespacesAndNewlines)
        Task { await load() }
    }

    @MainActor
    private func load() async {
        loading = true
        error = nil
        defer { loading = false }
        do {
            let apiBand = band == "butik" ? "" : band
            let apiSub = band == "butik" ? "butik" : sub
            payload = try await auth.apiClient().hotels(
                q: q.isEmpty ? nil : q,
                ilce: ilce.isEmpty ? nil : ilce,
                sub: apiSub.isEmpty ? nil : apiSub,
                band: apiBand.isEmpty ? nil : apiBand,
                sort: sort,
                price: price.isEmpty ? nil : price
            )
        } catch {
            self.error = error.localizedDescription
        }
    }
}

private struct HotelCard: View {
    let place: PlaceItem
    let raw: [String: Any]?

    init(place: PlaceItem, raw: [String: Any]?) {
        self.place = place
        self.raw = raw
    }

    var body: some View {
        let band = (raw?["price_band"] as? String ?? "sehir").lowercased()
        let badge = raw?["badge_label"] as? String ?? "OTEL"
        let priceLabel = raw?["price_label"] as? String ?? "Fiyat sor"
        let extra = raw?["extra"] as? [String: Any] ?? [:]
        let checkIn = extra["price_check_in"] as? String ?? ""
        let rating = raw?["rating"]
        let ratingText: String? = {
            if let n = rating as? NSNumber { return String(format: "%.1f", n.doubleValue) }
            if let d = rating as? Double { return String(format: "%.1f", d) }
            return nil
        }()
        let address = raw?["address"] as? String ?? ""
        let addrShort = address.split(separator: ",").first.map(String.init) ?? ""
        let subLabel = raw?["subcategory_label"] as? String ?? place.subcategory

        VStack(alignment: .leading, spacing: 0) {
            ZStack(alignment: .topLeading) {
                RemoteImage(url: place.imgUrl, placeholder: "bed.double.fill")
                    .frame(height: 108)
                    .frame(maxWidth: .infinity)
                    .clipped()
                Text(badge)
                    .font(.caption2.weight(.black))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(badgeColor(band))
                    .foregroundStyle(.white)
                    .clipShape(Capsule())
                    .padding(8)
            }
            VStack(alignment: .leading, spacing: 4) {
                Text("\(priceLabel) / gece\(checkIn.isEmpty ? "" : " · \(checkIn)")")
                    .font(.subheadline.weight(.black))
                    .lineLimit(2)
                Text(place.title)
                    .font(.caption.weight(.heavy))
                    .lineLimit(2)
                Text(addrShort.isEmpty ? place.ilce : "\(place.ilce) · \(addrShort)")
                    .font(.caption2)
                    .foregroundStyle(AppColors.muted)
                    .lineLimit(2)
                HStack(spacing: 6) {
                    if let ratingText { MetaChip(text: "★ \(ratingText)", color: AppColors.muted) }
                    if !subLabel.isEmpty { MetaChip(text: subLabel, color: AppColors.muted) }
                }
            }
            .padding(10)
        }
        .background(RoundedRectangle(cornerRadius: AppRadii.md).fill(AppColors.card))
        .overlay(RoundedRectangle(cornerRadius: AppRadii.md).stroke(AppColors.muted.opacity(0.08)))
    }

    private func badgeColor(_ band: String) -> Color {
        switch band {
        case "termal": return Color(red: 0.059, green: 0.463, blue: 0.431)
        case "uludag": return Color(red: 0.114, green: 0.306, blue: 0.863)
        case "butik": return Color(red: 0.486, green: 0.227, blue: 0.929)
        default: return AppColors.nav
        }
    }
}
