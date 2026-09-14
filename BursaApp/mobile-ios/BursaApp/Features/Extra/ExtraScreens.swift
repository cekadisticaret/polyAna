import SwiftUI
import PhotosUI

// MARK: - Create Event

struct CreateEventView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var auth: AuthStore
    @State private var title = ""
    @State private var venue = ""
    @State private var address = ""
    @State private var date = ""
    @State private var category = "concert"
    @State private var saving = false
    @State private var message: String?

    private let categories = [
        ("concert", "Konser"), ("theater", "Tiyatro"), ("event", "Etkinlik"), ("family", "Aile"),
    ]

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("Konser, tiyatro veya buluşma ekle. Onay sonrası herkese görünür.")
                        .font(.caption)
                        .foregroundStyle(AppColors.muted)
                }
                Section {
                    TextField("Başlık", text: $title)
                    TextField("Mekan", text: $venue)
                    TextField("Adres", text: $address)
                    TextField("Tarih (YYYY-MM-DD HH:MM)", text: $date)
                    Picker("Kategori", selection: $category) {
                        ForEach(categories, id: \.0) { key, label in
                            Text(label).tag(key)
                        }
                    }
                }
                if let message {
                    Section { Text(message).foregroundStyle(AppColors.coral) }
                }
            }
            .navigationTitle("Etkinlik oluştur")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Kapat") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(saving ? "…" : "Gönder") { Task { await submit() } }
                        .disabled(saving || title.trimmingCharacters(in: .whitespacesAndNewlines).count < 3)
                }
            }
        }
    }

    @MainActor
    private func submit() async {
        saving = true
        message = nil
        defer { saving = false }
        do {
            try await auth.apiClient().createEvent([
                "title": title.trimmingCharacters(in: .whitespacesAndNewlines),
                "category": category,
                "venue_name": venue.trimmingCharacters(in: .whitespacesAndNewlines),
                "address": address.trimmingCharacters(in: .whitespacesAndNewlines),
                "starts_at": date.trimmingCharacters(in: .whitespacesAndNewlines),
                "blurb": "Mobil uygulama üzerinden oluşturuldu",
            ])
            dismiss()
        } catch {
            message = error.localizedDescription
        }
    }
}

// MARK: - Notifications

struct NotificationsView: View {
    @EnvironmentObject private var auth: AuthStore
    @State private var events: [EventItem] = []
    @State private var loading = true

    var body: some View {
        AppPage(title: "Bildirimler") {
            List {
                if loading {
                    ProgressView().frame(maxWidth: .infinity)
                }
                ForEach(events) { event in
                    if event.slug.isEmpty {
                        eventRow(event)
                    } else {
                        NavigationLink(value: event.slug) {
                            eventRow(event)
                        }
                    }
                }
            }
            .listStyle(.plain)
            .navigationDestination(for: String.self) { slug in
                PlaceDetailView(slug: slug)
            }
            .refreshable { await load() }
            .task { await load() }
        }
    }

    private func eventRow(_ event: EventItem) -> some View {
        HStack(spacing: 12) {
            RemoteImage(url: event.imgUrl, placeholder: "bell.fill")
                .frame(width: 52, height: 52)
                .clipShape(RoundedRectangle(cornerRadius: 14))
            VStack(alignment: .leading, spacing: 4) {
                Text(event.title).font(.headline)
                Text("\(event.whenLabel) · \(event.startsAtLabel)")
                    .font(.caption)
                    .foregroundStyle(AppColors.muted)
                if !event.ilce.isEmpty {
                    Text(event.ilce).font(.caption2).foregroundStyle(AppColors.muted)
                }
            }
        }
        .padding(.vertical, 4)
    }

    @MainActor
    private func load() async {
        loading = true
        defer { loading = false }
        if let rows = try? await auth.apiClient().upcomingEvents() {
            events = rows
        }
    }
}

// MARK: - Place Search

struct PlaceSearchView: View {
    @EnvironmentObject private var auth: AuthStore
    @State private var query: String
    @State private var results: [PlaceItem] = []
    @State private var loading = false
    @State private var error: String?

    init(initialQuery: String = "") {
        _query = State(initialValue: initialQuery)
    }

