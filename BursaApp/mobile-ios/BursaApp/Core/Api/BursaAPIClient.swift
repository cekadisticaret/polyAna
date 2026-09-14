import Foundation

/// Tüm ağ çağrıları actor içinde — UI thread'i asla bloklanmaz.
actor BursaAPIClient {
    private let session: URLSession
    private var token: String?

    init(session: URLSession = .shared, token: String? = nil) {
        self.session = session
        self.token = token
    }

    func setToken(_ value: String?) {
        token = value
    }

    func currentToken() -> String? { token }

    // MARK: - Feed

    func feed(tab: String = "recents", offset: Int = 0) async throws -> FeedResponse {
        var components = URLComponents(url: AppConfig.apiBase.appendingPathComponent("feed"), resolvingAgainstBaseURL: false)!
        components.queryItems = [
            URLQueryItem(name: "tab", value: tab),
            URLQueryItem(name: "offset", value: String(offset)),
            URLQueryItem(name: "limit", value: "12"),
        ]
        let json = try await getJSON(url: components.url!)
        return FeedResponse.decode(from: json)
    }

    func toggleLike(postId: Int) async throws -> LikeResult {
        let url = AppConfig.apiBase.appendingPathComponent("posts/\(postId)/like")
        let json = try await postJSON(url: url, body: [:])
        let liked = json["liked"] as? Bool ?? false
        let likes = (json["likes"] as? Int) ?? (json["likes"] as? NSNumber)?.intValue ?? 0
        return LikeResult(liked: liked, likes: likes)
    }

    func upcomingEvents() async throws -> [EventItem] {
        let url = AppConfig.apiBase.appendingPathComponent("events/upcoming")
        let json = try await getJSON(url: url)
        return (json["events"] as? [[String: Any]] ?? []).compactMap(EventItem.decode(from:))
    }

    // MARK: - Auth

    func login(email: String, password: String) async throws -> (AuthUser, String) {
        let url = AppConfig.apiBase.appendingPathComponent("auth/login")
        let json = try await postJSON(url: url, body: ["email": email, "password": password])
        guard let token = json["token"] as? String, !token.isEmpty else {
            throw APIError(message: "Oturum oluşturulamadı", statusCode: 500)
        }
        self.token = token
        let user = try decodeUser(json["user"])
        return (user, token)
    }

    func register(name: String, email: String, password: String) async throws -> (AuthUser, String) {
        let url = AppConfig.apiBase.appendingPathComponent("auth/register")
        let json = try await postJSON(
            url: url,
            body: ["name": name, "email": email, "password": password]
        )
        guard let token = json["token"] as? String, !token.isEmpty else {
            throw APIError(message: "Hesap oluşturuldu ama oturum açılamadı", statusCode: 500)
        }
        self.token = token
        let user = try decodeUser(json["user"])
        return (user, token)
    }

    func me() async throws -> AuthUser {
        let url = AppConfig.apiBase.appendingPathComponent("me")
        let json = try await getJSON(url: url)
        return try decodeUser(json["user"])
    }

    func forgotPassword(email: String) async throws -> String {
        let url = AppConfig.apiBase.appendingPathComponent("auth/forgot-password")
        let json = try await postJSON(url: url, body: ["email": email.trimmingCharacters(in: .whitespacesAndNewlines)])
        return json["message"] as? String ?? "E-posta gönderildi."
    }

    // MARK: - HTTP

    private func headers(includeJSON: Bool = true) -> [String: String] {
        var h = ["Accept": "application/json"]
        if includeJSON { h["Content-Type"] = "application/json" }
        if let token, !token.isEmpty { h["Authorization"] = "Bearer \(token)" }
        return h
    }

    func getJSON(url: URL) async throws -> [String: Any] {
        var req = URLRequest(url: url)
        req.httpMethod = "GET"
        headers().forEach { req.setValue($1, forHTTPHeaderField: $0) }
        return try await perform(req)
    }

    func postJSON(url: URL, body: [String: Any]) async throws -> [String: Any] {
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        headers().forEach { req.setValue($1, forHTTPHeaderField: $0) }
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        return try await perform(req)
    }

    func patchJSON(url: URL, body: [String: Any]) async throws -> [String: Any] {
        var req = URLRequest(url: url)
        req.httpMethod = "PATCH"
        headers().forEach { req.setValue($1, forHTTPHeaderField: $0) }
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        return try await perform(req)
    }

    func deleteJSON(url: URL) async throws -> [String: Any] {
        var req = URLRequest(url: url)
        req.httpMethod = "DELETE"
        headers().forEach { req.setValue($1, forHTTPHeaderField: $0) }
        return try await perform(req)
    }

    private func perform(_ request: URLRequest) async throws -> [String: Any] {
        let (data, response) = try await session.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw APIError(message: "Geçersiz yanıt", statusCode: status)
        }
        if status >= 400 || obj["ok"] as? Bool == false {
            let msg = obj["error"] as? String ?? "Hata"
            throw APIError(message: msg, statusCode: status)
        }
        return obj
    }

    func decodeUser(_ value: Any?) throws -> AuthUser {
        guard let dict = value as? [String: Any] else {
            throw APIError(message: "Kullanıcı verisi yok", statusCode: 500)
        }
        let data = try JSONSerialization.data(withJSONObject: dict)
        return try JSONDecoder().decode(AuthUser.self, from: data)
    }
}
