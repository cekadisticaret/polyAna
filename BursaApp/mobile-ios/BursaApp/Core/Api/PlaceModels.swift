import Foundation

struct PlaceItem: Identifiable, Sendable, Hashable {
    var id: String { slug.isEmpty ? title : slug }
    let title: String
    let slug: String
    let category: String
    let ilce: String
    let blurb: String
    let imgUrl: String
    let lat: Double?
    let lng: Double?
    let subcategory: String
    let whenLabel: String
    let venueName: String
    let categoryLabel: String
    let path: String
    var isFav: Bool

    var detailSlug: String {
        let s = slug.trimmingCharacters(in: .whitespacesAndNewlines)
        if !s.isEmpty { return s }
        return Self.slugFromPath(path)
    }

    static func slugFromPath(_ path: String) -> String {
        let p = path.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !p.isEmpty else { return "" }
        let segment = p.split(separator: "/").last.map(String.init) ?? ""
        if segment.hasPrefix("bursa-") { return String(segment.dropFirst(6)) }
        return segment
    }

    static func decode(from json: [String: Any]) -> PlaceItem? {
        let path = json["path"] as? String ?? ""
        let slugRaw = (json["slug"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let slug = slugRaw.isEmpty ? slugFromPath(path) : slugRaw
        let title = json["title"] as? String ?? json["name"] as? String ?? ""
        guard !slug.isEmpty || !title.isEmpty else { return nil }
        return PlaceItem(
            title: title,
            slug: slug,
            category: json["category"] as? String ?? "",
            ilce: json["ilce"] as? String ?? "",
            blurb: json["blurb"] as? String ?? "",
            imgUrl: json["img_url"] as? String ?? "",
            lat: JSONValue.double(json["lat"]),
            lng: JSONValue.double(json["lng"]),
            subcategory: json["subcategory"] as? String ?? json["subcategory_label"] as? String ?? "",
            whenLabel: json["when"] as? String ?? json["when_long"] as? String ?? "",
            venueName: json["venue_name"] as? String ?? "",
            categoryLabel: json["category_label"] as? String ?? "",
            path: path,
            isFav: json["is_fav"] as? Bool ?? false
        )
    }

    static func list(from json: [String: Any], key: String = "places") -> [PlaceItem] {
        (json[key] as? [[String: Any]] ?? []).compactMap(decode(from:))
    }

    static func fromGroups(_ json: [String: Any]) -> [PlaceItem] {
        let groups = json["groups"] as? [[String: Any]] ?? []
        var all: [PlaceItem] = []
        for g in groups { all.append(contentsOf: list(from: g)) }
        if all.isEmpty { all = list(from: json) }
        return all
    }
}

struct MenuLink: Identifiable, Sendable, Hashable {
    var id: String { path + label }
    let label: String
    let path: String
    let category: String?
    static func decode(from json: [String: Any]) -> MenuLink {
        MenuLink(label: json["label"] as? String ?? "", path: json["path"] as? String ?? "", category: json["category"] as? String)
    }
}

struct MenuGroup: Identifiable, Sendable {
    var id: String { title }
    let title: String
    let icon: String
    let items: [MenuLink]
    static func decodeList(from json: [String: Any]) -> [MenuGroup] {
        (json["groups"] as? [[String: Any]] ?? []).compactMap { row in
            guard let title = row["title"] as? String else { return nil }
            return MenuGroup(title: title, icon: row["icon"] as? String ?? "", items: (row["items"] as? [[String: Any]] ?? []).map(MenuLink.decode(from:)))
        }
    }
}

struct LeaderRow: Identifiable, Sendable {
    var id: String { "\(rank)-\(name)" }
    let rank: Int
    let name: String
    let points: Int
    let avatarUrl: String
    static func decode(from json: [String: Any]) -> LeaderRow? {
        let u = json["user"] as? [String: Any] ?? json
        let name = u["name"] as? String ?? json["name"] as? String
        guard let name, !name.isEmpty else { return nil }
        return LeaderRow(
            rank: JSONValue.int(json["rank"]),
            name: name,
            points: JSONValue.int(u["points"] ?? u["loyalty_points"]),
            avatarUrl: u["avatar_url"] as? String ?? ""
        )
    }
}

struct ActivityType: Identifiable, Sendable {
    var id: String { key }
    let key: String
    let label: String
    let emoji: String
    static func decode(from json: [String: Any]) -> ActivityType {
        ActivityType(key: json["key"] as? String ?? "other", label: json["label"] as? String ?? "", emoji: json["emoji"] as? String ?? "✨")
    }
}

struct ActivitySeek: Identifiable, Sendable {
    let id: Int
    let activityType: String
    let activityLabel: String
    let emoji: String
    let title: String
    let host: String
    let ilce: String
    let venue: String
    let timeLabel: String
    let note: String
    let pointsMin: Int
    let slotsNeeded: Int
    let spotsLeft: Int
    let joined: Bool
    let pending: Bool
    let isMine: Bool
    let contactHint: String

    static func decode(from json: [String: Any]) -> ActivitySeek {
        ActivitySeek(
            id: JSONValue.int(json["id"]),
            activityType: json["activity_type"] as? String ?? json["type"] as? String ?? "other",
            activityLabel: json["activity_label"] as? String ?? "",
            emoji: json["emoji"] as? String ?? "✨",
            title: json["title"] as? String ?? json["host"] as? String ?? "",
            host: json["host"] as? String ?? "",
            ilce: json["ilce"] as? String ?? "",
            venue: json["venue"] as? String ?? "",
            timeLabel: json["time_label"] as? String ?? "",
            note: json["note"] as? String ?? "",
            pointsMin: JSONValue.int(json["points_min"]),
            slotsNeeded: JSONValue.int(json["slots_needed"], default: 1),
            spotsLeft: JSONValue.int(json["spots_left"], default: 1),
            joined: json["joined"] as? Bool ?? false,
            pending: json["pending"] as? Bool ?? false,
            isMine: json["is_mine"] as? Bool ?? false,
            contactHint: json["contact_hint"] as? String ?? ""
        )
    }
}

enum JSONValue {
    static func int(_ value: Any?, default defaultValue: Int = 0) -> Int {
        if let v = value as? Int { return v }
        if let v = value as? NSNumber { return v.intValue }
        if let s = value as? String, let v = Int(s) { return v }
        return defaultValue
    }
    static func double(_ value: Any?) -> Double? {
        if let v = value as? Double { return v }
        if let v = value as? NSNumber { return v.doubleValue }
        if let s = value as? String { return Double(s) }
        return nil
    }

    static func string(_ value: Any?, default defaultValue: String = "") -> String {
        if let v = value as? String { return v }
        if let v = value as? Int { return String(v) }
        if let v = value as? NSNumber { return v.stringValue }
        if let v = value as? Double { return String(v) }
        return defaultValue
    }
}

enum MobileEndpoint: String, Sendable { case vets, dentists, doctors, hospitals, hotels }

enum AppNavRoute: Hashable {
    case menu(MenuLink)
    case place(String)
    case news(String)
    case pharmacy(String)
    case settings
    case createEvent
    case search(String)
    case okey
    case category(String, String)
    case hotels
}
