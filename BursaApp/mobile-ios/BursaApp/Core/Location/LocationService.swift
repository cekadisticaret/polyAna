import CoreLocation
import Foundation

enum LocationService {
    static func requestLocation() async -> CLLocationCoordinate2D? {
        await withCheckedContinuation { cont in
            let manager = OneShotLocationManager { coord in
                cont.resume(returning: coord)
            }
            manager.start()
        }
    }
}

private final class OneShotLocationManager: NSObject, CLLocationManagerDelegate, @unchecked Sendable {
    private let manager = CLLocationManager()
    private let onResult: (CLLocationCoordinate2D?) -> Void
    private var done = false

    init(onResult: @escaping (CLLocationCoordinate2D?) -> Void) {
        self.onResult = onResult
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
    }

    func start() {
        manager.requestWhenInUseAuthorization()
        manager.requestLocation()
        Task { @MainActor [weak self] in
            try? await Task.sleep(nanoseconds: 8_000_000_000)
            self?.finish(nil)
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        finish(locations.last?.coordinate)
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        finish(nil)
    }

    private func finish(_ coord: CLLocationCoordinate2D?) {
        guard !done else { return }
        done = true
        onResult(coord)
    }
}
