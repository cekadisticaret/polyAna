import SwiftUI

// MARK: - Auth palette (FireVibe / AppColors)

private enum AuthPalette {
    static let sage = AppColors.bg
    static let forest = AppColors.nav
    static let hill = AppColors.nav
    static let hillDark = Color(red: 22 / 255, green: 55 / 255, blue: 41 / 255)
    static let balloonYellow = AppColors.chipSelected
    static let pinOrange = AppColors.chipSelected
    static let shoeYellow = AppColors.chipSelected
    static let mapYellow = AppColors.chipSelected
    static let mutedText = AppColors.muted
}

struct AuthFlowView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var auth: AuthStore
    @State private var path = NavigationPath()

    var body: some View {
        NavigationStack(path: $path) {
            AuthWelcomeView(
                onStart: { path.append(AuthRoute.login) },
                onRegister: { path.append(AuthRoute.register) },
                onClose: { dismiss() }
            )
            .navigationDestination(for: AuthRoute.self) { route in
                switch route {
                case .login:
                    AuthLoginView(
                        onSuccess: { dismiss() },
                        onForgot: { email in path.append(AuthRoute.forgot(email)) },
                        onRegister: { path.append(AuthRoute.register) }
                    )
                case .register:
                    AuthRegisterView(
                        onSuccess: { dismiss() },
                        onLogin: {
                            path.removeLast()
                            if path.isEmpty { path.append(AuthRoute.login) }
                        }
                    )
                case .forgot(let email):
                    AuthForgotPasswordView(initialEmail: email)
                }
            }
        }
    }
}

private enum AuthRoute: Hashable {
    case login
    case register
    case forgot(String)
}

// MARK: - Shared components

private struct AuthBackButton: View {
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: "chevron.left")
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(AuthPalette.forest)
                .frame(width: 44, height: 44, alignment: .leading)
        }
        .buttonStyle(.plain)
    }
}

private struct AuthTitleBadge: View {
    let line1: String
    let line2: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(line1)
                .font(.system(size: 36, weight: .black))
                .foregroundStyle(AuthPalette.forest)
            Text(line2)
                .font(.system(size: 36, weight: .black))
                .foregroundStyle(.white)
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(AuthPalette.forest)
                )
        }
    }
}

private struct AuthHeroCopy: View {
    let title: String
    let highlight: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            (
                Text(title)
                    .font(.system(size: 26, weight: .black))
                    .foregroundColor(AuthPalette.forest)
                + Text(highlight)
                    .font(.system(size: 26, weight: .black))
                    .foregroundColor(AuthPalette.forest)
                + Text(" 🏔")
                    .font(.system(size: 24))
            )
            .fixedSize(horizontal: false, vertical: true)

            Text(subtitle)
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(AuthPalette.mutedText.opacity(0.85))
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

private struct AuthPrimaryCapsuleButton: View {
    let title: String
    var loading = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 14) {
                ZStack {
                    Circle()
                        .fill(.white)
                        .frame(width: 38, height: 38)
                    Image(systemName: "play.fill")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(AuthPalette.forest)
                        .offset(x: 1)
                }
                Text(loading ? "\(title)…" : title)
                    .font(.system(size: 18, weight: .heavy))
                Spacer(minLength: 0)
                Image(systemName: "arrow.right")
                    .font(.system(size: 16, weight: .bold))
            }
            .foregroundStyle(.white)
            .padding(.leading, 10)
            .padding(.trailing, 22)
            .padding(.vertical, 16)
            .background(Capsule().fill(AuthPalette.forest))
        }
        .disabled(loading)
        .buttonStyle(.plain)
    }
}

private struct AuthFooterLink: View {
    let prefix: String
    let actionText: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            (
                Text(prefix + " ")
                    .foregroundColor(AuthPalette.mutedText.opacity(0.9))
                + Text(actionText)
                    .fontWeight(.black)
                    .foregroundColor(AuthPalette.forest)
            )
            .font(.system(size: 14, weight: .medium))
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(.plain)
        .padding(.top, 18)
    }
}

