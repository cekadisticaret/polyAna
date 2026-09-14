import SwiftUI
import MapKit
import CoreLocation

@MainActor
final class ExploreLocation: NSObject, ObservableObject, CLLocationManagerDelegate {
    @Published var center = CLLocationCoordinate2D(latitude: 40.1885, longitude: 29.0610)
    private let manager = CLLocationManager()

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
    }

    func request() {
        manager.requestWhenInUseAuthorization()
        manager.requestLocation()
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let loc = locations.last else { return }
        Task { @MainActor in center = loc.coordinate }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {}
}

struct ExploreView: View {
    @EnvironmentObject private var auth: AuthStore
    @StateObject private var location = ExploreLocation()
    @State private var places: [PlaceItem] = []
    @State private var chip: TravelCategoryChip = .all
    @State private var path = NavigationPath()
    @State private var selectedPlace: PlaceItem?
    @State private var region = MKCoordinateRegion(
        center: CLLocationCoordinate2D(latitude: 40.1885, longitude: 29.0610),
        span: MKCoordinateSpan(latitudeDelta: 0.06, longitudeDelta: 0.06)
    )

    var body: some View {
        NavigationStack(path: $path) {
            ZStack(alignment: .top) {
                TravelMapView(
                    region: $region,
                    places: filtered,
                    selectedSlug: selectedPlace?.slug,
                    onSelect: { place in
                        withAnimation(.spring(response: 0.35, dampingFraction: 0.86)) {
                            selectedPlace = place
                        }
                    }
                )
                .ignoresSafeArea()

                VStack(spacing: 12) {
                    TravelTopBar(location: "Bursa haritası", notificationCount: 0, onNotificationsTap: {})
                        .padding(.horizontal, AppSpacing.screenX)
                        .padding(.top, 8)

                    TravelCategoryChips(selected: $chip)
                        .padding(.horizontal, AppSpacing.screenX)
                    Spacer()
                }

                VStack {
                    Spacer()
                    HStack {
                        Spacer()
                        VStack(spacing: 10) {
                            mapFab(icon: "square.2.layers.3d") {
                                region.span = MKCoordinateSpan(latitudeDelta: 0.03, longitudeDelta: 0.03)
                            }
                            mapFab(icon: "location.fill") { centerOnUser() }
                        }
                        .padding(.trailing, 16)
                        .padding(.bottom, selectedPlace == nil ? 120 : 280)
                    }
                }

                VStack {
                    Spacer()
                    if let place = selectedPlace {
                        TravelMapSheet(
                            place: place,
                            distance: lighthouseDistance(from: (location.center.latitude, location.center.longitude), place: place),
                            onJoin: { path.append(place.detailSlug) }
                        )
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                    }
                }
            }
            .background(AppColors.bg.ignoresSafeArea())
            .task { location.request(); await load() }
            .onChange(of: location.center.latitude) { _ in
                region = MKCoordinateRegion(center: location.center, span: region.span)
                Task { await load() }
            }
            .onChange(of: chip) { _ in
                if let sel = selectedPlace, !filtered.contains(where: { $0.slug == sel.slug }) {
                    selectedPlace = filtered.first
                }
            }
            .navigationDestination(for: String.self) { slug in PlaceDetailView(slug: slug) }
        }
    }

    private var filtered: [PlaceItem] {
        switch chip {
        case .all: return places
        case .visit: return places.filter { $0.category == "visit" }
        case .food: return places.filter { $0.category == "food" }
        case .event: return places.filter { ["event", "concert", "theater", "cinema", "fun"].contains($0.category) }
        }
    }

    private func centerOnUser() {
        region = MKCoordinateRegion(center: location.center, span: MKCoordinateSpan(latitudeDelta: 0.04, longitudeDelta: 0.04))
        location.request()
    }

    @MainActor
    private func load() async {
        do {
            places = try await auth.apiClient().nearby(lat: location.center.latitude, lng: location.center.longitude)
            if selectedPlace == nil { selectedPlace = filtered.first ?? places.first }
        } catch {
            places = []
        }
    }