    var body: some View {
        AppPage(title: "Ara") {
            VStack(spacing: 0) {
                HStack {
                    TextField("Mekan, etkinlik…", text: $query)
                        .textFieldStyle(.roundedBorder)
                        .submitLabel(.search)
                        .onSubmit { Task { await search() } }
                    Button("Ara") { Task { await search() } }
                        .buttonStyle(.borderedProminent)
                        .tint(AppColors.accentDeep)
                }
                .padding(16)
                if let error {
                    Text(error).foregroundStyle(AppColors.coral).padding(.horizontal, 16)
                }
                ScrollView {
                    PlaceListSection(places: results)
                        .padding(16)
                }
            }
        }
        .task {
            if query.trimmingCharacters(in: .whitespacesAndNewlines).count >= 2 {
                await search()
            }
        }
    }

    @MainActor
    private func search() async {
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard q.count >= 2 else {
            error = q.isEmpty ? nil : "En az 2 karakter yaz"
            results = []
            return
        }
        loading = true
        error = nil
        defer { loading = false }
        do {
            results = try await auth.apiClient().places(q: q, limit: 40)
        } catch {
            self.error = error.localizedDescription
        }
    }
}

// MARK: - Route Planner

struct RoutePlannerView: View {
    @EnvironmentObject private var auth: AuthStore
    @State private var people = 2
    @State private var budget = "2000"
    @State private var transport = "bus"
    @State private var loading = false
    @State private var route: [String: Any]?
    @State private var error: String?

    private let transports = [("bus", "Toplu taşıma"), ("car", "Araba"), ("walk", "Yürüyüş")]

    var body: some View {
        AppPage(title: "Rota planlayıcı") {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text("Bütçene ve ulaşımına göre 1 günlük Bursa planı")
                        .font(.subheadline)
                        .foregroundStyle(AppColors.muted)
                    VStack(alignment: .leading, spacing: 12) {
                        Stepper("Kişi: \(people)", value: $people, in: 1...8)
                        TextField("Bütçe (TL)", text: $budget)
                            .keyboardType(.numberPad)
                            .textFieldStyle(.roundedBorder)
                        Picker("Ulaşım", selection: $transport) {
                            ForEach(transports, id: \.0) { key, label in
                                Text(label).tag(key)
                            }
                        }
                        .pickerStyle(.segmented)
                        Button(loading ? "Hesaplanıyor…" : "Plan oluştur") {
                            Task { await buildRoute() }
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(AppColors.nav)
                        .disabled(loading)
                    }
                    .padding(16)
                    .background(RoundedRectangle(cornerRadius: AppRadii.md).fill(AppColors.card))
                    if let error {
                        Text(error).foregroundStyle(AppColors.coral)
                    }
                    if let route {
                        routeResult(route)
                    }
                }
                .padding(16)
            }
        }
    }

    @ViewBuilder
    private func routeResult(_ data: [String: Any]) -> some View {
        let title = data["title"] as? String ?? "Günün planı"
        let estTotal = data["est_total_tl"]
        let budget = data["budget_tl"]
        let within = data["within_budget"] as? Bool == true
        let slots = data["slots"] as? [[String: Any]] ?? data["stops"] as? [[String: Any]] ?? data["places"] as? [[String: Any]] ?? []
        let tips = (data["tips"] as? [Any] ?? []).map { "\($0)" }.filter { !$0.isEmpty }

        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 10) {
                Text("Günün planı")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(AppColors.muted)
                Text(title)
                    .font(.title3.weight(.black))
                HStack(spacing: 8) {
                    if estTotal != nil {
                        MetaChip(text: "~\(JSONValue.int(estTotal)) TL", color: AppColors.ink)
                    }
                    if budget != nil {
                        MetaChip(
                            text: within ? "Bütçe \(JSONValue.int(budget)) TL ✓" : "Bütçe \(JSONValue.int(budget)) TL aşıldı",
                            color: within ? AppColors.accentDeep : AppColors.coral
                        )
                    }
                    MetaChip(text: "\(slots.count) durak", color: AppColors.muted)
                }
                if !tips.isEmpty {
                    ForEach(Array(tips.enumerated()), id: \.offset) { _, tip in
                        Text("• \(tip)")
                            .font(.caption)
                            .foregroundStyle(AppColors.muted)
                    }
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: AppRadii.md).fill(AppColors.card).cardShadow())

            ForEach(Array(slots.enumerated()), id: \.offset) { idx, slot in
                if let transit = slot["transit_from_prev"] as? String, !transit.isEmpty {
                    HStack(alignment: .top, spacing: 8) {
                        Text("🚌")
                        Text(transit)
                            .font(.caption)
                            .foregroundStyle(AppColors.muted)
                    }
                    .padding(.leading, 18)
                }
                RouteStopCard(slot: slot, index: idx + 1)
            }
        }
    }

    @MainActor
    private func buildRoute() async {
        loading = true
        error = nil
        route = nil
        defer { loading = false }
        do {
            let budgetVal = Int(budget.trimmingCharacters(in: .whitespacesAndNewlines)) ?? 0
            route = try await auth.apiClient().planDayRoute(people: people, budgetTl: budgetVal, transport: transport)
        } catch {
            self.error = error.localizedDescription
        }
    }
}