private struct AuthField: View {
    let label: String
    @Binding var text: String
    var keyboard: UIKeyboardType = .default
    var contentType: UITextContentType?
    var isSecure = false
    @Binding var reveal: Bool

    init(
        label: String,
        text: Binding<String>,
        keyboard: UIKeyboardType = .default,
        contentType: UITextContentType? = nil,
        isSecure: Bool = false,
        reveal: Binding<Bool> = .constant(false)
    ) {
        self.label = label
        _text = text
        self.keyboard = keyboard
        self.contentType = contentType
        self.isSecure = isSecure
        _reveal = reveal
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(label)
                .font(.caption.weight(.bold))
                .foregroundStyle(AuthPalette.mutedText.opacity(0.75))
            HStack {
                Group {
                    if isSecure && !reveal {
                        SecureField("", text: $text)
                    } else {
                        TextField("", text: $text)
                            .keyboardType(keyboard)
                            .textContentType(contentType)
                            .textInputAutocapitalization(keyboard == .emailAddress ? .never : .words)
                            .autocorrectionDisabled()
                    }
                }
                .font(.body.weight(.semibold))
                .foregroundStyle(AuthPalette.forest)
                if isSecure {
                    Button { reveal.toggle() } label: {
                        Image(systemName: reveal ? "eye.slash" : "eye")
                            .foregroundStyle(AuthPalette.mutedText.opacity(0.6))
                    }
                }
            }
            .padding(.horizontal, 18)
            .padding(.vertical, 16)
            .background(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .fill(Color.white.opacity(0.92))
            )
        }
    }
}

private struct AuthFormShell<Content: View>: View {
    let line1: String
    let line2: String
    let heroTitle: String
    let heroHighlight: String
    let heroSubtitle: String
    let onBack: () -> Void
    @ViewBuilder let content: Content

    var body: some View {
        ZStack {
            AuthPalette.sage.ignoresSafeArea()
            ScrollView(showsIndicators: false) {
                VStack(alignment: .leading, spacing: 0) {
                    AuthBackButton(action: onBack)
                    AuthTitleBadge(line1: line1, line2: line2)
                        .padding(.top, 4)
                    AuthTravelIllustration(compact: true)
                        .frame(height: 150)
                        .padding(.vertical, 12)
                    AuthHeroCopy(title: heroTitle, highlight: heroHighlight, subtitle: heroSubtitle)
                        .padding(.bottom, 22)
                    content
                }
                .padding(.horizontal, 24)
                .padding(.bottom, 28)
            }
        }
        .navigationBarHidden(true)
    }
}

// MARK: - Illustration

private struct AuthTravelIllustration: View {
    var compact = false

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            let h = geo.size.height
            let scale = compact ? min(w / 340, h / 150) : min(w / 340, h / 220)

