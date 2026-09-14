import SwiftUI

// MARK: - Pharmacy

struct PharmacyView: View {
    @EnvironmentObject private var auth: AuthStore
    @State private var payload: [String: Any] = [:]
    @State private var ilce = ""
    @State private var lat: Double?
    @State private var lng: Double?
    @State private var loading = true
    @State private var locating = false

    var body: some View {
        AppPage(title: "Nöbetçi eczaneler") {
            ScrollView {
                VStack(spacing: 0) {
                    pharmacyHero
                    VStack(spacing: 12) {
                        HStack {
                            Text(countLabel)
                                .font(.caption.weight(.bold))
                                .foregroundStyle(AppColors.muted)
                            Spacer()
                            if hasGeo {
                                Button("İlçe sırası") { clearGeo() }
                                    .font(.caption.weight(.heavy))
                            } else {
                                Button(locating ? "…" : "📍 Konuma göre") { Task { await sortByLocation() } }
                                    .buttonStyle(.borderedProminent)
                                    .tint(Color(red: 0.263, green: 0.627, blue: 0.278))
                                    .font(.caption.weight(.heavy))
                                    .disabled(locating)
                            }
                        }
                        if hasGeo {
                            Button("Konumu yenile") { Task { await sortByLocation() } }
                                .font(.caption)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        districtPicker
                        pharmacyGroups
                    }
                    .padding(16)
                }
            }
            .refreshable { await load() }
            .task { await load() }
        }
    }

    private var groups: [[String: Any]] { MobileJSON.maps(payload["groups"]) }
    private var districts: [String] { MobileJSON.strings(payload["districts"]) }
    private var count: Int { JSONValue.int(payload["count"]) }
    private var total: Int { JSONValue.int(payload["total"], default: count) }
    private var groupCount: Int { JSONValue.int(payload["group_count"], default: groups.count) }
    private var hasGeo: Bool { payload["has_geo"] as? Bool == true }
    private var dutyLabel: String {
        payload["duty_label"] as? String ?? payload["duty_date"] as? String ?? "Bursa"
    }

    private var countLabel: String {
        var parts = ["\(count) eczane"]
        if !ilce.isEmpty { parts.append(ilce) }
        if hasGeo { parts.append("yakından uzağa") }
        return parts.joined(separator: " · ")
    }

    private var pharmacyHero: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("💊").font(.largeTitle)
            Text("Bugün nöbetçi").font(.caption.weight(.bold)).foregroundStyle(.white.opacity(0.82))
            Text(dutyLabel).font(.title2.weight(.black)).foregroundStyle(.white)
            if let sub = payload["page_sub"] as? String, !sub.isEmpty {
                Text(sub).font(.caption).foregroundStyle(.white.opacity(0.88))
            }
            WrapStatsChips(items: ["\(total) nöbetçi", hasGeo ? "liste" : "\(groupCount) ilçe", "18:30 başlangıç"])
            if let note = payload["hero_note"] as? String, !note.isEmpty {
                Text(note).font(.caption2).foregroundStyle(.white.opacity(0.65))
            }
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            LinearGradient(
                colors: [Color(red: 0.106, green: 0.369, blue: 0.125), Color(red: 0.263, green: 0.627, blue: 0.278)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
    }

    private var districtPicker: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Bölge").font(.caption2.weight(.heavy)).foregroundStyle(AppColors.muted)
            Picker("Bölge", selection: $ilce) {
                Text("Tümü").tag("")
                ForEach(districts, id: \.self) { d in Text(d).tag(d) }
            }
            .pickerStyle(.menu)
            .onChange(of: ilce) { _ in Task { await load() } }
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: AppRadii.sm).fill(AppColors.card))
    }

    @ViewBuilder
    private var pharmacyGroups: some View {
        if loading && groups.isEmpty {
            ProgressView().padding(.vertical, 32)
        } else if groups.isEmpty {
            Text("Liste henüz yok veya bu ilçede nöbetçi bulunamadı.")
                .foregroundStyle(AppColors.muted)
                .multilineTextAlignment(.center)
                .padding(.vertical, 32)
        } else {
            ForEach(Array(groups.enumerated()), id: \.offset) { _, group in
                let places = MobileJSON.maps(group["places"])
                GroupHeaderRow(label: group["label"] as? String ?? "", count: places.count, unit: "eczane")
                ForEach(Array(places.enumerated()), id: \.offset) { _, row in
                    PharmacyRow(row: row)
                }
            }
        }
    }

    @MainActor
    private func load() async {
        loading = true
        defer { loading = false }
        if let json = try? await auth.apiClient().nobetciEczaneler(
            ilce: ilce.isEmpty ? nil : ilce,
            lat: lat,
            lng: lng
        ) {
            payload = json
        }
    }

    @MainActor
    private func sortByLocation() async {
        locating = true
        defer { locating = false }
        if let coord = await LocationService.requestLocation() {
            lat = coord.latitude
            lng = coord.longitude
        }
        await load()
    }

    private func clearGeo() {
        lat = nil
        lng = nil
        Task { await load() }
    }
}

private struct PharmacyRow: View {
    let row: [String: Any]