private struct RouteStopCard: View {
    let slot: [String: Any]
    let index: Int

    private var slug: String {
        (slot["slug"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var body: some View {
        let content = stopContent
        if slug.isEmpty {
            content
        } else {
            NavigationLink(value: slug) { content }.buttonStyle(.plain)
        }
    }

    private var stopContent: some View {
        HStack(alignment: .top, spacing: 12) {
            Text(slotEmoji)
                .font(.title3)
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 8) {
                    if let time = slot["slot_time"] as? String, !time.isEmpty {
                        Text(time).font(.caption.weight(.heavy))
                    }
                    if let label = slot["slot_label"] as? String, !label.isEmpty {
                        Text(label).font(.caption.weight(.semibold)).foregroundStyle(AppColors.muted)
                    }
                }
                Text(slot["title"] as? String ?? slot["name"] as? String ?? "Durak \(index)")
                    .font(.headline.weight(.heavy))
                HStack(spacing: 8) {
                    if let ilce = slot["ilce"] as? String, !ilce.isEmpty {
                        Text(ilce).font(.caption).foregroundStyle(AppColors.muted)
                    }
                    Text(costLabel)
                        .font(.caption.weight(.bold))
                        .foregroundStyle(costIsFree ? AppColors.accentDeep : AppColors.muted)
                }
            }
            Spacer(minLength: 0)
            if !slug.isEmpty {
                Image(systemName: "chevron.right").foregroundStyle(AppColors.muted.opacity(0.6))
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: AppRadii.md).fill(AppColors.card).cardShadow())
    }

    private var slotEmoji: String {
        let label = (slot["slot_label"] as? String ?? "").lowercased()
        if label.contains("kahvalt") { return "☕️" }
        if label.contains("öğle") || label.contains("ogle") { return "🍽️" }
        if label.contains("akşam") || label.contains("aksam") { return "🌙" }
        if label.contains("müze") || label.contains("muze") { return "🏛️" }
        return "📍"
    }

    private var costLabel: String {
        let cost = JSONValue.int(slot["slot_cost_tl"], default: -1)
        return cost <= 0 ? "Ücretsiz" : "~\(cost) TL"
    }

    private var costIsFree: Bool {
        JSONValue.int(slot["slot_cost_tl"], default: 0) <= 0
    }
}

// MARK: - Okey

struct OkeyView: View {
    @EnvironmentObject private var auth: AuthStore
    @State private var rows: [ActivitySeek] = []
    @State private var loading = true

    var body: some View {
        AppPage(title: "Okey — 4. arayan") {
            ScrollView {
                LazyVStack(spacing: 12) {
                    if loading { ProgressView().padding() }
                    ForEach(rows) { row in
                        okeyCard(row)
                    }
                }
                .padding(16)
            }
            .refreshable { await load() }
            .task { await load() }
        }
    }

