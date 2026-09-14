import SwiftUI

struct RemoteImage: View {
    let url: String
    var placeholder: String = "photo"

    var body: some View {
        Group {
            if let u = resolvedURL {
                AsyncImage(url: u) { phase in
                    switch phase {
                    case .success(let image):
                        image.resizable().scaledToFill()
                    case .failure:
                        placeholderView
                    case .empty:
                        ProgressView()
                    @unknown default:
                        placeholderView
                    }
                }
            } else {
                placeholderView
            }
        }
        .background(AppColors.bgSoft)
    }

    private var resolvedURL: URL? {
        let u = url.trimmingCharacters(in: .whitespacesAndNewlines)
        if u.isEmpty { return nil }
        if u.hasPrefix("http") { return URL(string: u) }
        return URL(string: u, relativeTo: AppConfig.siteBase)?.absoluteURL
    }

    private var placeholderView: some View {
        Image(systemName: placeholder)
            .font(.title2)
            .foregroundStyle(AppColors.muted.opacity(0.5))
            .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
