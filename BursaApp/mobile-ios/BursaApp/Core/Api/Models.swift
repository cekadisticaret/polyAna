import Foundation

struct AuthUser: Codable, Sendable, Equatable {
    let id: Int
    let name: String
    let displayName: String
    let avatarUrl: String
    let points: Int
    let email: String
    let showFullName: Bool
    let emailVerified: Bool

    enum CodingKeys: String, CodingKey {
        case id, name, email
        case displayName = "display_name"
        case avatarUrl = "avatar_url"
        case points = "loyalty_points"
        case showFullName = "show_full_name"
        case emailVerified = "email_verified"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = JSONFlex.int(c, .id)
        name = (try? c.decode(String.self, forKey: .name)) ?? "Üye"
        displayName = (try? c.decode(String.self, forKey: .displayName)) ?? name
        avatarUrl = (try? c.decode(String.self, forKey: .avatarUrl)) ?? ""
        points = JSONFlex.int(c, .points)
        email = (try? c.decode(String.self, forKey: .email)) ?? ""
        showFullName = (try? c.decode(Bool.self, forKey: .showFullName)) ?? false
        emailVerified = (try? c.decode(Bool.self, forKey: .emailVerified)) ?? false
    }
}

struct FeedUser: Codable, Sendable {
    let name: String
    let avatarUrl: String
    let handle: String

    enum CodingKeys: String, CodingKey {
        case name, handle
        case avatarUrl = "avatar_url"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        name = (try? c.decode(String.self, forKey: .name)) ?? "Üye"
        avatarUrl = (try? c.decode(String.self, forKey: .avatarUrl)) ?? ""
        handle = (try? c.decode(String.self, forKey: .handle)) ?? "@uye"
    }
}

struct FeedItem: Identifiable, Sendable {
    let kind: String
    let id: Int
    let ago: String
    let user: FeedUser
    let body: String
    let images: [String]
    var likes: Int
    var liked: Bool
    let comments: Int
    let placeTitle: String?
    let placeSlug: String?
}

struct EventItem: Identifiable, Sendable {
    var id: String { slug.isEmpty ? title : slug }
    let title: String
    let slug: String
    let whenLabel: String
    let startsAtLabel: String
    let imgUrl: String
    let ilce: String
    let going: Int
}

struct FeedResponse: Sendable {
    let feed: [FeedItem]
    let events: [EventItem]
    let hasMore: Bool
}

struct LikeResult: Sendable {
    let liked: Bool
    let likes: Int
}

enum JSONFlex {
    static func int<K: CodingKey>(_ c: KeyedDecodingContainer<K>, _ key: K) -> Int {
        if let v = try? c.decode(Int.self, forKey: key) { return v }
        if let v = try? c.decode(Double.self, forKey: key) { return Int(v) }
        if let s = try? c.decode(String.self, forKey: key), let v = Int(s) { return v }
        return 0
    }
}

extension FeedItem {
    static func decode(from json: [String: Any]) -> FeedItem? {
        guard let id = json["id"] as? Int ?? (json["id"] as? NSNumber)?.intValue else { return nil }
        let place = json["place"] as? [String: Any]
        let userJson = json["user"] as? [String: Any] ?? [:]
        let user = FeedUser(
            name: userJson["name"] as? String ?? "Üye",
            avatarUrl: userJson["avatar_url"] as? String ?? "",
            handle: userJson["handle"] as? String ?? "@uye"
        )
        let images = (json["images"] as? [Any])?.compactMap { $0 as? String }.filter { !$0.isEmpty } ?? []
        return FeedItem(
            kind: json["kind"] as? String ?? "post",
            id: id,
            ago: json["ago"] as? String ?? "",
            user: user,
            body: json["body"] as? String ?? "",
            images: images,
            likes: (json["likes"] as? Int) ?? (json["likes"] as? NSNumber)?.intValue ?? 0,
            liked: json["liked"] as? Bool ?? false,
            comments: (json["comments"] as? Int) ?? (json["comments"] as? NSNumber)?.intValue ?? 0,
            placeTitle: place?["title"] as? String,
            placeSlug: place?["slug"] as? String
        )
    }
}

extension FeedUser {
    init(name: String, avatarUrl: String, handle: String) {
        self.name = name
        self.avatarUrl = avatarUrl
        self.handle = handle
    }
}

extension EventItem {
    static func decode(from json: [String: Any]) -> EventItem? {
        guard let title = json["title"] as? String else { return nil }
        return EventItem(
            title: title,
            slug: json["slug"] as? String ?? "",
            whenLabel: json["when_label"] as? String ?? "",
            startsAtLabel: json["starts_at_label"] as? String ?? "",
            imgUrl: json["img_url"] as? String ?? "",
            ilce: json["ilce"] as? String ?? "",
            going: (json["going"] as? Int) ?? (json["going"] as? NSNumber)?.intValue ?? 0
        )
    }
}

extension FeedResponse {
    static func decode(from json: [String: Any]) -> FeedResponse {
        let rawFeed = json["feed"] as? [[String: Any]] ?? []
        let feed = rawFeed
            .filter { ($0["kind"] as? String) != "buddy_promo" }
            .compactMap(FeedItem.decode(from:))
        let events = (json["events"] as? [[String: Any]] ?? []).compactMap(EventItem.decode(from:))
        return FeedResponse(feed: feed, events: events, hasMore: json["has_more"] as? Bool ?? false)
    }
}