    private func okeyCard(_ row: ActivitySeek) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(row.host).font(.headline)
                Spacer()
                if !row.ilce.isEmpty {
                    Text(row.ilce).font(.caption).padding(.horizontal, 8).padding(.vertical, 4)
                        .background(AppColors.bg).clipShape(Capsule())
                }
            }
            if !row.timeLabel.isEmpty {
                Text(row.timeLabel).font(.caption).foregroundStyle(AppColors.muted)
            }
            if !row.note.isEmpty { Text(row.note).font(.subheadline) }
            if row.pointsMin > 0 {
                Text("Min. \(row.pointsMin) puan").font(.caption).foregroundStyle(AppColors.muted)
            }
            HStack {
                Spacer()
                Button(row.joined ? "Katıldın" : "Katıl") {
                    Task { await join(row) }
                }
                .buttonStyle(.borderedProminent)
                .tint(AppColors.nav)
                .disabled(row.joined || !auth.isLoggedIn)
            }
        }
        .padding(16)
        .background(RoundedRectangle(cornerRadius: AppRadii.lg).fill(AppColors.card))
    }

    @MainActor
    private func load() async {
        loading = true
        defer { loading = false }
        if let list = try? await auth.apiClient().okeySeeking() {
            rows = list
        }
    }

    @MainActor
    private func join(_ row: ActivitySeek) async {
        guard auth.isLoggedIn else { return }
        try? await auth.apiClient().joinActivitySeek(id: row.id)
        await load()
    }
}

// MARK: - Profile Settings

struct ProfileSettingsView: View {
    @EnvironmentObject private var auth: AuthStore
    @State private var name = ""
    @State private var showFullName = false
    @State private var curPass = ""
    @State private var newPass = ""
    @State private var newPass2 = ""
    @State private var saving = false
    @State private var uploading = false
    @State private var status: String?
    @State private var isError = false
    @State private var photoItem: PhotosPickerItem?

    var body: some View {
        AppPage(title: "Hesap ayarları") {
            Form {
                Section("Profil fotoğrafı") {
                    HStack {
                        RemoteImage(url: auth.user?.avatarUrl ?? "", placeholder: "person.crop.circle.fill")
                            .frame(width: 64, height: 64)
                            .clipShape(Circle())
                        PhotosPicker(selection: $photoItem, matching: .images) {
                            Text("Galeriden seç")
                        }
                        .disabled(uploading)
                        if uploading {
                            ProgressView().scaleEffect(0.85)
                        }
                    }
                }
                Section("Bilgiler") {
                    TextField("Ad", text: $name)
                    Toggle("Tam adımı göster", isOn: $showFullName)
                    Button(saving ? "Kaydediliyor…" : "Profili kaydet") {
                        Task { await saveProfile() }
                    }
                    .disabled(saving)
                }
                Section("Şifre") {
                    SecureField("Mevcut şifre", text: $curPass)
                    SecureField("Yeni şifre", text: $newPass)
                    SecureField("Yeni şifre (tekrar)", text: $newPass2)
                    Button("Şifreyi güncelle") { Task { await savePassword() } }
                        .disabled(saving)
                }
                if let status {
                    Section {
                        Text(status).foregroundStyle(isError ? AppColors.coral : AppColors.accentDeep)
                    }
                }
            }
        }
        .onAppear {
            name = auth.user?.name ?? ""
            showFullName = auth.user?.showFullName ?? false
        }
        .onChange(of: photoItem) { item in
            guard let item else { return }
            Task { await uploadPhoto(item) }
        }
    }

    @MainActor
    private func uploadPhoto(_ item: PhotosPickerItem) async {
        uploading = true
        isError = false
        defer { uploading = false }
        do {
            guard let data = try await item.loadTransferable(type: Data.self) else { return }
            try await auth.uploadAvatar(data, filename: "avatar.jpg")
            status = "Profil fotoğrafı güncellendi."
        } catch {
            isError = true
            status = error.localizedDescription
        }
    }

    @MainActor
    private func saveProfile() async {
        saving = true
        isError = false
        defer { saving = false }
        do {
            try await auth.updateProfile(name: name.trimmingCharacters(in: .whitespacesAndNewlines), showFullName: showFullName)
            status = "Profil kaydedildi."
        } catch {
            isError = true
            status = error.localizedDescription
        }
    }

    @MainActor
    private func savePassword() async {
        saving = true
        isError = false
        defer { saving = false }
        do {
            try await auth.updatePassword(current: curPass, newPassword: newPass, newPassword2: newPass2)
            curPass = ""
            newPass = ""
            newPass2 = ""
            status = "Şifre güncellendi."
        } catch {
            isError = true
            status = error.localizedDescription
        }
    }
}

// MARK: - Activity Buddy (full)

struct ActivityBuddyView: View {
    @EnvironmentObject private var auth: AuthStore
    @State private var rows: [ActivitySeek] = []
    @State private var types: [ActivityType] = []
    @State private var filter = ""
    @State private var loading = true
    @State private var showCreate = false
    @State private var showAuth = false