    var body: some View {
        let slug = (row["slug"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let name = row["name"] as? String ?? row["title"] as? String ?? "Eczane"
        let address = row["address"] as? String ?? row["adres"] as? String ?? ""
        let district = row["district"] as? String ?? row["ilce"] as? String ?? ""
        let phone = row["phone"] as? String ?? row["tel"] as? String ?? ""
        let maps = row["maps"] as? String ?? ""
        let hours = row["hours_short"] as? String ?? ""
        let distance = row["distance_label"] as? String ?? ""
        let walkMin = JSONValue.int(row["walk_min"])

        let content = HStack(alignment: .top, spacing: 12) {
            Text("💊")
                .font(.title2)
                .frame(width: 56, height: 56)
                .background(Color(red: 0.263, green: 0.627, blue: 0.278).opacity(0.15))
                .clipShape(RoundedRectangle(cornerRadius: 14))
            VStack(alignment: .leading, spacing: 6) {
                Text(name).font(.subheadline.weight(.heavy))
                if !distance.isEmpty {
                    Text(walkMin > 0 ? "\(distance) · ~\(walkMin) dk yürüme" : distance)
                        .font(.caption.weight(.bold))
                        .foregroundStyle(AppColors.muted)
                }
                Text(address.isEmpty ? district : address)
                    .font(.caption)
                    .foregroundStyle(AppColors.muted)
                HStack(spacing: 6) {
                    if !phone.isEmpty { PhoneLink(phone: phone) }
                    if !maps.isEmpty { MapsLink(urlString: maps, label: "Yol tarifi") }
                }
            }
            if !hours.isEmpty {
                Text(hours).font(.caption2.weight(.bold)).foregroundStyle(AppColors.muted)
            }
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: AppRadii.md).fill(AppColors.card))

        if slug.isEmpty {
            content
        } else {
            NavigationLink(value: "pharmacy:\(slug)") { content }.buttonStyle(.plain)
        }
    }
}

// MARK: - News

struct NewsView: View {
    @EnvironmentObject private var auth: AuthStore
    @State private var queryText = ""
    @State private var topic = ""
    @State private var page = 1
    @State private var articles: [[String: Any]] = []
    @State private var videos: [[String: Any]] = []
    @State private var topics: [String: String] = [:]
    @State private var meta: [String: Any] = [:]
    @State private var bursaspor: [String: Any]?
    @State private var featuredVideo: [String: Any]?
    @State private var loading = true
    @State private var loadingMore = false
    @State private var hasMore = false

    var body: some View {
        AppPage(title: "Bursa haberleri") {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    searchBar
                    Text("Bursa gündemi — trafik, belediye, sanayi, kültür ve spor.")
                        .font(.caption)
                        .foregroundStyle(AppColors.muted)
                    if let updated = meta["generated_at"] as? String, !updated.isEmpty {
                        Text("Güncellendi \(updated)").font(.caption2).foregroundStyle(AppColors.muted)
                    }
                    topicBar
                    if let bursaspor, bursaspor["next_match"] != nil {
                        bursasporStrip(bursaspor)
                    }
                    if let hero = articles.first {
                        heroArticle(hero)
                    }
                    if articles.count > 1 {
                        SectionHeader(title: "Son dakika")
                        ForEach(Array(articles.dropFirst().prefix(6).enumerated()), id: \.offset) { _, row in
                            newsSideRow(row)
                        }
                    }
                    if !videos.isEmpty {
                        newsVideosSection
                    }
                    if articles.count > 7 {
                        SectionHeader(title: "Daha fazla haber\(meta["total"] != nil ? " · \(JSONValue.int(meta["total"]))" : "")")
                        ForEach(Array(articles.dropFirst(7).enumerated()), id: \.offset) { _, row in
                            newsCard(row)
                        }
                    }
                    if articles.isEmpty && !loading {
                        Text("Bu filtrede haber yok.").foregroundStyle(AppColors.muted).frame(maxWidth: .infinity).padding(.vertical, 32)
                    }
                    if hasMore && !articles.isEmpty {
                        Button(loadingMore ? "Yükleniyor…" : "Daha fazla yükle") { Task { await loadMore() } }
                            .frame(maxWidth: .infinity)
                    }
                    if let disclaimer = meta["disclaimer"] as? String, !disclaimer.isEmpty {
                        Text(disclaimer).font(.caption2).foregroundStyle(AppColors.muted)
                    }
                }
                .padding(16)
            }
            .refreshable { await load(reset: true) }
            .task { await load(reset: true) }
        }
    }

    private var topicItems: [(String, String)] {
        [("", "Tümü")] + topics.sorted(by: { $0.key < $1.key }).map { ($0.key, $0.value) }
    }

    private var searchBar: some View {
        HStack {
            TextField("Bursa haber ara…", text: $queryText)
                .textFieldStyle(.roundedBorder)
                .submitLabel(.search)
                .onSubmit { Task { await load(reset: true) } }
            Button("Ara") { Task { await load(reset: true) } }
                .buttonStyle(.borderedProminent)
                .tint(AppColors.nav)
        }
    }

    private var topicBar: some View {
        FilterChips(items: topicItems, selected: topic) { topic = $0; Task { await load(reset: true) } }
    }

    @ViewBuilder
    private func bursasporStrip(_ data: [String: Any]) -> some View {
        let match = data["next_match"] as? [String: Any] ?? [:]
        NavigationLink {
            BursasporView()
        } label: {
            VStack(alignment: .leading, spacing: 6) {
                Text("Bursaspor").font(.caption.weight(.heavy)).foregroundStyle(AppColors.lime)
                Text("\(match["home_team"] as? String ?? "") vs \(match["away_team"] as? String ?? "")")
                    .font(.subheadline.weight(.black))
                    .foregroundStyle(.white)
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: AppRadii.md).fill(AppColors.nav))
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private func heroArticle(_ row: [String: Any]) -> some View {
        let slug = row["slug"] as? String ?? row["id"] as? String ?? ""
        let card = VStack(alignment: .leading, spacing: 8) {
            if let img = row["img_url"] as? String, !img.isEmpty {
                RemoteImage(url: img).frame(height: 200).clipShape(RoundedRectangle(cornerRadius: AppRadii.md))
            }
            Text(row["title"] as? String ?? "Haber").font(.title3.weight(.black))
            if let sum = row["summary"] as? String ?? row["blurb"] as? String {
                Text(sum).font(.caption).foregroundStyle(AppColors.muted).lineLimit(4)
            }
        }
        if slug.isEmpty {
            card
        } else {
            NavigationLink(value: "news:\(slug)") { card }.buttonStyle(.plain)
        }
    }

    @ViewBuilder
    private func newsSideRow(_ row: [String: Any]) -> some View {
        let slug = row["slug"] as? String ?? row["id"] as? String ?? ""
        let card = HStack(spacing: 10) {
            if let img = row["img_url"] as? String, !img.isEmpty {
                RemoteImage(url: img).frame(width: 72, height: 72).clipShape(RoundedRectangle(cornerRadius: AppRadii.sm))
            }
            VStack(alignment: .leading, spacing: 4) {
                Text(row["title"] as? String ?? "").font(.subheadline.weight(.heavy)).lineLimit(2)
                if let when = row["date_label"] as? String ?? row["when"] as? String {
                    Text(when).font(.caption2).foregroundStyle(AppColors.muted)
                }
            }
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: AppRadii.sm).fill(AppColors.card))
        if slug.isEmpty {
            card
        } else {
            NavigationLink(value: "news:\(slug)") { card }.buttonStyle(.plain)
        }
    }

    @ViewBuilder
    private func newsCard(_ row: [String: Any]) -> some View {
        let slug = row["slug"] as? String ?? row["id"] as? String ?? ""
        let card = VStack(alignment: .leading, spacing: 6) {
            Text(row["title"] as? String ?? "").font(.headline)
            if let sum = row["summary"] as? String ?? row["blurb"] as? String {
                Text(sum).font(.caption).foregroundStyle(AppColors.muted).lineLimit(3)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: AppRadii.md).fill(AppColors.card))
        if slug.isEmpty {
            card
        } else {
            NavigationLink(value: "news:\(slug)") { card }.buttonStyle(.plain)
        }
    }

    private var newsVideosSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionHeader(title: "Video gündem")
            if let featured = featuredVideo ?? videos.first {
                newsVideoCard(featured, large: true)
            }
            ForEach(Array(videos.dropFirst().prefix(4).enumerated()), id: \.offset) { _, video in
                newsVideoCard(video, large: false)
            }
        }
    }

    @ViewBuilder
    private func newsVideoCard(_ video: [String: Any], large: Bool) -> some View {
        let watch = video["watch_url"] as? String ?? video["url"] as? String ?? ""
        let content = VStack(alignment: .leading, spacing: 6) {
            if let thumb = video["thumb"] as? String ?? video["img_url"] as? String, !thumb.isEmpty {
                ZStack {
                    RemoteImage(url: thumb, placeholder: "play.rectangle.fill")
                        .frame(height: large ? 180 : 120)
                        .frame(maxWidth: .infinity)
                        .clipped()
                    Image(systemName: "play.circle.fill").font(.largeTitle).foregroundStyle(.white)
                }
            }
            Text(video["title"] as? String ?? "Video").font(large ? .subheadline.weight(.heavy) : .caption.weight(.heavy)).lineLimit(2)
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: AppRadii.md).fill(AppColors.bgSoft))
        if let url = URL(string: watch), !watch.isEmpty {
            Link(destination: url) { content }.buttonStyle(.plain)
        } else {
            content
        }
    }

    @MainActor
    private func load(reset: Bool) async {
        if reset {
            page = 1
            loading = true
        } else {
            loadingMore = true
        }
        defer { loading = false; loadingMore = false }
        do {
            let q = queryText.trimmingCharacters(in: .whitespacesAndNewlines)
            let json = try await auth.apiClient().bursaNews(
                page: page,
                topic: topic.isEmpty ? nil : topic,
                q: q.isEmpty ? nil : q
            )
            let batch = MobileJSON.maps(json["articles"])
            let nextMeta = json["meta"] as? [String: Any] ?? [:]
            let pages = JSONValue.int(nextMeta["pages"], default: 1)
            if reset {
                articles = batch
                if let topicMap = json["topics"] as? [String: String] {
                    topics = topicMap
                } else if let topicAny = json["topics"] as? [String: Any] {
                    topics = topicAny.mapValues { "\($0)" }
                }
                videos = MobileJSON.maps(json["videos"])
                featuredVideo = json["featured_video"] as? [String: Any]
                bursaspor = json["bursaspor"] as? [String: Any]
                meta = nextMeta
            } else {
                articles.append(contentsOf: batch)
            }
            hasMore = page < pages
        } catch {
            if reset { articles = [] }
        }
    }

    @MainActor
    private func loadMore() async {
        guard !loadingMore, hasMore else { return }
        page += 1
        await load(reset: false)
    }
}

