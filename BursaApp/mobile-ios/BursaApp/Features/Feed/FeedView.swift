import SwiftUI

// ─────────────────────────────────────────────────────────────
// MARK: FeedView — BursaVibe Anasayfa (FireVibe export merge)
// ─────────────────────────────────────────────────────────────
struct FeedView: View {
    @EnvironmentObject private var auth: AuthStore
    @StateObject private var vm = FeedViewModel()
    @State private var showAuth = false
    @State private var showNotifications = false
    @State private var feedTab = 0  // 0: Senin için, 1: Takip edilenler

    var onSearchTap: (() -> Void)?
    var onChipTap: ((String, String) -> Void)?
    var onHotels: (() -> Void)?
    var onSeeAllEvents: (() -> Void)?

    var body: some View {
        ScrollView(showsIndicators: false) {
            VStack(spacing: 0) {
                composeCard
                    .padding(.horizontal, 16)
                    .padding(.top, 16)

                nearbySection
                    .padding(.top, 20)

                feedTabSwitcher
                    .padding(.horizontal, 16)
                    .padding(.top, 24)

                feedPostsSection
                    .padding(.top, 16)
            }
            .padding(.bottom, 32)
        }
        .background(AppColors.bg.ignoresSafeArea())
        .safeAreaInset(edge: .top) { stickyHeader }
        .refreshable {
            vm.load(auth: auth, refresh: true)
            while vm.isLoading { try? await Task.sleep(nanoseconds: 100_000_000) }
        }
        .task { vm.load(auth: auth, refresh: true) }
        .onChange(of: auth.isLoggedIn) { _ in vm.load(auth: auth, refresh: true) }
        .alert("Hata", isPresented: Binding(get: { vm.errorMessage != nil },
                                            set: { if !$0 { vm.errorMessage = nil } })) {
            Button("Tamam", role: .cancel) {}
        } message: { Text(vm.errorMessage ?? "") }
        .sheet(isPresented: $showAuth) { AuthFlowView() }
        .sheet(isPresented: $showNotifications) { NavigationStack { NotificationsView() } }
    }

