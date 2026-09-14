import SwiftUI

// MARK: - Vets

struct VetsView: View {
    @EnvironmentObject private var auth: AuthStore
    @State private var payload: [String: Any] = [:]
    @State private var loading = true
    @State private var locating = false
    @State private var tab = "hepsi"
    @State private var ilce = ""
    @State private var sub = ""
    @State private var lat: Double?
    @State private var lng: Double?

    private let tabChips: [(String, String)] = [("hepsi", "Tümü"), ("yakin", "Yakınımda")]

    var body: some View {
        AppPage(title: "Veterinerler") {
            ScrollView {
                VStack(spacing: 0) {
                    healthHero(
                        imageUrl: payload["hero_img"] as? String ?? "",
                        emoji: "🐾",
                        subtitle: payload["page_sub"] as? String ?? "",
                        note: payload["hero_note"] as? String ?? "",
                        stats: heroStats,
                        gradient: [Color(red: 0.106, green: 0.263, blue: 0.196), Color(red: 0.251, green: 0.569, blue: 0.431)]
                    )
                    VStack(spacing: 12) {
                        nearBar
                        FilterChips(items: tabChips, selected: tab) { tab = $0; Task { await load() } }
                        if tab == "yakin" {
                            Text(yakinNote)
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(AppColors.muted)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        if tab == "hepsi" {
                            FilterChips(items: subChips, selected: sub) { sub = $0; Task { await load() } }
                            HStack {
                                Text("\(total) klinik · \(groupCount) bölge")
                                    .font(.caption.weight(.bold))
                                    .foregroundStyle(AppColors.muted)
                                Spacer()
                                IlcePicker(districts: districts, selected: $ilce)
                                    .onChange(of: ilce) { _ in Task { await load() } }
                            }
                        } else if total > 0 {
                            Text("\(total) veteriner · en yakından uzağa")
                                .font(.caption.weight(.bold))
                                .foregroundStyle(AppColors.muted)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        groupContent(emptyText: "Bu filtrede veteriner yok.", unit: "klinik")
                    }
                    .padding(16)
                }
            }
            .refreshable { await load() }
            .task { await load() }
        }
    }

    private var districts: [String] { MobileJSON.strings(payload["districts"]) }
    private var groups: [[String: Any]] { MobileJSON.maps(payload["groups"]) }
    private var total: Int { JSONValue.int(payload["total"], default: placesInGroups.count) }
    private var groupCount: Int { JSONValue.int(payload["group_count"], default: groups.count) }
    private var hospitalCount: Int { JSONValue.int(payload["hospital_count"]) }
    private var usedFallback: Bool { payload["used_fallback"] as? Bool == true }
    private var placesInGroups: [[String: Any]] {
        groups.flatMap { MobileJSON.maps($0["places"]) }
    }
    private var subChips: [(String, String)] { MobileJSON.chipItems(from: payload["subs"]) }
    private var heroStats: [String] {
        var s = ["\(total) klinik", "\(groupCount) bölge"]
        if hospitalCount > 0 { s.append("\(hospitalCount) hastane") }
        return s
    }
    private var yakinNote: String {
        if usedFallback { return "Konum alınamadı — Osmangazi merkez varsayıldı." }
        if let lat, let lng { return String(format: "Konumuna göre sıralı · %.4f, %.4f", lat, lng) }
        return "Yakın veterinerler için konumunu paylaş."
    }

    private var nearBar: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text("Yakınındaki klinikleri bul").font(.subheadline.weight(.heavy))
                Text("Konumuna göre en yakından uzağa sıralar.").font(.caption).foregroundStyle(AppColors.muted)
            }
            Spacer()
            Button(locating ? "…" : "Bul") { Task { await findNearby() } }
                .buttonStyle(.borderedProminent)
                .tint(Color(red: 0.251, green: 0.569, blue: 0.431))
                .disabled(locating)
        }
        .padding(14)
        .background(RoundedRectangle(cornerRadius: AppRadii.md).fill(AppColors.card))
    }

    @ViewBuilder
    private func groupContent(emptyText: String, unit: String) -> some View {
        if loading && groups.isEmpty {
            ProgressView().padding(.vertical, 32)
        } else if groups.isEmpty {
            Text(emptyText).foregroundStyle(AppColors.muted).padding(.vertical, 32)
        } else {
            ForEach(Array(groups.enumerated()), id: \.offset) { _, group in
                let places = MobileJSON.maps(group["places"])
                GroupHeaderRow(label: group["label"] as? String ?? "", count: places.count, unit: unit)
                ForEach(Array(places.enumerated()), id: \.offset) { _, row in
                    HealthPlaceRow(row: row, tint: Color(red: 0.251, green: 0.569, blue: 0.431))
                }
            }
        }
    }

    @MainActor
    private func load() async {
        loading = true
        defer { loading = false }
        if let json = try? await auth.apiClient().vets(
            tab: tab,
            ilce: tab == "hepsi" && !ilce.isEmpty ? ilce : nil,
            sub: tab == "hepsi" && !sub.isEmpty ? sub : nil,
            lat: tab == "yakin" ? lat : nil,
            lng: tab == "yakin" ? lng : nil
        ) {
            payload = json
        }
    }

    @MainActor
    private func findNearby() async {
        locating = true
        defer { locating = false }
        if let coord = await LocationService.requestLocation() {
            lat = coord.latitude
            lng = coord.longitude
        } else {
            lat = nil
            lng = nil
        }
        tab = "yakin"
        await load()
    }
}

