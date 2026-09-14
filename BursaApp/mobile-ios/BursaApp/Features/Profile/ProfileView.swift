import SwiftUI

struct ProfileView: View {
    @EnvironmentObject private var auth: AuthStore
    @Binding var tabSelection: ShellTab
    @Binding var navPath: NavigationPath
    @State private var showAuth = false

    @State private var menu: [MenuGroup] = []
    @State private var loadingMenu = true

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                TravelTopBar(location: "Bursa, Türkiye", notificationCount: 0, onNotificationsTap: {})
                header
                quickTiles
                if loadingMenu {
                    ProgressView().padding()
                } else {
                    ForEach(menu) { group in
                        menuBlock(group)
                    }
                }
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 24)
        }
        .background(AppColors.bg.ignoresSafeArea())
        .refreshable { await refresh() }
        .task { await refresh() }
        .sheet(isPresented: $showAuth) { AuthFlowView() }
    }

    private var header: some View {
        VStack(spacing: 12) {
            Button {
                if auth.isLoggedIn { navPath.append(AppNavRoute.settings) }
                else { showAuth = true }
            } label: {
                Group {
                    if auth.isLoggedIn, let user = auth.user, !user.avatarUrl.isEmpty {
                        RemoteImage(url: user.avatarUrl, placeholder: "person.fill")
                    } else if auth.isLoggedIn, let user = auth.user {
                        Text(String(user.name.prefix(1)).uppercased())
                            .font(.largeTitle.weight(.bold))
                            .foregroundStyle(.white)
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                            .background(AppColors.accentDeep)
                    } else {
                        Text("👋").font(.largeTitle)
                    }
                }
                .frame(width: 96, height: 96)
                .clipShape(Circle())
            }
            .buttonStyle(.plain)

            Text(auth.isLoggedIn ? (auth.user?.displayName ?? "Üye") : "Giriş")
                .font(AppTypography.screenTitle)
            Text(auth.isLoggedIn ? "\(auth.user?.points ?? 0) puan · Bursa rehberi" : "Hesabınla devam et")
                .font(.subheadline)
                .foregroundStyle(AppColors.muted)

            if auth.isLoggedIn {
                Button("Profili düzenle") { navPath.append(AppNavRoute.settings) }
                    .buttonStyle(.bordered)
                Button("Çıkış yap", role: .destructive) {
                    Task { await auth.logout(); await refresh() }
                }
                .buttonStyle(.bordered)
                .tint(AppColors.coral)
            } else {
                Button(auth.loading ? "Yükleniyor…" : "Giriş") { showAuth = true }
                    .buttonStyle(.borderedProminent)
                    .tint(AppColors.nav)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 8)
    }

    private var quickTiles: some View {
        HStack(spacing: 10) {
            quickTile("Gez", icon: "mountain.2.fill", color: AppColors.accentDeep) {
                navPath.append(MenuDestination(link: MenuLink(label: "Gezilecek", path: "/gezilecek", category: nil)))
            }
            quickTile("Etkinlik", icon: "plus.circle.fill", color: AppColors.pink) {
                if auth.isLoggedIn { navPath.append(AppNavRoute.createEvent) }
                else { showAuth = true }
            }
            quickTile("Liderler", icon: "trophy.fill", color: AppColors.sky) {
                navPath.append(MenuDestination(link: MenuLink(label: "Liderler", path: "/liderler", category: nil)))
            }
            quickTile("Partner", icon: "person.3.fill", color: AppColors.amber) {
                navPath.append(MenuDestination(link: MenuLink(label: "Partner", path: "/arkadas-ara", category: nil)))
            }
        }
    }

    private func quickTile(_ label: String, icon: String, color: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 6) {
                Image(systemName: icon).font(.title3).foregroundStyle(color)
                Text(label).font(.caption.weight(.heavy)).foregroundStyle(AppColors.ink)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 18)
            .background(RoundedRectangle(cornerRadius: AppRadii.md).fill(AppColors.chipSelected))
        }
        .buttonStyle(.plain)
    }

    private func menuBlock(_ group: MenuGroup) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(group.title)
                .font(.subheadline.weight(.bold))
                .foregroundStyle(AppColors.muted)
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
            ForEach(group.items) { item in
                Button {
                    AppMenuPath.open(item, tabSelection: $tabSelection, navigationPath: $navPath)
                } label: {
                    HStack {
                        Text(item.label).foregroundStyle(AppColors.ink)
                        Spacer()
                        Image(systemName: "chevron.right").font(.caption).foregroundStyle(AppColors.muted)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 14)
                }
                .buttonStyle(.plain)
                if item.id != group.items.last?.id {
                    Divider().padding(.leading, 16)
                }
            }
        }
        .background(RoundedRectangle(cornerRadius: AppRadii.lg).fill(AppColors.card).shadow(color: .black.opacity(0.05), radius: 8, y: 3))
    }

    @MainActor
    private func refresh() async {
        loadingMenu = true
        defer { loadingMenu = false }
        if auth.isLoggedIn { await auth.refreshUser() }
        if let groups = try? await auth.apiClient().mobileMenu() {
            menu = groups
        }
    }
}