// MARK: - Bursaspor

struct BursasporView: View {
    @EnvironmentObject private var auth: AuthStore
    @State private var payload: [String: Any] = [:]
    @State private var loading = true
    @State private var allFixturesOpen = false

    var body: some View {
        AppPage(title: "Bursaspor") {
            ScrollView {
                VStack(spacing: 14) {
                    if loading && payload.isEmpty { ProgressView().padding() }
                    heroSection
                    if let next = payload["next_match"] as? [String: Any] {
                        nextMatchCard(next)
                    }
                    if let desk = payload["desk"] as? [String: Any], !desk.isEmpty {
                        deskSection(desk)
                    }
                    let videos = MobileJSON.maps(payload["videos"])
                    if !videos.isEmpty { videosSection(videos) }
                    let news = MobileJSON.maps(payload["news"])
                    if !news.isEmpty { bursasporNewsSection(news) }
                    let standings = MobileJSON.maps(payload["standings"])
                    if !standings.isEmpty {
                        standingsSection(standings, league: payload["league"] as? String ?? "Trendyol 1. Lig")
                    }
                    fixtureSection
                    officialLinks
                }
                .padding(16)
            }
            .refreshable { await load() }
            .task { await load() }
        }
    }

    private var heroSection: some View {
        let heroBg = payload["hero_bg"] as? String ?? ""
        let bsRow = payload["bs_row"] as? [String: Any]
        let form = (payload["desk"] as? [String: Any])?["form"] as? [String] ?? []
        let league = payload["league"] as? String ?? "Trendyol 1. Lig"
        return ZStack(alignment: .bottomLeading) {
            if !heroBg.isEmpty {
                RemoteImage(url: heroBg).frame(height: 190).frame(maxWidth: .infinity).clipped()
            } else {
                AppColors.nav.frame(height: 190)
            }
            LinearGradient(colors: [AppColors.nav.opacity(0.35), AppColors.nav.opacity(0.92)], startPoint: .top, endPoint: .bottom)
                .frame(height: 190)
            VStack(alignment: .leading, spacing: 8) {
                Text("Yeşil · Beyaz · Timsah").font(.caption.weight(.heavy)).foregroundStyle(AppColors.lime)
                Text("Tutku burada.\nSahada yeşil.").font(.title2.weight(.black)).foregroundStyle(.white)
                HStack(spacing: 8) {
                    if let bsRow {
                        heroPill("\(JSONValue.int(bsRow["pos"])). sıra · \(JSONValue.int(bsRow["pts"])) puan")
                    }
                    if !form.isEmpty { formPill(form) }
                    heroPill(league)
                }
            }
            .padding(18)
            Text("🐊").font(.largeTitle).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing).padding(16)
        }
        .clipShape(RoundedRectangle(cornerRadius: AppRadii.lg))
    }

    @ViewBuilder
    private var fixtureSection: some View {
        let upcoming = MobileJSON.maps(payload["upcoming"])
        let recent = MobileJSON.maps(payload["recent"])
        let matches = MobileJSON.maps(payload["matches"])
        if upcoming.isEmpty && recent.isEmpty && matches.isEmpty { EmptyView() }
        else {
            panel(title: "Fikstür & sonuçlar") {
                if !upcoming.isEmpty {
                    Text("Sıradaki maçlar").font(.subheadline.weight(.heavy))
                    ForEach(Array(upcoming.enumerated()), id: \.offset) { _, m in fixCard(m, upcoming: true) }
                }
                if !recent.isEmpty {
                    Text("Son sonuçlar").font(.subheadline.weight(.heavy)).padding(.top, 8)
                    ForEach(Array(recent.enumerated()), id: \.offset) { _, m in fixCard(m, upcoming: false) }
                }
                if !matches.isEmpty {
                    Button(allFixturesOpen ? "Tüm sezonu gizle" : "Tüm sezon fikstürü (\(matches.count))") {
                        allFixturesOpen.toggle()
                    }
                    if allFixturesOpen {
                        ForEach(Array(matches.enumerated()), id: \.offset) { _, m in fixRow(m) }
                    }
                }
            }
        }
    }

    @MainActor
    private func load() async {
        loading = true
        defer { loading = false }
        if let json = try? await auth.apiClient().bursasporFeed() {
            payload = json
        }
    }
}