// MARK: - Dentists

struct DentistsView: View {
    @EnvironmentObject private var auth: AuthStore
    @State private var payload: [String: Any] = [:]
    @State private var loading = true
    @State private var ilce = ""
    @State private var band = ""

    var body: some View {
        AppPage(title: "Diş hekimleri") {
            ScrollView {
                VStack(spacing: 0) {
                    healthHero(
                        imageUrl: payload["hero_img"] as? String ?? "",
                        emoji: "🦷",
                        subtitle: payload["page_sub"] as? String ?? "",
                        note: payload["hero_note"] as? String ?? "",
                        stats: ["\(total) kayıt", "\(groupCount) ilçe"],
                        gradient: [Color(red: 0.047, green: 0.290, blue: 0.431), Color(red: 0.008, green: 0.518, blue: 0.780)]
                    )
                    VStack(spacing: 12) {
                        FilterChips(items: bandChips, selected: band) { band = $0; Task { await load() } }
                        HStack {
                            Text("\(total) kayıt · \(groupCount) ilçe\(band.isEmpty ? "" : " · \(band)")")
                                .font(.caption.weight(.bold))
                                .foregroundStyle(AppColors.muted)
                            Spacer()
                            IlcePicker(districts: districts, selected: $ilce)
                                .onChange(of: ilce) { _ in Task { await load() } }
                        }
                        dentistGroupContent
                    }
                    .padding(16)
                }
            }
            .refreshable { await load() }
            .task { await load() }
        }
    }

    private var districts: [String] { MobileJSON.strings(payload["districts"]) }
    private var groups: [[String: Any]] { MobileJSON.maps(payload["groups"]) }
    private var total: Int { JSONValue.int(payload["total"]) }
    private var groupCount: Int { JSONValue.int(payload["group_count"], default: groups.count) }
    private var bandChips: [(String, String)] { MobileJSON.chipItems(from: payload["bands"]) }

