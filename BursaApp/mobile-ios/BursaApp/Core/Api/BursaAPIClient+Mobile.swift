import Foundation

extension BursaAPIClient {
    func places(
        category: String? = nil, sub: String? = nil, spec: String? = nil,
        q: String? = nil, limit: Int = 24, offset: Int = 0
    ) async throws -> [PlaceItem] {
        var items: [URLQueryItem] = [
            URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "offset", value: String(offset)),
        ]
        if let category, !category.isEmpty { items.append(URLQueryItem(name: "category", value: category)) }
        if let sub, !sub.isEmpty { items.append(URLQueryItem(name: "sub", value: sub)) }
        if let spec, !spec.isEmpty { items.append(URLQueryItem(name: "spec", value: spec)) }
        if let q, !q.isEmpty { items.append(URLQueryItem(name: "q", value: q)) }
        var components = URLComponents(url: AppConfig.apiBase.appendingPathComponent("places"), resolvingAgainstBaseURL: false)!
        components.queryItems = items
        return PlaceItem.list(from: try await getJSON(url: components.url!))
    }

    func placeDetail(slug: String) async throws -> [String: Any] {
        let s = slug.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !s.isEmpty else { throw APIError(message: "Geçersiz slug", statusCode: 400) }
        let json = try await getJSON(url: AppConfig.apiBase.appendingPathComponent("places/\(s)"))
        guard let place = json["place"] as? [String: Any] else {
            throw APIError(message: "Mekan bulunamadı", statusCode: 404)
        }
        return place
    }

    func togglePlaceFavorite(slug: String) async throws -> (Bool, Int) {
        let s = slug.trimmingCharacters(in: .whitespacesAndNewlines)
        let json = try await postJSON(url: AppConfig.apiBase.appendingPathComponent("places/\(s)/favorite"), body: [:])
        return (json["is_fav"] as? Bool ?? false, JSONValue.int(json["fav_count"]))
    }

    func nearby(lat: Double, lng: Double, radius: Int = 1200) async throws -> [PlaceItem] {
        var components = URLComponents(url: AppConfig.apiBase.appendingPathComponent("discover/nearby"), resolvingAgainstBaseURL: false)!
        components.queryItems = [
            URLQueryItem(name: "lat", value: String(lat)),
            URLQueryItem(name: "lng", value: String(lng)),
            URLQueryItem(name: "r", value: String(radius)),
        ]
        return PlaceItem.list(from: try await getJSON(url: components.url!))
    }

    func mapRoute(fromLat: Double, fromLng: Double, toLat: Double, toLng: Double, profile: String = "foot") async throws -> MapRouteResult {
        var components = URLComponents(url: AppConfig.siteBase.appendingPathComponent("api/route"), resolvingAgainstBaseURL: false)!
        components.queryItems = [
            URLQueryItem(name: "from_lat", value: String(fromLat)),
            URLQueryItem(name: "from_lng", value: String(fromLng)),
            URLQueryItem(name: "to_lat", value: String(toLat)),
            URLQueryItem(name: "to_lng", value: String(toLng)),
            URLQueryItem(name: "profile", value: profile),
        ]
        let json = try await getJSON(url: components.url!)
        let raw = json["coordinates"] as? [[Any]] ?? []
        var points: [CLLocationCoordinate2D] = []
        for item in raw where item.count >= 2 {
            if let lat = (item[0] as? NSNumber)?.doubleValue ?? Double("\(item[0])"),
               let lng = (item[1] as? NSNumber)?.doubleValue ?? Double("\(item[1])") {
                points.append(CLLocationCoordinate2D(latitude: lat, longitude: lng))
            }
        }
        guard points.count >= 2 else { throw APIError(message: "Rota bulunamadı", statusCode: 404) }
        return MapRouteResult(
            points: points,
            distanceM: JSONValue.double(json["distance_m"]),
            durationS: JSONValue.double(json["duration_s"])
        )
    }

    func mobileMenu() async throws -> [MenuGroup] {
        MenuGroup.decodeList(from: try await getJSON(url: AppConfig.apiBase.appendingPathComponent("mobile/menu")))
    }

    func weeklyLeaders() async throws -> [LeaderRow] {
        let json = try await getJSON(url: AppConfig.apiBase.appendingPathComponent("leaders/weekly"))
        return (json["leaders"] as? [[String: Any]] ?? []).compactMap(LeaderRow.decode(from:))
    }

    func updateMe(action: String, name: String? = nil, showFullName: Bool? = nil,
                  currentPassword: String? = nil, newPassword: String? = nil, newPassword2: String? = nil) async throws -> AuthUser {
        var body: [String: Any] = ["action": action]
        if let name { body["name"] = name }
        if let showFullName { body["show_full_name"] = showFullName }
        if let currentPassword { body["current_password"] = currentPassword }
        if let newPassword { body["new_password"] = newPassword }
        if let newPassword2 { body["new_password2"] = newPassword2 }
        let json = try await patchJSON(url: AppConfig.apiBase.appendingPathComponent("me"), body: body)
        return try decodeUser(json["user"])
    }

    func uploadAvatar(data: Data, filename: String) async throws -> AuthUser {
        let boundary = "Boundary-\(UUID().uuidString)"
        var req = URLRequest(url: AppConfig.apiBase.appendingPathComponent("me/avatar"))
        req.httpMethod = "POST"
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        if let token = currentToken(), !token.isEmpty {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        var body = Data()
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"avatar\"; filename=\"\(filename)\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
        body.append(data)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        req.httpBody = body
        let json = try await performMultipart(req)
        return try decodeUser(json["user"])
    }

    private func performMultipart(_ request: URLRequest) async throws -> [String: Any] {
        let (data, response) = try await URLSession.shared.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw APIError(message: "Geçersiz yanıt", statusCode: status)
        }
        if status >= 400 || obj["ok"] as? Bool == false {
            throw APIError(message: obj["error"] as? String ?? "Hata", statusCode: status)
        }
        return obj
    }

    func createEvent(_ payload: [String: Any]) async throws {
        _ = try await postJSON(url: AppConfig.apiBase.appendingPathComponent("places"), body: payload)
    }

    func activityTypes() async throws -> [ActivityType] {
        let json = try await getJSON(url: AppConfig.apiBase.appendingPathComponent("activities/types"))
        return (json["types"] as? [[String: Any]] ?? []).map(ActivityType.decode(from:))
    }

    func activitySeeking(type: String? = nil) async throws -> [ActivitySeek] {
        var components = URLComponents(url: AppConfig.apiBase.appendingPathComponent("activities/seeking"), resolvingAgainstBaseURL: false)!
        if let type, !type.isEmpty { components.queryItems = [URLQueryItem(name: "type", value: type)] }
        let json = try await getJSON(url: components.url!)
        return (json["seeking"] as? [[String: Any]] ?? []).map(ActivitySeek.decode(from:))
    }

    func createActivitySeek(_ payload: [String: Any]) async throws {
        _ = try await postJSON(url: AppConfig.apiBase.appendingPathComponent("activities/seeking"), body: payload)
    }

    func joinActivitySeek(id: Int) async throws {
        _ = try await postJSON(url: AppConfig.apiBase.appendingPathComponent("activities/seeking/\(id)/join"), body: [:])
    }

    func leaveActivitySeek(id: Int) async throws {
        _ = try await deleteJSON(url: AppConfig.apiBase.appendingPathComponent("activities/seeking/\(id)/join"))
    }

    func mobileGET(_ path: String, query: [String: String] = [:]) async throws -> [String: Any] {
        var components = URLComponents(url: AppConfig.apiBase.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty { components.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) } }
        return try await getJSON(url: components.url!)
    }

    func visitPlaces(page: Int = 1, q: String = "", ilce: String = "", sort: String = "featured",
                     kinds: [String] = [], fees: [String] = [], tags: [String] = []) async throws -> [String: Any] {
        var parts = ["page=\(page)"]
        if !q.isEmpty { parts.append("q=\(q.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? q)") }
        if !ilce.isEmpty { parts.append("ilce=\(ilce.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ilce)") }
        if !sort.isEmpty { parts.append("sort=\(sort)") }
        for k in kinds where !k.isEmpty { parts.append("kind=\(k.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? k)") }
        for f in fees where !f.isEmpty { parts.append("fee=\(f)") }
        for t in tags where !t.isEmpty { parts.append("tag=\(t)") }
        let urlStr = AppConfig.apiBase.appendingPathComponent("mobile/visit").absoluteString + "?" + parts.joined(separator: "&")
        return try await getJSON(url: URL(string: urlStr)!)
    }

    func vets(tab: String = "hepsi", ilce: String? = nil, sub: String? = nil, lat: Double? = nil, lng: Double? = nil) async throws -> [String: Any] {
        var q: [String: String] = ["tab": tab]
        if let ilce, !ilce.isEmpty { q["ilce"] = ilce }
        if let sub, !sub.isEmpty { q["sub"] = sub }
        if let lat { q["lat"] = String(lat) }
        if let lng { q["lng"] = String(lng) }
        return try await mobileGET("mobile/vets", query: q)
    }

    func dentists(ilce: String? = nil, band: String? = nil) async throws -> [String: Any] {
        var q: [String: String] = [:]
        if let ilce, !ilce.isEmpty { q["ilce"] = ilce }
        if let band, !band.isEmpty { q["band"] = band }
        return try await mobileGET("mobile/dentists", query: q)
    }

    func doctors(ilce: String? = nil, spec: String? = nil) async throws -> [String: Any] {
        var q: [String: String] = [:]
        if let ilce, !ilce.isEmpty { q["ilce"] = ilce }
        if let spec, !spec.isEmpty { q["spec"] = spec }
        return try await mobileGET("mobile/doctors", query: q)
    }

    func hospitals(ilce: String? = nil, band: String? = nil) async throws -> [String: Any] {
        var q: [String: String] = [:]
        if let ilce, !ilce.isEmpty { q["ilce"] = ilce }
        if let band, !band.isEmpty { q["band"] = band }
        return try await mobileGET("mobile/hospitals", query: q)
    }

    func hotels(q: String? = nil, ilce: String? = nil, sub: String? = nil, band: String? = nil,
                sort: String? = nil, price: String? = nil) async throws -> [String: Any] {
        var query: [String: String] = [:]
        if let q, !q.isEmpty { query["q"] = q }
        if let ilce, !ilce.isEmpty { query["ilce"] = ilce }
        if let sub, !sub.isEmpty { query["sub"] = sub }
        if let band, !band.isEmpty { query["band"] = band }
        if let sort, !sort.isEmpty { query["sort"] = sort }
        if let price, !price.isEmpty { query["price"] = price }
        return try await mobileGET("mobile/hotels", query: query)
    }

    func nobetciEczaneler(ilce: String? = nil, lat: Double? = nil, lng: Double? = nil) async throws -> [String: Any] {
        var q: [String: String] = [:]
        if let ilce, !ilce.isEmpty { q["ilce"] = ilce }
        if let lat { q["lat"] = String(lat) }
        if let lng { q["lng"] = String(lng) }
        return try await mobileGET("mobile/nobetci-eczaneler", query: q)
    }

    func nobetciEczaneDetail(slug: String) async throws -> [String: Any] {
        try await getJSON(url: AppConfig.apiBase.appendingPathComponent("mobile/nobetci-eczaneler/\(slug)"))
    }

    func bursaNews(page: Int = 1, topic: String? = nil, q: String? = nil) async throws -> [String: Any] {
        var qd: [String: String] = ["page": String(page), "limit": "24"]
        if let topic, !topic.isEmpty { qd["konu"] = topic }
        if let q, !q.isEmpty { qd["q"] = q }
        return try await mobileGET("mobile/news", query: qd)
    }

    func bursaNewsDetail(slug: String) async throws -> [String: Any] {
        try await getJSON(url: AppConfig.apiBase.appendingPathComponent("mobile/news/\(slug)"))
    }

    func bursasporFeed() async throws -> [String: Any] {
        try await mobileGET("mobile/bursaspor")
    }

    func teleferikInfo() async throws -> [String: Any] {
        try await mobileGET("mobile/teleferik")
    }

    func utilitiesInfo() async throws -> [String: Any] {
        try await mobileGET("mobile/utilities")
    }

    func weekend() async throws -> [String: Any] {
        try await getJSON(url: AppConfig.apiBase.appendingPathComponent("discover/weekend"))
    }

    func planDayRoute(people: Int = 2, budgetTl: Int = 0, transport: String = "bus") async throws -> [String: Any] {
        var q: [String: String] = [
            "people": String(max(1, min(8, people))),
            "transport": transport,
        ]
        if budgetTl > 0 { q["budget"] = String(budgetTl) }
        return try await mobileGET("route", query: q)
    }

    func mobilePlaces(_ endpoint: MobileEndpoint, ilce: String? = nil, tab: String? = nil,
                      band: String? = nil, spec: String? = nil, q: String? = nil) async throws -> [String: Any] {
        switch endpoint {
        case .vets: return try await vets(tab: tab ?? "hepsi", ilce: ilce)
        case .dentists: return try await dentists(ilce: ilce, band: band)
        case .doctors: return try await doctors(ilce: ilce, spec: spec)
        case .hospitals: return try await hospitals(ilce: ilce, band: band)
        case .hotels: return try await hotels(q: q, ilce: ilce, band: band)
        }
    }

    func okeySeeking() async throws -> [ActivitySeek] {
        try await activitySeeking(type: "okey")
    }
}

import CoreLocation

struct MapRouteResult: Sendable {
    let points: [CLLocationCoordinate2D]
    let distanceM: Double?
    let durationS: Double?
}