// MARK: - Teleferik

struct TeleferikView: View {
    @EnvironmentObject private var auth: AuthStore
    @State private var data: [String: Any] = [:]
    @State private var loading = true

    var body: some View {
        AppPage(title: "Uludağ teleferik") {
            ScrollView {
                VStack(spacing: 14) {
                    if loading && data.isEmpty { ProgressView().padding() }
                    teleferikHero
                    hoursStrip
                    let prices = MobileJSON.maps(data["prices"])
                    if !prices.isEmpty {
                        panel(title: "Bilet fiyatları", subtitle: "Gidiş-dönüş · gişe ve online tarife") {
                            ForEach(Array(prices.enumerated()), id: \.offset) { _, p in priceCard(p) }
                        }
                    }
                    let discounts = MobileJSON.maps(data["discounts"])
                    if !discounts.isEmpty {
                        panel(title: "İndirimli günler", subtitle: "Kimlik veya belge gişede sorulur") {
                            ForEach(Array(discounts.enumerated()), id: \.offset) { _, d in discountCard(d) }
                        }
                    }
                    let hours = data["hours"] as? [String: Any] ?? [:]
                    if !hours.isEmpty {
                        panel(title: "Açılış · kapanış", subtitle: "Hava muhalefetinde seferler durabilir") {
                            hoursPanel(hours)
                        }
                    }
                    let buses = MobileJSON.maps(data["buses"])
                    if !buses.isEmpty {
                        panel(title: "Teleferiğe nasıl gidilir?", subtitle: "Teferrüç alt istasyonu") {
                            ForEach(Array(buses.enumerated()), id: \.offset) { _, b in busCard(b) }
                        }
                    }
                    let stations = MobileJSON.maps(data["stations"])
                    if !stations.isEmpty {
                        panel(title: "İstasyon hattı", subtitle: "Teferrüç'ten oteller bölgesine") {
                            ForEach(Array(stations.enumerated()), id: \.offset) { idx, s in
                                stationRow(s, isLast: idx == stations.count - 1)
                            }
                        }
                    }
                    let tips = MobileJSON.strings(data["tips"])
                    if !tips.isEmpty {
                        panel(title: "Pratik ipuçları") {
                            ForEach(tips, id: \.self) { tip in
                                Text("• \(MobileJSON.stripHtml(tip))").font(.caption).foregroundStyle(AppColors.muted)
                            }
                        }
                    }
                    panel(title: "Uludağ gününü planla") {
                        HStack {
                            NavigationLink { RoutePlannerView() } label: { Text("Rota planla").font(.caption.weight(.heavy)) }
                            NavigationLink(value: "teleferik") { Text("Gezilecek kaydı").font(.caption.weight(.heavy)) }
                        }
                    }
                    let phones = MobileJSON.strings(data["phones"])
                    if !phones.isEmpty {
                        HStack(spacing: 8) {
                            ForEach(phones, id: \.self) { p in PhoneLink(phone: p) }
                        }
                    }
                    let sources = MobileJSON.maps(data["sources"])
                    if !sources.isEmpty {
                        HStack(spacing: 8) {
                            ForEach(Array(sources.enumerated()), id: \.offset) { _, s in
                                if let url = s["url"] as? String, let label = s["label"] as? String, let link = URL(string: url) {
                                    Link(label, destination: link).font(.caption)
                                }
                            }
                        }
                    }
                    if let disclaimer = data["disclaimer"] as? String, !disclaimer.isEmpty {
                        Text(disclaimer).font(.caption2).foregroundStyle(AppColors.muted)
                    }
                }
                .padding(16)
            }
            .refreshable { await load() }
            .task { await load() }
        }
    }

