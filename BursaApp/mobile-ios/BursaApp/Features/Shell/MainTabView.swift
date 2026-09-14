import SwiftUI

enum ShellTab: Int, CaseIterable {
    case feed, explore, food, profile

    var title: String {
        switch self {
        case .feed: "Anasayfa"
        case .explore: "Yakınımda"
        case .food: "Lezzet & Gece"
        case .profile: "Profil"
        }
    }

    var icon: String {
        switch self {
        case .feed: "house.fill"
        case .explore: "map.fill"
        case .food: "fork.knife"
        case .profile: "person.fill"
        }
    }
}

struct MainTabView: View {
    @EnvironmentObject private var auth: AuthStore
    @StateObject private var shellNav = ShellNavigator()
    @State private var tab: ShellTab = .feed
    @State private var profilePath = NavigationPath()
    @State private var feedPath = NavigationPath()
    @State private var showAuth = false
    @State private var showCreateEvent = false
    @State private var showNotifications = false

    var body: some View {
        ZStack(alignment: .bottom) {
            AppColors.bg.ignoresSafeArea()

            VStack(spacing: 0) {
                ZStack {
                    FeedTabStack(path: $feedPath, isActive: tab == .feed, showAuth: $showAuth)
                    ExploreTabStack(isActive: tab == .explore)
                    FoodTabStack(isActive: tab == .food)
                    ProfileTabStack(path: $profilePath, tabSelection: $tab, isActive: tab == .profile, showAuth: $showAuth)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .safeAreaInset(edge: .bottom) {
                Color.clear.frame(height: 88)
            }

            FloatingTabBar(
                selection: $tab,
                userAvatar: auth.user?.avatarUrl,
                onCreateTap: {
                    if auth.isLoggedIn { showCreateEvent = true }
                    else { showAuth = true }
                }
            )
        }
        .sheet(isPresented: $showAuth) { AuthFlowView() }
        .sheet(isPresented: $showCreateEvent) { CreateEventView() }
        .sheet(isPresented: $showNotifications) {
            NavigationStack { NotificationsView() }
        }
        .environmentObject(shellNav)
        .onAppear { shellNav.onSelectTab = { tab = $0 } }
    }
}

private struct FeedTabStack: View {
    @Binding var path: NavigationPath
    let isActive: Bool
    @Binding var showAuth: Bool

    var body: some View {
        NavigationStack(path: $path) {
            FeedView(
                onSearchTap: { path.append(AppNavRoute.search("")) },
                onChipTap: { title, cat in path.append(AppNavRoute.category(title, cat)) },
                onHotels: { path.append(AppNavRoute.hotels) },
                onSeeAllEvents: { path.append(AppNavRoute.category("Etkinlikler", "event")) }
            )
            .padding(.top, isActive ? 8 : 0)
            .navigationDestination(for: AppNavRoute.self) { route in
                switch route {
                case .search(let q): PlaceSearchView(initialQuery: q)
                case .category(let title, let cat): CategoryPlacesView(title: title, category: cat)
                case .hotels: HotelsView()
                default: EmptyView()
                }
            }
            .navigationDestination(for: String.self) { slug in PlaceDetailView(slug: slug) }
        }
        .opacity(isActive ? 1 : 0)
        .allowsHitTesting(isActive)
    }
}

private struct ExploreTabStack: View {
    let isActive: Bool
    var body: some View {
        ExploreView()
            .opacity(isActive ? 1 : 0)
            .allowsHitTesting(isActive)
    }
}

private struct FoodTabStack: View {
    let isActive: Bool
    var body: some View {
        FoodView()
            .padding(.top, isActive ? 8 : 0)
            .opacity(isActive ? 1 : 0)
            .allowsHitTesting(isActive)
    }
}

private struct ProfileTabStack: View {
    @Binding var path: NavigationPath
    @Binding var tabSelection: ShellTab
    let isActive: Bool
    @Binding var showAuth: Bool

    var body: some View {
        NavigationStack(path: $path) {
            ProfileView(tabSelection: $tabSelection, navPath: $path)
                .navigationDestination(for: MenuDestination.self) { MenuDestinationView(link: $0.link) }
                .navigationDestination(for: String.self) { PlaceDetailView(slug: $0) }
                .navigationDestination(for: AppNavRoute.self) { route in
                    switch route {
                    case .settings: ProfileSettingsView()
                    case .createEvent: CreateEventView()
                    case .hotels: HotelsView()
                    case .category(let title, let cat): CategoryPlacesView(title: title, category: cat)
                    default: EmptyView()
                    }
                }
        }
        .opacity(isActive ? 1 : 0)
        .allowsHitTesting(isActive)
    }
}

struct FloatingTabBar: View {
    @Binding var selection: ShellTab
    var userAvatar: String?
    let onCreateTap: () -> Void

    var body: some View {
        HStack(spacing: 0) {
            tabIcon(.feed)
            tabIcon(.explore)
            createButton
            tabIcon(.food)
            profileIcon
        }
        .frame(height: 68)
        .padding(.horizontal, 8)
        .background(
            RoundedRectangle(cornerRadius: 26)
                .fill(Color.white)
                .shadow(color: Color(red: 23/255, green: 35/255, blue: 59/255).opacity(0.16), radius: 20, y: 8)
                .overlay(RoundedRectangle(cornerRadius: 26).stroke(AppColors.border.opacity(0.7), lineWidth: 1))
        )
        .padding(.horizontal, 16)
        .padding(.bottom, 10)
    }

    private func tabIcon(_ item: ShellTab) -> some View {
        Button { selection = item } label: {
            VStack(spacing: 4) {
                ZStack {
                    if selection == item {
                        RoundedRectangle(cornerRadius: 12)
                            .fill(AppColors.secondary)
                            .frame(width: 40, height: 32)
                    }
                    Image(systemName: item.icon)
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundColor(selection == item ? AppColors.primary : AppColors.muted)
                }
                Text(item.title)
                    .font(.system(size: 10, weight: selection == item ? .bold : .semibold))
                    .foregroundColor(selection == item ? AppColors.primary : AppColors.muted)
                    .lineLimit(1)
            }
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(.plain)
    }

    private var createButton: some View {
        Button(action: onCreateTap) {
            VStack(spacing: 4) {
                Image(systemName: "plus")
                    .font(.system(size: 22, weight: .bold))
                    .foregroundColor(AppColors.ink)
                    .frame(width: 56, height: 56)
                    .background(Circle().fill(AppColors.accent)
                        .shadow(color: AppColors.accent.opacity(0.45), radius: 12, y: 6))
                    .offset(y: -10)
                Text("Etkinlik")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(AppColors.muted)
                    .offset(y: -10)
            }
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(.plain)
    }

    private var profileIcon: some View {
        Button { selection = .profile } label: {
            VStack(spacing: 4) {
                ZStack {
                    if selection == .profile {
                        RoundedRectangle(cornerRadius: 12)
                            .fill(AppColors.secondary)
                            .frame(width: 40, height: 32)
                    }
                    Group {
                        if let userAvatar, !userAvatar.isEmpty {
                            RemoteImage(url: userAvatar, placeholder: "person.fill")
                                .frame(width: 24, height: 24)
                                .clipShape(Circle())
                        } else {
                            Image(systemName: "person.fill")
                                .font(.system(size: 17, weight: .semibold))
                                .foregroundColor(selection == .profile ? AppColors.primary : AppColors.muted)
                        }
                    }
                }
                Text(ShellTab.profile.title)
                    .font(.system(size: 10, weight: selection == .profile ? .bold : .semibold))
                    .foregroundColor(selection == .profile ? AppColors.primary : AppColors.muted)
            }
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(.plain)
    }
}