    @ViewBuilder
    private var dentistGroupContent: some View {
        if loading && groups.isEmpty {
            ProgressView().padding(.vertical, 32)
        } else if groups.isEmpty {
            Text("Bu filtrede diş hekimi / klinik yok.").foregroundStyle(AppColors.muted).padding(.vertical, 32)
        } else {
            ForEach(Array(groups.enumerated()), id: \.offset) { _, group in
                let places = MobileJSON.maps(group["places"])
                GroupHeaderRow(label: group["label"] as? String ?? "", count: places.count, unit: "kayıt")
                ForEach(Array(places.enumerated()), id: \.offset) { _, row in
                    HealthPlaceRow(row: row, tint: Color(red: 0.008, green: 0.518, blue: 0.780))
                }
            }
        }
    }

    @MainActor
    private func load() async {
        loading = true
        defer { loading = false }
        if let json = try? await auth.apiClient().dentists(
            ilce: ilce.isEmpty ? nil : ilce,
            band: band.isEmpty ? nil : band
        ) {
            payload = json
        }
    }
}

// MARK: - Doctors

struct DoctorsView: View {
    @EnvironmentObject private var auth: AuthStore
    @State private var payload: [String: Any] = [:]
    @State private var loading = true
    @State private var ilce = ""
    @State private var spec = ""

    var body: some View {
        AppPage(title: "Doktorlar") {
            ScrollView {
                VStack(spacing: 0) {
                    healthHero(
                        imageUrl: payload["hero_img"] as? String ?? "",
                        emoji: "🩺",
                        subtitle: payload["page_sub"] as? String ?? "",
                        note: payload["hero_note"] as? String ?? "",
                        stats: ["\(total) hekim", "\(specCount) branş"],
                        gradient: [Color(red: 0.373, green: 0.153, blue: 0.553), Color(red: 0.576, green: 0.439, blue: 0.859)]
                    )
                    VStack(spacing: 12) {
                        HStack(spacing: 10) {
                            FilterDropdown(title: "Branş", items: specItems, selected: spec) { spec = $0; Task { await load() } }
                            FilterDropdown(title: "İlçe", items: [("", "Tüm ilçeler")] + districts.map { ($0, $0) }, selected: ilce) { ilce = $0; Task { await load() } }
                        }
                        Text("\(total) hekim · \(specCount) branş\(spec.isEmpty ? "" : " · \(specLabel)")\(ilce.isEmpty ? "" : " · \(ilce)")")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(AppColors.muted)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        doctorGroupContent
                    }
                    .padding(16)
                }
            }
            .refreshable { await load() }
            .task { await load() }
        }
    }

    private var districts: [String] { MobileJSON.strings(payload["districts"]) }
    private var groups: [[String: Any]] { MobileJSON.maps(payload["groups"]) }
    private var total: Int { JSONValue.int(payload["total"]) }
    private var specCount: Int { JSONValue.int(payload["spec_count"], default: groups.count) }
    private var specItems: [(String, String)] { MobileJSON.chipItems(from: payload["specs"], allLabel: "Tüm branşlar") }
    private var specLabel: String {
        specItems.first(where: { $0.0 == spec })?.1 ?? spec
    }

    @ViewBuilder
    private var doctorGroupContent: some View {
        if loading && groups.isEmpty {
            ProgressView().padding(.vertical, 32)
        } else if groups.isEmpty {
            Text("Bu filtrede hekim yok.").foregroundStyle(AppColors.muted).padding(.vertical, 32)
        } else {
            ForEach(Array(groups.enumerated()), id: \.offset) { _, group in
                let places = MobileJSON.maps(group["places"])
                GroupHeaderRow(label: group["label"] as? String ?? "", count: places.count, unit: "hekim")
                ForEach(Array(places.enumerated()), id: \.offset) { _, row in
                    HealthPlaceRow(row: row, tint: Color(red: 0.576, green: 0.439, blue: 0.859))
                }
            }
        }
    }

    @MainActor
    private func load() async {
        loading = true
        defer { loading = false }
        if let json = try? await auth.apiClient().doctors(
            ilce: ilce.isEmpty ? nil : ilce,
            spec: spec.isEmpty ? nil : spec
        ) {
            payload = json
        }
    }
}