    private var teleferikHero: some View {
        let heroUrl = "/static/visit/teleferik.jpg"
        let updated = data["generated_label"] as? String ?? ""
        let prices = MobileJSON.maps(data["prices"])
        let tam = prices.first?["amount_tl"]
        let ogr = prices.count > 1 ? prices[1]["amount_tl"] : nil
        return ZStack(alignment: .bottomLeading) {
            RemoteImage(url: heroUrl).frame(height: 220).frame(maxWidth: .infinity).clipped()
            LinearGradient(colors: [.clear, AppColors.nav.opacity(0.85)], startPoint: .top, endPoint: .bottom)
            VStack(alignment: .leading, spacing: 6) {
                Text("Uludağ teleferik").font(.title2.weight(.black)).foregroundStyle(.white)
                if let tam { Text("Tam: \(JSONValue.string(tam)) TL").font(.caption.weight(.heavy)).foregroundStyle(.white) }
                if let ogr { Text("Öğrenci: \(JSONValue.string(ogr)) TL").font(.caption).foregroundStyle(.white.opacity(0.9)) }
                if !updated.isEmpty { Text(updated).font(.caption2).foregroundStyle(.white.opacity(0.7)) }
            }
            .padding(16)
        }
        .clipShape(RoundedRectangle(cornerRadius: AppRadii.lg))
    }

    private var hoursStrip: some View {
        let hours = data["hours"] as? [String: Any] ?? [:]
        let summer = hours["summer"] as? String ?? hours["yaz"] as? String ?? ""
        let winter = hours["winter"] as? String ?? hours["kis"] as? String ?? ""
        return HStack(spacing: 10) {
            if !summer.isEmpty { MetaChip(text: "Yaz: \(summer)") }
            if !winter.isEmpty { MetaChip(text: "Kış: \(winter)") }
        }
    }

    @MainActor
    private func load() async {
        loading = true
        defer { loading = false }
        if let json = try? await auth.apiClient().teleferikInfo() {
            data = json
        }
    }
}

// MARK: - Utilities

struct UtilitiesView: View {
    @EnvironmentObject private var auth: AuthStore
    @State private var utilities: [String: Any] = [:]
    @State private var loading = true

    private let sections: [(key: String, icon: String, title: String)] = [
        ("water", "💧", "BUSKİ su fiyatları"),
        ("electricity", "⚡", "Elektrik fiyatları"),
        ("gas", "🔥", "Doğalgaz fiyatları"),
    ]

    var body: some View {
        AppPage(title: "Faturalar & tarifeler") {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Text("BUSKİ · UEDAŞ · Bursagaz güncel tarife ve iletişim özeti.")
                        .font(.caption)
                        .foregroundStyle(AppColors.muted)
                    if let updated = utilities["generated_label"] as? String, !updated.isEmpty {
                        Text("Son güncelleme: \(updated)").font(.caption2).foregroundStyle(AppColors.muted)
                    }
                    ForEach(sections, id: \.key) { kind in
                        if let block = utilities[kind.key] as? [String: Any] {
                            UtilityBlock(kind: kind, data: block)
                        }
                    }
                    NavigationLink { TeleferikView() } label: {
                        Text("Uludağ teleferik tarifeleri →")
                            .font(.subheadline.weight(.heavy))
                            .padding(14)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(RoundedRectangle(cornerRadius: AppRadii.md).fill(AppColors.nav))
                            .foregroundStyle(.white)
                    }
                    .buttonStyle(.plain)
                    if let disclaimer = utilities["disclaimer"] as? String, !disclaimer.isEmpty {
                        Text(disclaimer).font(.caption2).foregroundStyle(AppColors.muted)
                    }
                }
                .padding(16)
            }
            .refreshable { await load() }
            .task { await load() }
        }
    }

    @MainActor
    private func load() async {
        loading = true
        defer { loading = false }
        if let json = try? await auth.apiClient().utilitiesInfo(),
           let raw = json["utilities"] as? [String: Any] {
            utilities = raw
        }
    }
}

private struct UtilityBlock: View {
    let kind: (key: String, icon: String, title: String)
    let data: [String: Any]
    @State private var branchesOpen = false

    var body: some View {
        let company = data["company"] as? String ?? kind.title
        let phones = MobileJSON.strings(data["phones"])
        let emergency = data["emergency"] as? String ?? ""
        let tariffNote = data["tariff_note"] as? String ?? ""
        let effective = data["effective_label"] as? String ?? ""
        let tariffs = MobileJSON.maps(data["tariffs"])
        let branches = MobileJSON.maps(data["branches"])
        let shown = branchesOpen ? branches : Array(branches.prefix(4))

        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 10) {
                Text(kind.icon).font(.largeTitle)
                VStack(alignment: .leading, spacing: 4) {
                    Text(kind.title).font(.headline.weight(.black))
                    if company != kind.title {
                        Text(company).font(.caption).foregroundStyle(AppColors.muted)
                    }
                }
            }
            if !phones.isEmpty {
                HStack(spacing: 8) {
                    ForEach(phones, id: \.self) { PhoneLink(phone: $0) }
                }
            }
            if !emergency.isEmpty {
                Text(emergency).font(.caption.weight(.bold)).foregroundStyle(AppColors.coral)
            }
            if !effective.isEmpty { Text(effective).font(.caption.weight(.heavy)) }
            if !tariffNote.isEmpty { Text(tariffNote).font(.caption).foregroundStyle(AppColors.muted) }
            if !tariffs.isEmpty {
                Text("Tarife").font(.subheadline.weight(.black))
                ForEach(Array(tariffs.enumerated()), id: \.offset) { _, t in
                    HStack {
                        Text(t["label"] as? String ?? "").font(.caption.weight(.semibold))
                        Spacer()
                        Text(t["amount"] as? String ?? t["value"] as? String ?? "").font(.caption.weight(.heavy))
                    }
                }
            }
            if !branches.isEmpty {
                Text("Şubeler").font(.subheadline.weight(.black))
                ForEach(Array(shown.enumerated()), id: \.offset) { _, b in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(b["name"] as? String ?? b["ilce"] as? String ?? "Şube").font(.caption.weight(.heavy))
                        if let addr = b["address"] as? String { Text(addr).font(.caption2).foregroundStyle(AppColors.muted) }
                    }
                }
                if branches.count > 4 {
                    Button(branchesOpen ? "Daha az göster" : "Tüm şubeler (\(branches.count))") {
                        branchesOpen.toggle()
                    }
                    .font(.caption.weight(.heavy))
                }
            }
        }
        .padding(16)
        .background(RoundedRectangle(cornerRadius: AppRadii.lg).fill(AppColors.card))
    }
}

