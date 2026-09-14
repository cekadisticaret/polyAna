import Foundation

enum AppConfig {
    static let apiBase = URL(string: ProcessInfo.processInfo.environment["BURSAAPP_API"] ?? "https://bursaapp.com/api/v1")!
    static let siteBase = URL(string: ProcessInfo.processInfo.environment["BURSAAPP_SITE"] ?? "https://bursaapp.com")!
}
