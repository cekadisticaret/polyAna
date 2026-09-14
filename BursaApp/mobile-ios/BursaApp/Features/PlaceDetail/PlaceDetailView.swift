import SwiftUI

struct PlaceDetailView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var auth: AuthStore
    let slug: String
    @State private var place: [String: Any]?
    @State private var loading = true
    @State private var error: String?
    @State private var isFav = false
    @State private var favCount = 0
    @State private var favBusy = false
    @State private var showAuth = false
    @State private var tab = 0

    var body: some View {
        ZStack(alignment: .bottom) {
            ScrollView(showsIndicators: false) {
                VStack(alignment: .leading, spacing: 0) {
                    heroSection
                    contentSection
                }
                .padding(.bottom, 100)
            }
            bottomBar
        }
        .background(AppColors.bg.ignoresSafeArea())
        .navigationBarHidden(true)
        .task { await load() }
        .refreshable { await load() }
        .sheet(isPresented: $showAuth) { AuthFlowView() }
    }

    @ViewBuilder
    private var heroSection: some View {
        if loading && place == nil {
            ProgressView().frame(maxWidth: .infinity).padding(.vertical, 80)
        } else if let error {
            VStack(spacing: 12) {
                Text(error).foregroundStyle(AppColors.coral)
                Button("Tekrar dene") { Task { await load() } }
            }.padding()
        } else if let place {
            ZStack(alignment: .top) {
                if let img = place["img_url"] as? String, !img.isEmpty {
                    RemoteImage(url: img, placeholder: "photo")
                        .frame(height: 320)
                        .frame(maxWidth: .infinity)
                        .clipped()
                } else {
                    Rectangle().fill(AppColors.bgSoft).frame(height: 320)
                }
                HStack {
                    TravelGhostButton(icon: "chevron.left") { dismiss() }
                    Spacer()
                    Button { Task { await toggleFavorite() } } label: {
                        Image(systemName: isFav ? "heart.fill" : "heart")
                            .font(.body.weight(.semibold))
                            .foregroundStyle(isFav ? AppColors.coral : AppColors.ink)
                            .frame(width: 42, height: 42)
                            .background(Circle().fill(.white).shadow(color: .black.opacity(0.10), radius: 8, y: 3))
                    }
                    .buttonStyle(.plain)
                    .disabled(favBusy)
                }
                .padding(.horizontal, 16)
                .padding(.top, 8)
            }
            .clipShape(RoundedRectangle(cornerRadius: AppRadii.xl, style: .continuous))
            .padding(.horizontal, 12)
            .padding(.top, 8)
        }
    }

    @ViewBuilder
    private var contentSection: some View {
        if let place {
            VStack(alignment: .leading, spacing: 16) {
                HStack(alignment: .top) {
                    Text(place["title"] as? String ?? "")
                        .font(.title2.weight(.bold))
                        .foregroundStyle(AppColors.ink)
                    Spacer()
                    HStack(spacing: 4) {
                        Image(systemName: "star.fill").foregroundStyle(AppColors.amber)
                        Text(travelRating(seed: slug.hashValue)).font(.subheadline.weight(.bold))
                    }
                }

                HStack(spacing: 10) {
                    TravelInfoPod(icon: "globe.europe.africa.fill", label: "Konum", value: place["ilce"] as? String ?? "Bursa")
                    TravelInfoPod(icon: "clock.fill", label: "Durum", value: openLabel(for: place))
                    TravelInfoPod(icon: "sun.max.fill", label: "Bölge", value: place["category_label"] as? String ?? "Keşif")
                }

                TravelDetailTabs(selected: $tab, titles: ["Genel", "Detay", "Yorum"])

                Group {
                    switch tab {
                    case 1: detailTab(place)
                    case 2: reviewsTab
                    default: overviewTab(place)
                    }
                }

                if let img = place["img_url"] as? String, !img.isEmpty {
                    Text("Galeri").font(.headline.weight(.bold)).foregroundStyle(AppColors.ink)
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 10) {
                            ForEach(0..<4, id: \.self) { _ in
                                RemoteImage(url: img, placeholder: "photo")
                                    .frame(width: 88, height: 88)
                                    .clipShape(RoundedRectangle(cornerRadius: AppRadii.sm))
                            }
                        }
                    }
                }
            }
            .padding(.horizontal, AppSpacing.screenX)
            .padding(.top, 16)
        }
    }

    private func overviewTab(_ place: [String: Any]) -> some View {
        Text(bodyText(for: place))
            .font(.body)
            .foregroundStyle(AppColors.muted)
            .lineSpacing(5)
    }

    private func detailTab(_ place: [String: Any]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            if let address = place["address"] as? String, !address.isEmpty {
                Label(address, systemImage: "mappin.and.ellipse")
                    .font(.subheadline)
                    .foregroundStyle(AppColors.ink)
            }
            if !metaLine(for: place).isEmpty {
                Text(metaLine(for: place)).font(.caption.weight(.semibold)).foregroundStyle(AppColors.muted)
            }
            if let maps = mapsURL(for: place) {
                Link(destination: maps) {
                    Label("Haritada aç", systemImage: "map.fill")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(AppColors.nav)
                }
            }
        }
    }

    private var reviewsTab: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 4) {
                Image(systemName: "star.fill").foregroundStyle(AppColors.amber)
                Text("\(travelRating(seed: slug.hashValue)) · BursaApp topluluğu")
                    .font(.subheadline.weight(.semibold))
            }
            Text("\(max(favCount, 1)) kişi favoriledi.")
                .font(.caption)
                .foregroundStyle(AppColors.muted)
        }
    }

    @ViewBuilder
    private var bottomBar: some View {
        if place != nil {
            TravelBottomActionBar(
                leftTitle: "Favori",
                leftValue: "Toplam: \(favCount)",
                buttonTitle: webURL(for: place ?? [:]) != nil ? "İncele" : "Harita"
            ) {
                if let url = webURL(for: place ?? [:]) {
                    UIApplication.shared.open(url)
                } else if let maps = mapsURL(for: place ?? [:]) {
                    UIApplication.shared.open(maps)
                }
            }
        }
    }

    private func openLabel(for place: [String: Any]) -> String {
        if let when = place["starts_at_label"] as? String, !when.isEmpty { return when }
        return "Açık"
    }

    private func metaLine(for place: [String: Any]) -> String {
        [place["category_label"] as? String, place["ilce"] as? String, place["starts_at_label"] as? String]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .joined(separator: " · ")
    }

    private func bodyText(for place: [String: Any]) -> String {
        let blurb = (place["blurb"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let body = (place["body"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return !blurb.isEmpty ? blurb : (body.isEmpty ? "Bursa'da keşfedilmeyi bekleyen bir durak." : body)
    }

    private func mapsURL(for place: [String: Any]) -> URL? {
        if let lat = place["lat"] as? Double, let lng = place["lng"] as? Double {
            return URL(string: "https://maps.apple.com/?ll=\(lat),\(lng)")
        }
        if let lat = place["lat"] as? Int, let lng = place["lng"] as? Int {
            return URL(string: "https://maps.apple.com/?ll=\(lat),\(lng)")
        }
        return nil
    }

    private func webURL(for place: [String: Any]) -> URL? {
        let path = (place["path"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let s = (place["slug"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? slug
        let rel = path.isEmpty ? "/yer/\(s)" : path
        return URL(string: rel, relativeTo: AppConfig.siteBase)?.absoluteURL
    }

    @MainActor
    private func load() async {
        loading = true
        error = nil
        defer { loading = false }
        do {
            let p = try await auth.apiClient().placeDetail(slug: slug)
            place = p
            isFav = p["is_fav"] as? Bool ?? false
            favCount = JSONValue.int(p["fav_count"])
        } catch {
            self.error = error.localizedDescription
        }
    }

    @MainActor
    private func toggleFavorite() async {
        guard auth.isLoggedIn else { showAuth = true; return }
        favBusy = true
        defer { favBusy = false }
        do {
            let (fav, count) = try await auth.apiClient().togglePlaceFavorite(slug: slug)
            isFav = fav
            favCount = count
        } catch {
            self.error = error.localizedDescription
        }
    }
}