    var body: some View {
        AppPage(title: "Partner ara") {
            VStack(spacing: 0) {
                if !types.isEmpty {
                    FilterChips(
                        items: [("", "Tümü")] + types.map { ($0.key, "\($0.emoji) \($0.label)") },
                        selected: filter,
                        onSelect: { filter = $0; Task { await load() } }
                    )
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                }
                ScrollView {
                    LazyVStack(spacing: 12) {
                        if loading { ProgressView().padding() }
                        ForEach(rows) { row in
                            activityCard(row)
                        }
                        if !loading && rows.isEmpty {
                            Text("Henüz ilan yok").foregroundStyle(AppColors.muted).padding(.vertical, 40)
                        }
                    }
                    .padding(16)
                }
            }
            .refreshable { await load() }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("İlan ver") {
                        if auth.isLoggedIn { showCreate = true } else { showAuth = true }
                    }
                }
            }
            .sheet(isPresented: $showCreate) { createSheet }
            .sheet(isPresented: $showAuth) { AuthFlowView() }
            .task { await load() }
        }
    }

    private func activityCard(_ row: ActivitySeek) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("\(row.emoji) \(row.title.isEmpty ? row.activityLabel : row.title)")
                    .font(.headline)
                Spacer()
                if row.isMine { Text("Senin").font(.caption2).foregroundStyle(AppColors.accentDeep) }
            }
            if !row.host.isEmpty { Text(row.host).font(.caption).foregroundStyle(AppColors.muted) }
            if !row.timeLabel.isEmpty { Text(row.timeLabel).font(.caption) }
            if !row.venue.isEmpty { Text(row.venue).font(.caption).foregroundStyle(AppColors.muted) }
            if !row.note.isEmpty { Text(row.note).font(.subheadline) }
            HStack {
                if row.spotsLeft > 0 {
                    Text("\(row.spotsLeft) kişi aranıyor").font(.caption2).foregroundStyle(AppColors.muted)
                }
                Spacer()
                if row.joined {
                    Button("Ayrıl") { Task { await leave(row) } }
                        .buttonStyle(.bordered)
                } else if row.pending {
                    Text("Onay bekliyor").font(.caption).foregroundStyle(AppColors.muted)
                } else {
                    Button("Katıl") { Task { await join(row) } }
                        .buttonStyle(.borderedProminent)
                        .tint(AppColors.nav)
                        .disabled(!auth.isLoggedIn)
                }
            }
        }
        .padding(14)
        .background(RoundedRectangle(cornerRadius: AppRadii.md).fill(AppColors.card))
    }

    private var createSheet: some View {
        ActivityCreateSheet(types: types, initialType: filter) {
            showCreate = false
            Task { await load() }
        }
    }

    @MainActor
    private func load() async {
        loading = true
        defer { loading = false }
        do {
            types = try await auth.apiClient().activityTypes()
            rows = try await auth.apiClient().activitySeeking(type: filter.isEmpty ? nil : filter)
        } catch {
            rows = []
        }
    }

    @MainActor
    private func join(_ row: ActivitySeek) async {
        guard auth.isLoggedIn else { showAuth = true; return }
        try? await auth.apiClient().joinActivitySeek(id: row.id)
        await load()
    }

    @MainActor
    private func leave(_ row: ActivitySeek) async {
        try? await auth.apiClient().leaveActivitySeek(id: row.id)
        await load()
    }
}

private struct ActivityCreateSheet: View {
    @EnvironmentObject private var auth: AuthStore
    @Environment(\.dismiss) private var dismiss
    let types: [ActivityType]
    let initialType: String
    let onDone: () -> Void