// MARK: - Weekend

struct WeekendView: View {
    @EnvironmentObject private var auth: AuthStore
    @State private var sections: [(title: String, places: [PlaceItem])] = []
    @State private var label = "Hafta sonu önerileri"
    @State private var loading = true

    var body: some View {
        AppPage(title: "Hafta sonu planı") {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    Text(label).font(.subheadline.weight(.heavy)).foregroundStyle(AppColors.muted)
                    if loading && sections.isEmpty {
                        ProgressView().frame(maxWidth: .infinity).padding(.vertical, 32)
                    } else if sections.isEmpty {
                        Text("Bu hafta sonu için öneri yok.").foregroundStyle(AppColors.muted).padding(.vertical, 32)
                    } else {
                        ForEach(Array(sections.enumerated()), id: \.offset) { _, section in
                            Text(section.title).font(.headline.weight(.black)).padding(.top, 8)
                            ForEach(section.places) { place in
                                NavigationLink(value: place.detailSlug) {
                                    EventPlaceCard(place: place)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                }
                .padding(16)
            }
            .refreshable { await load() }
            .task { await load() }
        }
    }

    @MainActor
    private func load() async {
        loading = true
        defer { loading = false }
        guard let data = try? await auth.apiClient().weekend() else { return }
        var built: [(String, [PlaceItem])] = []
        for dayKey in ["saturday", "sunday"] {
            guard let day = data[dayKey] as? [[String: Any]] else { continue }
            var places: [PlaceItem] = []
            for block in day {
                places.append(contentsOf: PlaceItem.list(from: block))
            }
            guard !places.isEmpty else { continue }
            let labelKey = "\(dayKey)_label"
            let title = (data[labelKey] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
            let fallback = dayKey == "saturday" ? "Cumartesi" : "Pazar"
            built.append(((title?.isEmpty == false ? title! : fallback), places))
        }
        sections = built
        let sat = data["saturday_label"] as? String ?? ""
        let sun = data["sunday_label"] as? String ?? ""
        let combined = [sat, sun].filter { !$0.isEmpty }.joined(separator: " · ")
        if !combined.isEmpty { label = combined }
    }
}

// MARK: - Leaders

struct LeadersView: View {
    @EnvironmentObject private var auth: AuthStore
    @State private var leaders: [LeaderRow] = []

    var body: some View {
        AppPage(title: "Haftanın liderleri") {
            List(leaders) { row in
                HStack(spacing: 12) {
                    Text("#\(row.rank)").font(.headline).foregroundStyle(AppColors.accentDeep).frame(width: 32)
                    if !row.avatarUrl.isEmpty {
                        RemoteImage(url: row.avatarUrl, placeholder: "person.circle.fill")
                            .frame(width: 36, height: 36)
                            .clipShape(Circle())
                    } else {
                        Image(systemName: "person.circle.fill")
                            .font(.title2)
                            .foregroundStyle(AppColors.muted)
                    }
                    Text(row.name)
                    Spacer()
                    Text("\(row.points) puan").foregroundStyle(AppColors.muted)
                }
            }
            .refreshable { await load() }
            .task { await load() }
        }
    }

    @MainActor
    private func load() async {
        if let rows = try? await auth.apiClient().weeklyLeaders() {
            leaders = rows
        }
    }
}

// MARK: - Bursaspor helpers

private func heroPill(_ text: String) -> some View {
    Text(text)
        .font(.caption.weight(.bold))
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(Color.white.opacity(0.14))
        .foregroundStyle(.white)
        .clipShape(Capsule())
}

private func formPill(_ form: [String]) -> some View {
    HStack(spacing: 4) {
        ForEach(form, id: \.self) { ch in
            Text(ch)
                .font(.caption2.weight(.black))
                .foregroundStyle(.white)
                .frame(width: 22, height: 22)
                .background(formColor(ch))
                .clipShape(Circle())
        }
    }
    .padding(.horizontal, 8)
    .padding(.vertical, 5)
    .background(Color.white.opacity(0.14))
    .clipShape(Capsule())
}

private func formColor(_ ch: String) -> Color {
    switch ch.uppercased() {
    case "G": return AppColors.accentDeep
    case "M": return AppColors.coral
    default: return AppColors.amber
    }
}

private func nextMatchCard(_ match: [String: Any]) -> some View {
    let home = match["home_team"] as? String ?? ""
    let away = match["away_team"] as? String ?? ""
    let isHome = match["is_home"] as? Bool == true
    let week = JSONValue.int(match["week"])
    let date = match["kickoff_date"] as? String ?? match["kickoff_at"] as? String ?? ""
    let time = match["kickoff_time"] as? String ?? ""
    let venue = match["venue"] as? String ?? ""
    let ticket = match["ticket_url"] as? String ?? "https://www.bursaspor.org.tr/"
    return panel(title: "\(isHome ? "İç saha" : "Deplasman")\(week > 0 ? " · \(week). hafta" : "")") {
        HStack {
            teamCol(home, highlight: home.contains("Bursaspor"))
            Text("VS").font(.caption.weight(.black)).foregroundStyle(AppColors.muted)
            teamCol(away, highlight: away.contains("Bursaspor"))
        }
        if !date.isEmpty || !time.isEmpty || !venue.isEmpty {
            Text([date.isEmpty ? nil : "📅 \(date)", time.isEmpty ? nil : "🕐 \(time)", venue.isEmpty ? nil : "📍 \(venue)"].compactMap { $0 }.joined(separator: " · "))
                .font(.caption)
                .foregroundStyle(AppColors.muted)
        }
        HStack {
            if let url = URL(string: "https://www.bursaspor.org.tr/") {
                Link("Resmi site", destination: url)
            }
            if let url = URL(string: ticket) {
                Link("Bilet / Passolig", destination: url)
                    .font(.caption.weight(.heavy))
            }
        }
    }
}

private func teamCol(_ name: String, highlight: Bool) -> some View {
    VStack {
        Circle()
            .fill(highlight ? AppColors.accentDeep : AppColors.bgSoft)
            .frame(width: 44, height: 44)
            .overlay(Text(name.prefix(1)).font(.headline.weight(.black)).foregroundStyle(highlight ? .white : AppColors.ink))
        Text(name).font(.caption2.weight(.heavy)).multilineTextAlignment(.center).lineLimit(2)
            .foregroundStyle(highlight ? AppColors.accentDeep : AppColors.ink)
    }
    .frame(maxWidth: .infinity)
}

private func deskSection(_ desk: [String: Any]) -> some View {
    let form = desk["form"] as? [String] ?? []
    let generated = desk["generated_at"] as? String ?? ""
    return panel(title: "Maç masası", trailing: form.isEmpty ? nil : AnyView(formPill(form))) {
        if let note = desk["standings_note"] as? String, !note.isEmpty {
            Text(note).font(.caption.weight(.heavy)).foregroundStyle(AppColors.lime)
        }
        if let analysis = desk["analysis"] as? String, !analysis.isEmpty {
            Text(analysis).font(.caption)
        }
        if let preview = desk["preview"] as? String, !preview.isEmpty {
            noteCard(title: "Önizleme", body: preview)
        }
        if let review = desk["review"] as? String, !review.isEmpty {
            noteCard(title: "Maç arkası", body: review)
        }
        if !generated.isEmpty {
            Text("Son derleme: \(generated)").font(.caption2).foregroundStyle(AppColors.muted)
        }
    }
}

private func noteCard(title: String, body: String) -> some View {
    VStack(alignment: .leading, spacing: 4) {
        Text(title).font(.subheadline.weight(.black))
        Text(body).font(.caption).foregroundStyle(AppColors.muted)
    }
    .padding(12)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(RoundedRectangle(cornerRadius: AppRadii.sm).fill(AppColors.bgSoft))
}

@MainActor
private func videosSection(_ videos: [[String: Any]]) -> some View {
    panel(title: "Yeşil-beyaz video") {
        BursasporVideoCard(video: videos[0], large: true)
        ForEach(Array(videos.dropFirst().prefix(4).enumerated()), id: \.offset) { _, v in
            BursasporVideoCard(video: v, large: false)
        }
    }
}

private struct BursasporVideoCard: View {
    let video: [String: Any]
    let large: Bool

    var body: some View {
        let watch = video["watch_url"] as? String ?? ""
        let content = VStack(alignment: .leading, spacing: 6) {
            if let thumb = video["thumb"] as? String, !thumb.isEmpty {
                RemoteImage(url: thumb).frame(height: large ? 160 : 100).frame(maxWidth: .infinity).clipped()
            }
            Text(video["title"] as? String ?? "Video").font(.caption.weight(.heavy)).lineLimit(2)
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: AppRadii.md).fill(AppColors.bgSoft))

        if let url = URL(string: watch), !watch.isEmpty {
            Link(destination: url) { content }.buttonStyle(.plain)
        } else {
            content
        }
    }
}

@MainActor
private func bursasporNewsSection(_ news: [[String: Any]]) -> some View {
    panel(title: "Öne çıkan gündem") {
        ForEach(Array(news.enumerated()), id: \.offset) { _, item in
            if let url = item["url"] as? String, let link = URL(string: url) {
                Link(destination: link) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(item["title"] as? String ?? "").font(.subheadline.weight(.heavy))
                        if let blurb = item["blurb"] as? String { Text(blurb).font(.caption).foregroundStyle(AppColors.muted).lineLimit(2) }
                    }
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(RoundedRectangle(cornerRadius: AppRadii.sm).fill(AppColors.bgSoft))
                }
            }
        }
    }
}

