import Foundation
import SwiftUI

enum FeedRow: Identifiable, Sendable {
    case post(FeedItem)
    case event(EventItem)

    var id: String {
        switch self {
        case .post(let p): "post-\(p.id)"
        case .event(let e): "event-\(e.slug)-\(e.title)"
        }
    }
}

@MainActor
final class FeedViewModel: ObservableObject {
    @Published private(set) var rows: [FeedRow] = []
    @Published private(set) var heroEvent: EventItem?
    @Published private(set) var events: [EventItem] = []
    @Published private(set) var leaders: [LeaderRow] = []
    @Published private(set) var locals: [PlaceItem] = []
    @Published private(set) var destinations: [PlaceItem] = []
    @Published private(set) var isLoading = false
    @Published private(set) var hasMore = false
    @Published var errorMessage: String?

    private var offset = 0
    private var loadTask: Task<Void, Never>?

    func load(auth: AuthStore, refresh: Bool) {
        loadTask?.cancel()
        loadTask = Task {
            if refresh {
                offset = 0
                if !Task.isCancelled { rows = [] }
            }
            isLoading = true
            errorMessage = nil
            defer { isLoading = false }

            do {
                let api = auth.apiClient()
                async let feedRes = api.feed(offset: offset)
                async let leadersRes = api.weeklyLeaders()
                async let foodRes = api.places(category: "food", limit: 12)
                async let visitRes = api.places(category: "visit", limit: 12)
                let res = try await feedRes
                guard !Task.isCancelled else { return }

                heroEvent = res.events.first
                events = res.events
                leaders = Array(((try? await leadersRes) ?? []).prefix(8))
                let food = (try? await foodRes) ?? []
                let visit = (try? await visitRes) ?? []
                destinations = visit + food
                locals = Array(food.prefix(6))
                hasMore = res.hasMore
                offset += res.feed.count

                var eventIdx = 0
                var newRows: [FeedRow] = refresh ? [] : rows
                for (i, post) in res.feed.enumerated() {
                    newRows.append(.post(post))
                    if (i + 1) % 2 == 0, eventIdx < res.events.count {
                        newRows.append(.event(res.events[eventIdx]))
                        eventIdx += 1
                    }
                }
                rows = newRows
            } catch is CancellationError {
                return
            } catch {
                if !Task.isCancelled {
                    errorMessage = error.localizedDescription
                }
            }
        }
    }

    func loadMore(auth: AuthStore) {
        guard hasMore, !isLoading else { return }
        load(auth: auth, refresh: false)
    }

    func toggleLike(postId: Int, auth: AuthStore) async {
        do {
            let result = try await auth.apiClient().toggleLike(postId: postId)
            if let idx = rows.firstIndex(where: {
                if case .post(let p) = $0 { return p.id == postId }
                return false
            }) {
                if case .post(var item) = rows[idx] {
                    item.liked = result.liked
                    item.likes = result.likes
                    rows[idx] = .post(item)
                }
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    deinit {
        loadTask?.cancel()
    }
}
