import Foundation

struct APIError: LocalizedError, Sendable {
    let message: String
    let statusCode: Int

    var errorDescription: String? { message }
}