    // ─────────────────────────────────────────────────────────
    // MARK: Sticky Header
    // ─────────────────────────────────────────────────────────
    private var stickyHeader: some View {
        VStack(spacing: 0) {
            HStack(alignment: .top, spacing: 0) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Bursa bugün ne konuşuyor?")
                        .font(.system(size: 22, weight: .bold))
                        .foregroundColor(AppColors.ink)
                    Button {} label: {
                        HStack(spacing: 6) {
                            Image(systemName: "mappin.fill").font(.system(size: 11))
                            Text("Osmangazi, Bursa").font(.system(size: 12, weight: .semibold))
                            Image(systemName: "chevron.down").font(.system(size: 11, weight: .semibold))
                        }
                        .foregroundColor(Color(red: 23/255, green: 62/255, blue: 120/255))
                        .padding(.horizontal, 12).padding(.vertical, 7)
                        .background(Capsule().fill(AppColors.secondary))
                    }
                }
                Spacer()
                HStack(spacing: 12) {
                    Button { showNotifications = true } label: {
                        ZStack(alignment: .topTrailing) {
                            Image(systemName: "bell")
                                .font(.system(size: 17, weight: .semibold))
                                .foregroundColor(AppColors.ink)
                                .frame(width: 40, height: 40)
                                .background(Circle().fill(AppColors.card)
                                    .shadow(color: .black.opacity(0.08), radius: 6))
                                .overlay(Circle().stroke(AppColors.border, lineWidth: 1))
                            Text("3")
                                .font(.system(size: 9, weight: .heavy))
                                .foregroundColor(.white)
                                .frame(width: 16, height: 16)
                                .background(Circle().fill(AppColors.destructive))
                                .offset(x: 2, y: -2)
                        }
                    }
                    Circle()
                        .fill(AppColors.secondary)
                        .frame(width: 40, height: 40)
                        .overlay(Image(systemName: "person.fill")
                            .font(.system(size: 16))
                            .foregroundColor(AppColors.primary))
                        .shadow(color: .black.opacity(0.08), radius: 4)
                }
            }
            .padding(.horizontal, 20)
            .padding(.top, 12)
            .padding(.bottom, 12)
            Divider().overlay(AppColors.border.opacity(0.6))
        }
        .background(AppColors.bg.opacity(0.97))
    }

    // ─────────────────────────────────────────────────────────
    // MARK: Compose Card
    // ─────────────────────────────────────────────────────────
    private var composeCard: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Circle()
                    .fill(AppColors.secondary)
                    .frame(width: 40, height: 40)
                    .overlay(Image(systemName: "bubble.left")
                        .font(.system(size: 15))
                        .foregroundColor(AppColors.primary))
                Button { if !auth.isLoggedIn { showAuth = true } } label: {
                    HStack {
                        Text("Bursa'da ne oluyor?")
                            .font(.system(size: 15))
                            .foregroundColor(AppColors.muted)
                        Spacer()
                    }
                }
            }
            .padding(.horizontal, 16).padding(.top, 16)

            Divider().padding(.top, 14).overlay(AppColors.border)

            HStack {
                HStack(spacing: 2) {
                    composeBtn("photo", "Fotoğraf", AppColors.primary)
                    composeBtn("mappin", "Konum", AppColors.success)
                    composeBtn("calendar.badge.plus", "Etkinlik",
                               Color(red: 173/255, green: 101/255, blue: 0/255))
                }
                Spacer()
                Text("Paylaş")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundColor(AppColors.muted)
                    .padding(.horizontal, 12).padding(.vertical, 7)
                    .background(Capsule().fill(AppColors.surface))
            }
            .padding(.horizontal, 16).padding(.vertical, 12)

            HStack(spacing: 8) {
                Image(systemName: "sparkles").font(.system(size: 13)).foregroundColor(AppColors.primary)
                HStack(spacing: 0) {
                    Text("Paylaşmak için ")
                        .font(.system(size: 12))
                        .foregroundColor(Color(red: 23/255, green: 62/255, blue: 120/255))
                    Button { showAuth = true } label: {
                        Text("giriş yap")
                            .font(.system(size: 12, weight: .bold))
                            .foregroundColor(AppColors.primary)
                    }
                }
                Spacer()
            }
            .padding(.horizontal, 16).padding(.vertical, 10)
            .background(AppColors.secondary)
        }
        .background(AppColors.card)
        .clipShape(RoundedRectangle(cornerRadius: AppRadii.lg))
        .shadow(color: .black.opacity(0.06), radius: 8, y: 3)
        .overlay(RoundedRectangle(cornerRadius: AppRadii.lg).stroke(AppColors.border.opacity(0.7), lineWidth: 1))
    }

    private func composeBtn(_ icon: String, _ label: String, _ color: Color) -> some View {
        Button {} label: {
            HStack(spacing: 5) {
                Image(systemName: icon).font(.system(size: 13))
                Text(label).font(.system(size: 11, weight: .semibold))
            }
            .foregroundColor(color)
            .padding(.horizontal, 8).padding(.vertical, 7)
        }
    }

    // ─────────────────────────────────────────────────────────
    // MARK: Yakındaki Hareket
    // ─────────────────────────────────────────────────────────
    private var nearbySection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Yakındaki hareket")
                    .font(.system(size: 17, weight: .bold))
                    .foregroundColor(AppColors.ink)
                Spacer()
                Button { onSeeAllEvents?() } label: {
                    Text("Haritada gör")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(AppColors.primary)
                }
            }
            .padding(.horizontal, 16)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    nearbyCard(
                        icon: "person.3.fill", label: "Heykel'de", value: "12 kişi",
                        bg: Color(red: 255/255, green: 243/255, blue: 215/255),
                        iconBg: AppColors.accent, iconFg: Color(red: 51/255, green: 33/255, blue: 0/255),
                        showAvatars: true
                    )
                    nearbyCard(
                        icon: "music.note", label: "Nilüfer'de", value: "Canlı müzik",
                        sub: "Şimdi başlıyor",
                        bg: Color(red: 232/255, green: 245/255, blue: 242/255),
                        iconBg: AppColors.success, iconFg: .white
                    )
                    nearbyCard(
                        icon: "figure.walk", label: "Mudanya sahil", value: "Yürüyüş",
                        sub: "8 kişi katıldı",
                        bg: AppColors.secondary,
                        iconBg: AppColors.primary, iconFg: .white
                    )
                    if !vm.events.isEmpty {
                        ForEach(vm.events.prefix(2)) { e in
                            nearbyCard(
                                icon: "calendar", label: e.ilce.isEmpty ? "Bursa" : e.ilce,
                                value: e.title, sub: e.startsAtLabel,
                                bg: AppColors.secondary, iconBg: AppColors.primary, iconFg: .white
                            )
                        }
                    }
                }
                .padding(.horizontal, 16)
            }
        }
    }

    private func nearbyCard(
        icon: String, label: String, value: String, sub: String? = nil,
        bg: Color, iconBg: Color, iconFg: Color, showAvatars: Bool = false
    ) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            ZStack {
                Circle().fill(iconBg).frame(width: 32, height: 32)
                Image(systemName: icon).font(.system(size: 13)).foregroundColor(iconFg)
            }
            Text(label)
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(AppColors.ink)
                .padding(.top, 12)
            Text(value)
                .font(.system(size: 14, weight: .bold))
                .foregroundColor(AppColors.ink)
                .padding(.top, 2)
                .lineLimit(2)
            if showAvatars {
                HStack(spacing: -6) {
                    ForEach([AppColors.destructive, AppColors.primary, AppColors.success], id: \.self) { c in
                        Circle().fill(c).frame(width: 20, height: 20)
                            .overlay(Circle().stroke(bg, lineWidth: 2))
                    }
                }
                .padding(.top, 8)
            } else if let sub = sub {
                Text(sub)
                    .font(.system(size: 11))
                    .foregroundColor(AppColors.muted)
                    .padding(.top, 8)
                    .lineLimit(1)
            }
        }
        .frame(width: 142, alignment: .leading)
        .padding(12)
        .background(RoundedRectangle(cornerRadius: AppRadii.lg).fill(bg)
            .shadow(color: .black.opacity(0.05), radius: 6, y: 2))
    }

    // ─────────────────────────────────────────────────────────
    // MARK: Feed Tab Switcher
    // ─────────────────────────────────────────────────────────
    private var feedTabSwitcher: some View {
        HStack(spacing: 0) {
            feedTabBtn("Senin için", idx: 0)
            feedTabBtn("Takip edilenler", idx: 1)
        }
        .padding(4)
        .background(Capsule().fill(AppColors.surface))
    }

    private func feedTabBtn(_ title: String, idx: Int) -> some View {
        Button { feedTab = idx } label: {
            Text(title)
                .font(.system(size: 14, weight: feedTab == idx ? .bold : .semibold))
                .foregroundColor(feedTab == idx ? AppColors.ink : AppColors.muted)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 9)
                .background(
                    feedTab == idx
                        ? AnyView(Capsule().fill(AppColors.card)
                            .shadow(color: .black.opacity(0.08), radius: 4, y: 2))
                        : AnyView(Color.clear)
                )
        }
        .buttonStyle(.plain)
    }

    // ─────────────────────────────────────────────────────────
    // MARK: Feed Posts
    // ─────────────────────────────────────────────────────────
    private var feedPostsSection: some View {
        VStack(spacing: 16) {
            ForEach(vm.events.prefix(5)) { event in
                if event.slug.isEmpty {
                    feedPostCard(event: event)
                } else {
                    NavigationLink(value: event.slug) {
                        feedPostCard(event: event)
                    }
                    .buttonStyle(.plain)
                }
            }
            if vm.isLoading {
                ProgressView().padding(.vertical, 24)
            } else if vm.events.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "bubble.left.and.bubble.right")
                        .font(.system(size: 40))
                        .foregroundColor(AppColors.border)
                    Text("Henüz gönderi yok")
                        .font(.subheadline)
                        .foregroundColor(AppColors.muted)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 48)
            }
        }
        .padding(.horizontal, 16)
    }

    private func feedPostCard(event: EventItem) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            // Author row
            HStack(alignment: .top, spacing: 12) {
                Circle()
                    .fill(AppColors.secondary)
                    .frame(width: 44, height: 44)
                    .overlay(Image(systemName: "person.fill")
                        .font(.system(size: 17))
                        .foregroundColor(AppColors.primary))
                VStack(alignment: .leading, spacing: 3) {
                    HStack {
                        Text(event.title)
                            .font(.system(size: 14, weight: .bold))
                            .foregroundColor(AppColors.ink)
                            .lineLimit(1)
                        Spacer()
                        Image(systemName: "ellipsis")
                            .font(.system(size: 16))
                            .foregroundColor(AppColors.muted)
                    }
                    HStack(spacing: 4) {
                        Text(event.startsAtLabel.isEmpty ? event.whenLabel : event.startsAtLabel)
                            .font(.system(size: 12))
                            .foregroundColor(AppColors.muted)
                        if !event.ilce.isEmpty {
                            Text("·").foregroundColor(AppColors.muted).font(.system(size: 12))
                            Text(event.ilce)
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(AppColors.success)
                        }
                    }
                }
            }
            .padding(16)

            // Location tag
            if !event.ilce.isEmpty {
                HStack(spacing: 6) {
                    Image(systemName: "mappin.fill")
                        .font(.system(size: 11))
                        .foregroundColor(AppColors.primary)
                    Text(event.ilce)
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(Color(red: 23/255, green: 62/255, blue: 120/255))
                }
                .padding(.horizontal, 10).padding(.vertical, 6)
                .background(Capsule().fill(AppColors.secondary))
                .padding(.leading, 16).padding(.bottom, 12)
            }

            // Image
            if !event.imgUrl.isEmpty {
                RemoteImage(url: event.imgUrl, placeholder: "photo")
                    .frame(maxWidth: .infinity, minHeight: 180, maxHeight: 220)
                    .clipped()
            }

            // Actions row
            HStack {
                HStack(spacing: 20) {
                    postActionBtn("heart", "42")
                    postActionBtn("bubble.left", "8")
                    postActionBtn("arrow.2.squarepath", nil)
                }
                Spacer()
                HStack(spacing: 16) {
                    postActionBtn("bookmark", nil)
                    postActionBtn("flag", nil)
                }
            }
            .foregroundColor(AppColors.muted)
            .padding(.horizontal, 16).padding(.vertical, 12)
        }
        .background(AppColors.card)
        .clipShape(RoundedRectangle(cornerRadius: AppRadii.lg))
        .shadow(color: .black.opacity(0.06), radius: 6, y: 2)
        .overlay(RoundedRectangle(cornerRadius: AppRadii.lg).stroke(AppColors.border.opacity(0.7), lineWidth: 1))
    }

    private func postActionBtn(_ icon: String, _ count: String?) -> some View {
        Button {} label: {
            HStack(spacing: 6) {
                Image(systemName: icon).font(.system(size: 18))
                if let count = count {
                    Text(count).font(.system(size: 13, weight: .semibold))
                }
            }
        }
    }
}