// MARK: - Hospitals

struct HospitalsView: View {
    @EnvironmentObject private var auth: AuthStore
    @State private var payload: [String: Any] = [:]
    @State private var loading = true
    @State private var ilce = ""
    @State private var band = ""

    var body: some View {
        AppPage(title: "Hastaneler") {
            ScrollView {
                VStack(spacing: 0) {
                    healthHero(
                        imageUrl: payload["hero_img"] as? String ?? "",
                        emoji: "🏥",
                        subtitle: payload["page_sub"] as? String ?? "",
                        note: payload["hero_note"] as? String ?? "",
                        stats: ["\(total) hastane", "\(groupCount) ilçe"],
                        gradient: [Color(red: 0.573, green: 0.051, blue: 0.051), Color(red: 0.863, green: 0.149, blue: 0.149)]
                    )
                    VStack(spacing: 12) {
                        FilterChips(items: bandChips, selected: band) { band = $0; Task { await load() } }
                        HStack {
                            Text("\(total) hastane · \(groupCount) ilçe\(band.isEmpty ? "" : " · \(band)")")
                                .font(.caption.weight(.bold))
                                .foregroundStyle(AppColors.muted)
                            Spacer()
                            IlcePicker(districts: districts, selected: $ilce)
                                .onChange(of: ilce) { _ in Task { await load() } }
                        }
                        hospitalGroupContent
                    }
                    .padding(16)
                }
            }
            .refreshable { await load() }
            .task { await load() }
        }
    }

    private var districts: [String] { MobileJSON.strings(payload["districts"]) }
    private var groups: [[String: Any]] { MobileJSON.maps(payload["groups"]) }
    private var total: Int { JSONValue.int(payload["total"]) }
    private var groupCount: Int { JSONValue.int(payload["group_count"], default: groups.count) }
    private var bandChips: [(String, String)] { MobileJSON.chipItems(from: payload["bands"]) }

    @ViewBuilder
    private var hospitalGroupContent: some View {
        if loading && groups.isEmpty {
            ProgressView().padding(.vertical, 32)
        } else if groups.isEmpty {
            Text("Bu filtrede hastane yok.").foregroundStyle(AppColors.muted).padding(.vertical, 32)
        } else {
            ForEach(Array(groups.enumerated()), id: \.offset) { _, group in
                let places = MobileJSON.maps(group["places"])
                GroupHeaderRow(label: group["label"] as? String ?? "", count: places.count, unit: "hastane")
                ForEach(Array(places.enumerated()), id: \.offset) { _, row in
                    HealthPlaceRow(row: row, tint: Color(red: 0.863, green: 0.149, blue: 0.149))
                }
            }
        }
    }

    @MainActor
    private func load() async {
        loading = true
        defer { loading = false }
        if let json = try? await auth.apiClient().hospitals(
            ilce: ilce.isEmpty ? nil : ilce,
            band: band.isEmpty ? nil : band
        ) {
            payload = json
        }
    }
}

// MARK: - Shared health UI

@ViewBuilder
private func healthHero(
    imageUrl: String,
    emoji: String,
    subtitle: String,
    note: String,
    stats: [String],
    gradient: [Color]
) -> some View {
    ZStack(alignment: .bottomLeading) {
        if !imageUrl.isEmpty {
            RemoteImage(url: imageUrl, placeholder: "photo")
                .frame(height: 188)
                .frame(maxWidth: .infinity)
                .clipped()
        } else {
            LinearGradient(colors: gradient, startPoint: .bottomLeading, endPoint: .topTrailing)
                .frame(height: 188)
        }
        LinearGradient(colors: [gradient.first?.opacity(0.94) ?? AppColors.nav, gradient.last?.opacity(0.55) ?? AppColors.nav], startPoint: .bottomLeading, endPoint: .topTrailing)
            .frame(height: 188)
        VStack(alignment: .leading, spacing: 8) {
            Text(emoji).font(.largeTitle)
            Spacer()
            if !subtitle.isEmpty {
                Text(subtitle).font(.caption).foregroundStyle(.white.opacity(0.88))
            }
            WrapStatsChips(items: stats)
            if !note.isEmpty {
                Text(note).font(.caption2).foregroundStyle(.white.opacity(0.65))
            }
        }
        .padding(20)
        .frame(height: 188, alignment: .bottomLeading)
    }
}