            ZStack {
                cloud(at: CGPoint(x: w * 0.18, y: h * 0.12), scale: scale)
                cloud(at: CGPoint(x: w * 0.72, y: h * 0.08), scale: scale * 0.85)

                // Balloon
                ZStack {
                    Ellipse()
                        .fill(
                            LinearGradient(
                                colors: [AuthPalette.balloonYellow, AuthPalette.hill],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .frame(width: 74 * scale, height: 92 * scale)
                    VStack(spacing: 0) {
                        ForEach(0..<4, id: \.self) { i in
                            Rectangle()
                                .fill(i.isMultiple(of: 2) ? AuthPalette.balloonYellow : AuthPalette.hill)
                                .frame(width: 74 * scale, height: 8 * scale)
                        }
                    }
                    .clipShape(Ellipse())
                    .frame(width: 74 * scale, height: 92 * scale)
                    Rectangle()
                        .fill(AuthPalette.forest.opacity(0.5))
                        .frame(width: 2 * scale, height: 28 * scale)
                        .offset(y: 56 * scale)
                }
                .offset(x: w * 0.28, y: h * 0.02)

                // Airplane badge
                Circle()
                    .fill(AuthPalette.forest)
                    .frame(width: 44 * scale, height: 44 * scale)
                    .overlay {
                        Image(systemName: "airplane")
                            .font(.system(size: 18 * scale, weight: .bold))
                            .foregroundStyle(.white)
                            .rotationEffect(.degrees(-35))
                    }
                    .offset(x: w * 0.42, y: h * 0.14)

                // Hills
                AuthHillShape()
                    .fill(AuthPalette.hill)
                    .frame(height: h * 0.42)
                    .frame(maxHeight: .infinity, alignment: .bottom)
                AuthHillShape()
                    .fill(AuthPalette.hillDark)
                    .frame(height: h * 0.28)
                    .frame(maxWidth: .infinity, alignment: .trailing)
                    .frame(maxHeight: .infinity, alignment: .bottom)
                    .offset(x: w * 0.22)

                // Location pin
                VStack(spacing: 0) {
                    Image(systemName: "mappin.circle.fill")
                        .font(.system(size: 38 * scale))
                        .foregroundStyle(AuthPalette.pinOrange)
                        .background(Circle().fill(.white).padding(4 * scale))
                }
                .offset(x: w * 0.30, y: h * 0.36)

                // Hiker
                hiker(scale: scale)
                    .offset(x: -w * 0.06, y: h * 0.30)

                // Foreground leaves
                leaf(scale: scale)
                    .offset(x: w * 0.34, y: h * 0.58)
                leaf(scale: scale * 0.8)
                    .rotationEffect(.degrees(25))
                    .offset(x: w * 0.42, y: h * 0.62)
            }
        }
    }

    private func cloud(at point: CGPoint, scale: CGFloat) -> some View {
        ZStack {
            Circle().fill(.white.opacity(0.95)).frame(width: 34 * scale, height: 34 * scale)
            Circle().fill(.white.opacity(0.95)).frame(width: 26 * scale, height: 26 * scale).offset(x: 22 * scale)
            Circle().fill(.white.opacity(0.95)).frame(width: 20 * scale, height: 20 * scale).offset(x: -18 * scale, y: 6 * scale)
        }
        .position(point)
    }

    private func hiker(scale: CGFloat) -> some View {
        ZStack {
            // Legs
            RoundedRectangle(cornerRadius: 3 * scale)
                .fill(AuthPalette.forest)
                .frame(width: 10 * scale, height: 34 * scale)
                .offset(x: -8 * scale, y: 38 * scale)
            RoundedRectangle(cornerRadius: 3 * scale)
                .fill(AuthPalette.forest)
                .frame(width: 10 * scale, height: 34 * scale)
                .offset(x: 8 * scale, y: 38 * scale)
            // Shoes
            Capsule()
                .fill(AuthPalette.shoeYellow)
                .frame(width: 16 * scale, height: 8 * scale)
                .offset(x: -8 * scale, y: 56 * scale)
            Capsule()
                .fill(AuthPalette.shoeYellow)
                .frame(width: 16 * scale, height: 8 * scale)
                .offset(x: 8 * scale, y: 56 * scale)
            // Body
            RoundedRectangle(cornerRadius: 8 * scale)
                .fill(AuthPalette.hill)
                .frame(width: 38 * scale, height: 44 * scale)
                .offset(y: 8 * scale)
            // Backpack
            RoundedRectangle(cornerRadius: 6 * scale)
                .fill(AuthPalette.hillDark)
                .frame(width: 18 * scale, height: 28 * scale)
                .offset(x: -22 * scale, y: 6 * scale)
            // Map
            RoundedRectangle(cornerRadius: 4 * scale)
                .fill(AuthPalette.mapYellow)
                .frame(width: 28 * scale, height: 22 * scale)
                .overlay {
                    RoundedRectangle(cornerRadius: 2 * scale)
                        .stroke(AuthPalette.forest.opacity(0.25), lineWidth: 1)
                }
                .offset(x: 18 * scale, y: 4 * scale)
            // Head
            Circle()
                .fill(Color(red: 0.93, green: 0.82, blue: 0.72))
                .frame(width: 26 * scale, height: 26 * scale)
                .offset(y: -22 * scale)
            // Hat
            Capsule()
                .fill(AuthPalette.hill)
                .frame(width: 34 * scale, height: 12 * scale)
                .offset(y: -32 * scale)
        }
    }

