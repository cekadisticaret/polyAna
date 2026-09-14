import SwiftUI

@main
struct BursaAppApp: App {
    @StateObject private var auth = AuthStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(auth)
                .task {
                    await auth.loadSession()
                }
        }
    }
}

struct RootView: View {
    @EnvironmentObject private var auth: AuthStore

    var body: some View {
        Group {
            if auth.loading && auth.user == nil && auth.token == nil {
                LaunchLoadingView()
            } else {
                MainTabView()
            }
        }
        .animation(.easeInOut(duration: 0.2), value: auth.loading)
    }
}

private struct LaunchLoadingView: View {
    var body: some View {
        ZStack {
            AppColors.bg.ignoresSafeArea()
            ProgressView()
                .tint(AppColors.accentDeep)
        }
    }
}