    @State private var activityType = ""
    @State private var title = ""
    @State private var whenLabel = "Esnek"
    @State private var venue = ""
    @State private var note = ""
    @State private var contact = ""
    @State private var slots = 1
    @State private var saving = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Picker("Aktivite", selection: $activityType) {
                    ForEach(types) { t in
                        Text("\(t.emoji) \(t.label)").tag(t.key)
                    }
                }
                TextField("Başlık (isteğe bağlı)", text: $title)
                Stepper("Kaç kişi: \(slots)", value: $slots, in: 1...10)
                TextField("Ne zaman?", text: $whenLabel)
                TextField("Bulışma yeri", text: $venue)
                TextField("Not", text: $note, axis: .vertical)
                TextField("İletişim", text: $contact)
                if let error {
                    Text(error).foregroundStyle(AppColors.coral)
                }
            }
            .navigationTitle("İlan ver")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("İptal") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(saving ? "…" : "Yayınla") { Task { await publish() } }
                        .disabled(saving || activityType.isEmpty)
                }
            }
            .onAppear {
                if activityType.isEmpty {
                    activityType = initialType.isEmpty ? (types.first?.key ?? "") : initialType
                }
            }
        }
    }

    @MainActor
    private func publish() async {
        saving = true
        error = nil
        defer { saving = false }
        var payload: [String: Any] = [
            "activity_type": activityType,
            "slots_needed": slots,
            "when_label": whenLabel.trimmingCharacters(in: .whitespacesAndNewlines),
            "venue": venue.trimmingCharacters(in: .whitespacesAndNewlines),
            "note": note.trimmingCharacters(in: .whitespacesAndNewlines),
            "contact_hint": contact.trimmingCharacters(in: .whitespacesAndNewlines),
        ]
        let t = title.trimmingCharacters(in: .whitespacesAndNewlines)
        if !t.isEmpty { payload["title"] = t }
        do {
            try await auth.apiClient().createActivitySeek(payload)
            dismiss()
            onDone()
        } catch {
            self.error = error.localizedDescription
        }
    }
}

// MARK: - News Detail

struct NewsDetailView: View {
    @EnvironmentObject private var auth: AuthStore
    let slug: String
    @State private var article: [String: Any]?
    @State private var loading = true

    var body: some View {
        AppPage(title: article?["title"] as? String ?? "Haber") {
            ScrollView {
                if loading {
                    ProgressView().padding(.vertical, 40)
                } else if let article {
                    VStack(alignment: .leading, spacing: 12) {
                        if let img = article["img_url"] as? String, !img.isEmpty {
                            RemoteImage(url: img).frame(height: 200).clipShape(RoundedRectangle(cornerRadius: AppRadii.md))
                        }
                        if let date = article["date_label"] as? String ?? article["when"] as? String {
                            Text(date).font(.caption).foregroundStyle(AppColors.muted)
                        }
                        if let body = article["body"] as? String ?? article["content"] as? String {
                            Text(body).font(.body)
                        } else if let sum = article["summary"] as? String {
                            Text(sum).font(.body)
                        }
                    }
                    .padding(16)
                }
            }
            .task { await load() }
        }
    }

    @MainActor
    private func load() async {
        loading = true
        defer { loading = false }
        if let json = try? await auth.apiClient().bursaNewsDetail(slug: slug) {
            article = json["article"] as? [String: Any] ?? json["news"] as? [String: Any] ?? json
        }
    }
}

// MARK: - Pharmacy Detail

struct PharmacyDetailView: View {
    @EnvironmentObject private var auth: AuthStore
    let slug: String
    @State private var row: [String: Any]?

    var body: some View {
        AppPage(title: row?["title"] as? String ?? row?["name"] as? String ?? "Eczane") {
            ScrollView {
                if let row {
                    VStack(alignment: .leading, spacing: 10) {
                        if let ilce = row["ilce"] as? String { Text(ilce).foregroundStyle(AppColors.accentDeep) }
                        if let addr = row["address"] as? String ?? row["adres"] as? String {
                            Text(addr)
                        }
                        if let tel = row["phone"] as? String ?? row["tel"] as? String, !tel.isEmpty {
                            Link("Ara: \(tel)", destination: URL(string: "tel:\(tel.filter { $0.isNumber || $0 == "+" })") ?? URL(string: "tel:")!)
                        }
                        if let lat = JSONValue.double(row["lat"]), let lng = JSONValue.double(row["lng"]) {
                            Link("Haritada aç", destination: URL(string: "https://maps.apple.com/?daddr=\(lat),\(lng)")!)
                        }
                    }
                    .padding(16)
                } else {
                    ProgressView().padding(.vertical, 40)
                }
            }
            .task {
                if let json = try? await auth.apiClient().nobetciEczaneDetail(slug: slug) {
                    row = json["pharmacy"] as? [String: Any] ?? json
                }
            }
        }
    }
}