    private func leaf(scale: CGFloat) -> some View {
        Ellipse()
            .fill(AuthPalette.forest.opacity(0.85))
            .frame(width: 34 * scale, height: 16 * scale)
    }
}

private struct AuthHillShape: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: 0, y: rect.maxY))
        path.addQuadCurve(
            to: CGPoint(x: rect.maxX, y: rect.maxY),
            control: CGPoint(x: rect.midX, y: rect.minY - rect.height * 0.15)
        )
        path.closeSubpath()
        return path
    }
}

// MARK: - Welcome

private struct AuthWelcomeView: View {
    let onStart: () -> Void
    let onRegister: () -> Void
    let onClose: () -> Void

    var body: some View {
        ZStack {
            AuthPalette.sage.ignoresSafeArea()
            VStack(alignment: .leading, spacing: 0) {
                AuthBackButton(action: onClose)

                AuthTitleBadge(line1: "Explore", line2: "Worldwide")
                    .padding(.top, 4)

                AuthTravelIllustration()
                    .frame(height: 240)
                    .padding(.top, 8)

                Spacer(minLength: 16)

                AuthHeroCopy(
                    title: "Discover The World With ",
                    highlight: "Travel Guider",
                    subtitle: "Explore destinations, cultures, and hidden gems with our travel guide"
                )

                AuthPrimaryCapsuleButton(title: "Let's get started!", action: onStart)
                    .padding(.top, 26)

                AuthFooterLink(prefix: "You do not have any account?", actionText: "Sign Up", action: onRegister)
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 20)
        }
        .navigationBarHidden(true)
    }
}

// MARK: - Login

struct AuthLoginView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var auth: AuthStore
    @State private var email = ""
    @State private var password = ""
    @State private var revealPassword = false
    @State private var error: String?
    let onSuccess: () -> Void
    let onForgot: (String) -> Void
    let onRegister: () -> Void

    var body: some View {
        AuthFormShell(
            line1: "Hoş",
            line2: "geldin",
            heroTitle: "Hesabınla ",
            heroHighlight: "devam et",
            heroSubtitle: "Beğeni, yorum ve etkinlik paylaşımı için giriş yap.",
            onBack: { dismiss() }
        ) {
            AuthField(label: "E-posta", text: $email, keyboard: .emailAddress, contentType: .emailAddress)
            AuthField(
                label: "Şifre",
                text: $password,
                contentType: .password,
                isSecure: true,
                reveal: $revealPassword
            )
            .padding(.top, 14)

            HStack {
                Spacer()
                Button("Şifremi unuttum") { onForgot(email) }
                    .font(.subheadline.weight(.heavy))
                    .foregroundStyle(AuthPalette.forest)
            }
            .padding(.top, 10)

            if let error {
                Text(error)
                    .font(.subheadline)
                    .foregroundStyle(AppColors.coral)
                    .padding(.top, 12)
            }

            AuthPrimaryCapsuleButton(title: "Giriş yap", loading: auth.loading) {
                Task { await submit() }
            }
            .padding(.top, 22)
            .disabled(email.isEmpty || password.isEmpty)

            AuthFooterLink(prefix: "Hesabın yok mu?", actionText: "Kayıt ol", action: onRegister)
        }
        .onAppear {
            if email.isEmpty, let saved = auth.savedEmail { email = saved }
        }
    }

    private func submit() async {
        error = nil
        do {
            try await auth.login(email: email, password: password)
            await auth.refreshUser()
            onSuccess()
        } catch {
            self.error = error.localizedDescription
        }
    }
}