private func standingsSection(_ standings: [[String: Any]], league: String) -> some View {
    panel(title: "Lig puan durumu", subtitle: league) {
        ScrollView(.horizontal, showsIndicators: false) {
            VStack(alignment: .leading, spacing: 0) {
                HStack {
                    Text("#").frame(width: 24)
                    Text("Takım").frame(width: 120, alignment: .leading)
                    Text("O").frame(width: 24)
                    Text("G").frame(width: 24)
                    Text("B").frame(width: 24)
                    Text("M").frame(width: 24)
                    Text("P").frame(width: 24)
                }
                .font(.caption2.weight(.heavy))
                ForEach(Array(standings.enumerated()), id: \.offset) { _, r in
                    let team = r["team"] as? String ?? ""
                    let isBs = team.contains("Bursaspor")
                    HStack {
                        Text(JSONValue.string(r["pos"])).frame(width: 24)
                        Text(team).frame(width: 120, alignment: .leading).lineLimit(1)
                        Text(JSONValue.string(r["p"])).frame(width: 24)
                        Text(JSONValue.string(r["w"])).frame(width: 24)
                        Text(JSONValue.string(r["d"])).frame(width: 24)
                        Text(JSONValue.string(r["l"])).frame(width: 24)
                        Text(JSONValue.string(r["pts"])).frame(width: 24)
                    }
                    .font(.caption2.weight(isBs ? .black : .regular))
                    .foregroundStyle(isBs ? AppColors.accentDeep : AppColors.ink)
                    .padding(.vertical, 4)
                    .background(isBs ? AppColors.accentDeep.opacity(0.08) : Color.clear)
                }
            }
        }
    }
}