private struct WrapStatsChips: View {
    let items: [String]

    var body: some View {
        FlowLayout(spacing: 8) {
            ForEach(items, id: \.self) { label in
                Text(label)
                    .font(.caption2.weight(.heavy))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(Color.white.opacity(0.16))
                    .foregroundStyle(.white)
                    .clipShape(Capsule())
                    .overlay(Capsule().stroke(Color.white.opacity(0.22)))
            }
        }
    }
}

private struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? 0
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        for sub in subviews {
            let size = sub.sizeThatFits(.unspecified)
            if x + size.width > width, x > 0 {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
        }
        return CGSize(width: width, height: y + rowHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX
        var y = bounds.minY
        var rowHeight: CGFloat = 0
        for sub in subviews {
            let size = sub.sizeThatFits(.unspecified)
            if x + size.width > bounds.maxX, x > bounds.minX {
                x = bounds.minX
                y += rowHeight + spacing
                rowHeight = 0
            }
            sub.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
        }
    }
}

private struct HealthPlaceRow: View {
    let row: [String: Any]
    let tint: Color

    var body: some View {
        let slug = (row["slug"] as? String ?? PlaceItem.slugFromPath(row["path"] as? String ?? "")).trimmingCharacters(in: .whitespacesAndNewlines)
        let title = row["title"] as? String ?? row["name"] as? String ?? "Kayıt"
        let initial = (row["initial"] as? String ?? String(title.prefix(1))).uppercased()
        let address = row["address"] as? String ?? ""
        let ilce = row["ilce"] as? String ?? ""
        let subLabel = row["subcategory_label"] as? String ?? row["price_band"] as? String ?? row["spec_label"] as? String ?? ""
        let distance = row["distance_label"] as? String ?? ""
        let hours = row["hours_short"] as? String ?? row["rating_label"] as? String ?? ""
        let phone = row["phone"] as? String ?? row["tel"] as? String ?? ""
        let maps = row["maps"] as? String ?? ""
        let img = row["img_url"] as? String ?? ""

        let meta = [distance, subLabel, address.isEmpty ? ilce : address].filter { !$0.isEmpty }.joined(separator: " · ")

        let content = HStack(alignment: .top, spacing: 12) {
            Group {
                if !img.isEmpty {
                    RemoteImage(url: img, placeholder: "cross.case.fill")
                } else {
                    Text(initial)
                        .font(.title2.weight(.black))
                        .foregroundStyle(tint)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .background(tint.opacity(0.15))
                }
            }
            .frame(width: 56, height: 56)
            .clipShape(RoundedRectangle(cornerRadius: 14))

            VStack(alignment: .leading, spacing: 6) {
                Text(title).font(.subheadline.weight(.heavy))
                if !meta.isEmpty {
                    Text(meta).font(.caption).foregroundStyle(AppColors.muted).lineLimit(3)
                }
                HStack(spacing: 6) {
                    if !phone.isEmpty { PhoneLink(phone: phone) }
                    if !maps.isEmpty { MapsLink(urlString: maps, label: "Yol tarifi") }
                }
            }
            if !hours.isEmpty {
                Text(hours.contains("★") ? hours : hours)
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(AppColors.muted)
                    .multilineTextAlignment(.trailing)
            }
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: AppRadii.md).fill(AppColors.card))

        if slug.isEmpty {
            content
        } else {
            NavigationLink(value: slug) { content }.buttonStyle(.plain)
        }
    }
}