// MARK: - Register

struct AuthRegisterView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var auth: AuthStore
    @State private var name = ""
    @State private var email = ""
    @State private var password = ""
    @State private var revealPassword = false
    @State private var error: String?
    let onSuccess: () -> Void
    let onLogin: () -> Void

    var body: some View {
        AuthFormShell(
            line1: "Hesap",
            line2: "oluştur",
            heroTitle: "BursaApp'e ",
            heroHighlight: "katıl",
            heroSubtitle: "Ücretsiz hesap — puan kazan, etkinlik paylaş.",
            onBack: { dismiss() }
        ) {
            AuthField(label: "Ad Soyad", text: $name, contentType: .name)
            AuthField(label: "E-posta", text: $email, keyboard: .emailAddress, contentType: .emailAddress)
                .padding(.top, 14)
            AuthField(
                label: "Şifre (en az 8 karakter)",
                text: $password,
                contentType: .newPassword,
                isSecure: true,
                reveal: $revealPassword
            )
            .padding(.top, 14)

            if let error {
                Text(error)
                    .font(.subheadline)
                    .foregroundStyle(AppColors.coral)
                    .padding(.top, 12)
            }

            AuthPrimaryCapsuleButton(title: "Kayıt ol", loading: auth.loading) {
                Task { await submit() }
            }
            .padding(.top, 22)
            .disabled(name.isEmpty || email.isEmpty || password.count < 8)

            AuthFooterLink(prefix: "Zaten hesabın var mı?", actionText: "Giriş yap", action: onLogin)
        }
        .onAppear {
            if email.isEmpty, let saved = auth.savedEmail { email = saved }
        }
    }

    private func submit() async {
        error = nil
        do {
            try await auth.register(name: name, email: email, password: password)
            await auth.refreshUser()
            onSuccess()
        } catch {
            self.error = error.localizedDescription
        }
    }
}

// MARK: - Forgot password

struct AuthForgotPasswordView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var auth: AuthStore
    @State private var email: String
    @State private var error: String?
    @State private var success: String?
    @State private var loading = false

    init(initialEmail: String) {
        _email = State(initialValue: initialEmail)
    }

    var body: some View {
        AuthFormShell(
            line1: "Şifre",
            line2: "sıfırla",
            heroTitle: "Yeni şifre ",
            heroHighlight: "e-posta ile",
            heroSubtitle: "Kayıtlı e-posta adresine geçici şifre gönderilir.",
            onBack: { dismiss() }
        ) {
            AuthField(label: "E-posta", text: $email, keyboard: .emailAddress, contentType: .emailAddress)

            if let error {
                Text(error)
                    .font(.subheadline)
                    .foregroundStyle(AppColors.coral)
                    .padding(.top, 12)
            }

            if let success {
                Text(success)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(AuthPalette.forest)
                    .padding(14)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(
                        RoundedRectangle(cornerRadius: 18, style: .continuous)
                            .fill(Color.white.opacity(0.75))
                    )
                    .padding(.top, 12)
            }

            AuthPrimaryCapsuleButton(title: "Yeni şifre gönder", loading: loading) {
                Task { await submit() }
            }
            .padding(.top, 22)
            .disabled(loading || email.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
    }

    private func submit() async {
        let trimmed = email.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.contains("@") else {
            error = "Geçerli bir e-posta gir"
            success = nil
            return
        }
        error = nil
        success = nil
        loading = true
        defer { loading = false }
        do {
            success = try await auth.apiClient().forgotPassword(email: trimmed)
        } catch {
            self.error = error.localizedDescription
        }
    }
}

typealias LoginView = AuthLoginView
typealias RegisterView = AuthRegisterView
typealias ForgotPasswordView = AuthForgotPasswordView