@MainActor
private func fixCard(_ match: [String: Any], upcoming: Bool) -> some View {
    let home = match["home_team"] as? String ?? ""
    let away = match["away_team"] as? String ?? ""
    let week = JSONValue.int(match["week"])
    let isHome = match["is_home"] as? Bool == true
    let when = match["kickoff_at"] as? String ?? ""
    let venue = match["venue"] as? String ?? ""
    let ticket = match["ticket_url"] as? String ?? ""
    return VStack(alignment: .leading, spacing: 6) {
        HStack {
            Text("\(week > 0 ? "\(week). hafta" : "Maç") · \(isHome ? "İç saha" : "Deplasman")")
                .font(.caption2.weight(.bold))
                .foregroundStyle(AppColors.muted)
            Spacer()
            if !upcoming, match["home_score"] != nil {
                Text("\(JSONValue.string(match["home_score"]))–\(JSONValue.string(match["away_score"]))").font(.caption.weight(.black))
            }
        }
        Text("\(home) vs \(away)").font(.subheadline.weight(.heavy))
        if !when.isEmpty || !venue.isEmpty {
            Text([when, venue].filter { !$0.isEmpty }.joined(separator: " · ")).font(.caption).foregroundStyle(AppColors.muted)
        }
        if upcoming, let url = URL(string: ticket), !ticket.isEmpty {
            Link("Bilet →", destination: url).font(.caption.weight(.heavy))
        }
    }
    .padding(12)
    .background(RoundedRectangle(cornerRadius: AppRadii.sm).fill(isHome ? AppColors.accentDeep.opacity(0.08) : AppColors.bgSoft))
}

private func fixRow(_ match: [String: Any]) -> some View {
    let home = match["home_team"] as? String ?? ""
    let away = match["away_team"] as? String ?? ""
    let week = match["week"]
    let played = match["played"] as? Bool == true
    let score = played ? "\(JSONValue.string(match["home_score"]))–\(JSONValue.string(match["away_score"]))" : "vs"
    return HStack {
        Text(JSONValue.string(week, default: "—")).frame(width: 28).font(.caption2).foregroundStyle(AppColors.muted)
        Text("\(home) \(score) \(away)").font(.caption2)
        Spacer()
        Text(match["kickoff_at"] as? String ?? "—").font(.caption2).foregroundStyle(AppColors.muted)
    }
    .padding(.vertical, 4)
}

private var officialLinks: some View {
    HStack(spacing: 8) {
        if let url = URL(string: "https://www.bursaspor.org.tr/") {
            Link("Resmi site", destination: url).font(.caption.weight(.heavy))
        }
        Link("Bursa haberleri", destination: AppConfig.siteBase.appendingPathComponent("haberler"))
            .font(.caption.weight(.heavy))
    }
}

// MARK: - Teleferik helpers

private func priceCard(_ price: [String: Any]) -> some View {
    HStack {
        VStack(alignment: .leading, spacing: 4) {
            Text(price["label"] as? String ?? "Bilet").font(.subheadline.weight(.heavy))
            if let note = price["note"] as? String { Text(note).font(.caption2).foregroundStyle(AppColors.muted) }
        }
        Spacer()
        Text("\(JSONValue.string(price["amount_tl"], default: JSONValue.string(price["amount"]))) TL").font(.headline.weight(.black))
    }
    .padding(12)
    .background(RoundedRectangle(cornerRadius: AppRadii.sm).fill(AppColors.bgSoft))
}

private func discountCard(_ item: [String: Any]) -> some View {
    VStack(alignment: .leading, spacing: 4) {
        Text(item["title"] as? String ?? item["label"] as? String ?? "İndirim").font(.subheadline.weight(.heavy))
        if let body = item["body"] as? String ?? item["detail"] as? String {
            Text(body).font(.caption).foregroundStyle(AppColors.muted)
        }
    }
    .padding(12)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(RoundedRectangle(cornerRadius: AppRadii.sm).fill(AppColors.bgSoft))
}

private func hoursPanel(_ hours: [String: Any]) -> some View {
    VStack(alignment: .leading, spacing: 6) {
        if let summer = hours["summer"] as? String ?? hours["yaz"] as? String { Text("Yaz: \(summer)").font(.caption) }
        if let winter = hours["winter"] as? String ?? hours["kis"] as? String { Text("Kış: \(winter)").font(.caption) }
        if let note = hours["note"] as? String { Text(note).font(.caption2).foregroundStyle(AppColors.muted) }
    }
}

private func busCard(_ item: [String: Any]) -> some View {
    VStack(alignment: .leading, spacing: 4) {
        Text(item["title"] as? String ?? item["line"] as? String ?? "Hat").font(.subheadline.weight(.heavy))
        if let detail = item["detail"] as? String ?? item["body"] as? String {
            Text(detail).font(.caption).foregroundStyle(AppColors.muted)
        }
    }
    .padding(12)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(RoundedRectangle(cornerRadius: AppRadii.sm).fill(AppColors.bgSoft))
}

private func stationRow(_ station: [String: Any], isLast: Bool) -> some View {
    HStack(alignment: .top, spacing: 10) {
        VStack(spacing: 0) {
            Circle().fill(AppColors.accentDeep).frame(width: 10, height: 10)
            if !isLast { Rectangle().fill(AppColors.muted.opacity(0.3)).frame(width: 2, height: 32) }
        }
        VStack(alignment: .leading, spacing: 2) {
            Text(station["name"] as? String ?? station["title"] as? String ?? "İstasyon").font(.caption.weight(.heavy))
            if let alt = station["altitude"] as? String ?? station["elevation"] as? String {
                Text(alt).font(.caption2).foregroundStyle(AppColors.muted)
            }
        }
        Spacer()
    }
}

// MARK: - Panel helper

private func panel<Content: View>(title: String, subtitle: String? = nil, trailing: AnyView? = nil, @ViewBuilder content: () -> Content) -> some View {
    VStack(alignment: .leading, spacing: 12) {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title).font(.headline.weight(.black))
                if let subtitle { Text(subtitle).font(.caption).foregroundStyle(AppColors.muted) }
            }
            Spacer()
            trailing
        }
        content()
    }
    .padding(16)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(RoundedRectangle(cornerRadius: AppRadii.lg).fill(AppColors.card))
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
