import Foundation
import SwiftUI

/// Oturum durumu yalnızca MainActor'da — SwiftUI güncellemeleri güvenli.
@MainActor
final class AuthStore: ObservableObject {
    static let tokenKey = "bursaapp_token"
    static let emailKey = "bursaapp_email"

    @Published private(set) var user: AuthUser?
    @Published private(set) var token: String?
    @Published private(set) var savedEmail: String?
    @Published private(set) var loading = false

    private let api = BursaAPIClient()

    var isLoggedIn: Bool { user != nil && !(token?.isEmpty ?? true) }

    func apiClient() -> BursaAPIClient { api }

    func loadSession() async {
        loading = true
        defer { loading = false }

        token = KeychainStore.read(Self.tokenKey)
        savedEmail = KeychainStore.read(Self.emailKey)

        guard let token, !token.isEmpty else { return }
        await api.setToken(token)

        do {
            user = try await api.me()
        } catch let err as APIError where err.statusCode == 401 || err.statusCode == 403 {
            await clearSession()
        } catch {
            // Ağ hatası — token saklı kalsın, sonraki yenilemede dene.
        }
    }

    func login(email: String, password: String) async throws {
        loading = true
        defer { loading = false }

        let trimmed = email.trimmingCharacters(in: .whitespacesAndNewlines)
        let (u, t) = try await api.login(email: trimmed, password: password)
        token = t
        user = u
        savedEmail = trimmed
        KeychainStore.write(Self.tokenKey, value: t)
        KeychainStore.write(Self.emailKey, value: trimmed)
    }

    func register(name: String, email: String, password: String) async throws {
        loading = true
        defer { loading = false }

        let trimmed = email.trimmingCharacters(in: .whitespacesAndNewlines)
        let (u, t) = try await api.register(
            name: name.trimmingCharacters(in: .whitespacesAndNewlines),
            email: trimmed,
            password: password
        )
        token = t
        user = u
        savedEmail = trimmed
        KeychainStore.write(Self.tokenKey, value: t)
        KeychainStore.write(Self.emailKey, value: trimmed)
    }

    func logout() async {
        await clearSession()
    }

    func refreshUser() async {
        guard isLoggedIn else { return }
        do {
            user = try await api.me()
        } catch {
            // ignore transient errors
        }
    }

    func updateProfile(name: String, showFullName: Bool) async throws {
        loading = true
        defer { loading = false }
        user = try await api.updateMe(action: "profile", name: name, showFullName: showFullName)
    }

    func updatePassword(current: String, newPassword: String, newPassword2: String) async throws {
        loading = true
        defer { loading = false }
        user = try await api.updateMe(
            action: "password",
            currentPassword: current,
            newPassword: newPassword,
            newPassword2: newPassword2
        )
    }

    func uploadAvatar(_ data: Data, filename: String) async throws {
        loading = true
        defer { loading = false }
        user = try await api.uploadAvatar(data: data, filename: filename)
    }

    private func clearSession() async {
        token = nil
        user = nil
        await api.setToken(nil)
        KeychainStore.delete(Self.tokenKey)
    }
}