    private func mapFab(icon: String, action: @escaping () -> Void) -> some View {
        TravelGhostButton(icon: icon, action: action)
    }
}

private struct TravelMapSheet: View {
    let place: PlaceItem
    let distance: String
    let onJoin: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Capsule().fill(Color.gray.opacity(0.35)).frame(width: 44, height: 5).frame(maxWidth: .infinity).padding(.top, 8)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    ForEach(0..<3, id: \.self) { _ in
                        RemoteImage(url: place.imgUrl, placeholder: "photo")
                            .frame(width: 140, height: 100)
                            .clipShape(RoundedRectangle(cornerRadius: AppRadii.sm))
                    }
                }
            }
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 4) {
                        Text(place.title).font(.headline.weight(.heavy)).foregroundStyle(AppColors.ink)
                        Image(systemName: "checkmark.seal.fill").font(.caption).foregroundStyle(AppColors.nav)
                    }
                    Text("\(travelJoinCount(seed: place.title.hashValue)) kişi keşfetti")
                        .font(.caption)
                        .foregroundStyle(AppColors.muted)
                }
                Spacer()
                Button(action: onJoin) {
                    Text("Katıl")
                        .font(.caption.weight(.heavy))
                        .foregroundStyle(AppColors.nav)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .background(Capsule().fill(AppColors.chipSelected))
                }
                .buttonStyle(.plain)
            }
            Text(place.blurb.isEmpty ? "\(place.title), Bursa'da popüler bir durak." : place.blurb)
                .font(.subheadline).foregroundStyle(AppColors.muted).lineLimit(3)
            Label(distance, systemImage: "mappin.and.ellipse")
                .font(.caption.weight(.semibold)).foregroundStyle(AppColors.muted)
        }
        .padding(.horizontal, 18)
        .padding(.bottom, 24)
        .background(
            RoundedRectangle(cornerRadius: AppRadii.xl, style: .continuous)
                .fill(Color.white)
                .shadow(color: .black.opacity(0.12), radius: 20, y: -4)
                .ignoresSafeArea(edges: .bottom)
        )
    }
}

private struct TravelMapView: UIViewRepresentable {
    @Binding var region: MKCoordinateRegion
    let places: [PlaceItem]
    let selectedSlug: String?
    let onSelect: (PlaceItem) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(onSelect: onSelect) }

    func makeUIView(context: Context) -> MKMapView {
        let map = MKMapView()
        map.delegate = context.coordinator
        map.showsUserLocation = true
        map.pointOfInterestFilter = .excludingAll
        return map
    }

    func updateUIView(_ mapView: MKMapView, context: Context) {
        context.coordinator.onSelect = onSelect
        context.coordinator.selectedSlug = selectedSlug
        if !mapView.region.center.isApproximatelyEqual(to: region.center) {
            mapView.setRegion(region, animated: true)
        }
        mapView.removeAnnotations(mapView.annotations.filter { !($0 is MKUserLocation) })
        for place in places {
            guard let lat = place.lat, let lng = place.lng else { continue }
            mapView.addAnnotation(TravelMapAnnotation(place: place, coordinate: CLLocationCoordinate2D(latitude: lat, longitude: lng)))
        }
    }

    final class Coordinator: NSObject, MKMapViewDelegate {
        var onSelect: (PlaceItem) -> Void
        var selectedSlug: String?
        init(onSelect: @escaping (PlaceItem) -> Void) { self.onSelect = onSelect }

        func mapView(_ mapView: MKMapView, viewFor annotation: MKAnnotation) -> MKAnnotationView? {
            guard let ann = annotation as? TravelMapAnnotation else { return nil }
            let id = "travelPin"
            let view = mapView.dequeueReusableAnnotationView(withIdentifier: id) as? TravelPinView
                ?? TravelPinView(annotation: annotation, reuseIdentifier: id)
            view.annotation = annotation
            view.configure(place: ann.place, selected: ann.place.slug == selectedSlug)
            return view
        }

        func mapView(_ mapView: MKMapView, didSelect view: MKAnnotationView) {
            guard let ann = view.annotation as? TravelMapAnnotation else { return }
            onSelect(ann.place)
            mapView.deselectAnnotation(ann, animated: false)
        }
    }
}

private final class TravelMapAnnotation: NSObject, MKAnnotation {
    let place: PlaceItem
    dynamic var coordinate: CLLocationCoordinate2D
    init(place: PlaceItem, coordinate: CLLocationCoordinate2D) { self.place = place; self.coordinate = coordinate }
}

private final class TravelPinView: MKAnnotationView {
    private let ring = UIView()
    private let circle = UIView()
    private let iconView = UIImageView()

    override init(annotation: MKAnnotation?, reuseIdentifier: String?) {
        super.init(annotation: annotation, reuseIdentifier: reuseIdentifier)
        frame = CGRect(x: 0, y: 0, width: 48, height: 48)
        centerOffset = CGPoint(x: 0, y: -20)
        canShowCallout = false
        ring.frame = CGRect(x: 2, y: 2, width: 44, height: 44)
        ring.layer.cornerRadius = 22
        ring.layer.borderWidth = 3
        addSubview(ring)
        circle.frame = CGRect(x: 6, y: 6, width: 36, height: 36)
        circle.backgroundColor = .white
        circle.layer.cornerRadius = 18
        circle.layer.shadowColor = UIColor.black.cgColor
        circle.layer.shadowOpacity = 0.12
        circle.layer.shadowRadius = 4
        addSubview(circle)
        iconView.frame = CGRect(x: 12, y: 12, width: 24, height: 24)
        iconView.contentMode = .scaleAspectFit
        addSubview(iconView)
    }

    required init?(coder: NSCoder) { nil }

    func configure(place: PlaceItem, selected: Bool) {
        let cfg = UIImage.SymbolConfiguration(pointSize: 14, weight: .semibold)
        iconView.image = UIImage(systemName: lighthouseCategoryIcon(place.category), withConfiguration: cfg)
        iconView.tintColor = UIColor(red: 27 / 255, green: 67 / 255, blue: 50 / 255, alpha: 1)
        ring.layer.borderColor = selected
            ? UIColor(red: 27 / 255, green: 67 / 255, blue: 50 / 255, alpha: 1).cgColor
            : UIColor.clear.cgColor
    }
}

func lighthouseDistance(from center: (lat: Double, lng: Double), place: PlaceItem) -> String {
    guard let lat = place.lat, let lng = place.lng else {
        return place.ilce.isEmpty ? "Bursa" : place.ilce
    }
    let r = 6371000.0
    let p1 = center.lat * .pi / 180, p2 = lat * .pi / 180
    let dp = (lat - center.lat) * .pi / 180
    let dl = (lng - center.lng) * .pi / 180
    let a = sin(dp / 2) * sin(dp / 2) + cos(p1) * cos(p2) * sin(dl / 2) * sin(dl / 2)
    let d = r * 2 * atan2(sqrt(a), sqrt(1 - a))
    if d >= 1000 { return String(format: "%.1f km uzakta", d / 1000) }
    return "\(Int(d)) m uzakta"
}

func lighthouseCategoryIcon(_ category: String) -> String {
    switch category {
    case "food": return "fork.knife"
    case "nightlife", "fun": return "wineglass.fill"
    case "event", "concert", "theater", "cinema": return "calendar"
    case "hotel": return "bed.double.fill"
    case "visit": return "camera.fill"
    default: return "mappin.circle.fill"
    }
}

private extension CLLocationCoordinate2D {
    func isApproximatelyEqual(to other: CLLocationCoordinate2D, epsilon: Double = 0.0001) -> Bool {
        abs(latitude - other.latitude) < epsilon && abs(longitude - other.longitude) < epsilon
    }
}
