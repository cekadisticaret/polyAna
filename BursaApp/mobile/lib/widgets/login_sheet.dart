import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/auth/auth_store.dart';
import '../core/theme/app_theme.dart';

void showLoginSheet(BuildContext context, {VoidCallback? onSuccess}) {
  showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (_) => LoginSheet(onSuccess: onSuccess),
  );
}

void requireAuth(BuildContext context, VoidCallback onOk) {
  final auth = context.read<AuthStore>();
  if (auth.isLoggedIn) {
    onOk();
    return;
  }
  showLoginSheet(context, onSuccess: onOk);
}

class LoginSheet extends StatefulWidget {
  const LoginSheet({super.key, this.onSuccess});
  final VoidCallback? onSuccess;

  @override
  State<LoginSheet> createState() => _LoginSheetState();
}

class _LoginSheetState extends State<LoginSheet> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _name = TextEditingController();
  bool _register = false;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _name.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() => _error = null);
    final auth = context.read<AuthStore>();
    try {
      if (_register) {
        await auth.register(_name.text, _email.text, _password.text);
      } else {
        await auth.login(_email.text, _password.text);
      }
      if (!mounted) return;
      Navigator.pop(context);
      widget.onSuccess?.call();
    } catch (e) {
      setState(() => _error = e.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.viewInsetsOf(context).bottom;
    return Padding(
      padding: EdgeInsets.only(bottom: bottom),
      child: Container(
        margin: const EdgeInsets.all(12),
        padding: const EdgeInsets.fromLTRB(22, 16, 22, 26),
        decoration: BoxDecoration(
          color: AppColors.card,
          borderRadius: BorderRadius.circular(AppRadii.xl),
          boxShadow: AppShadows.soft,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Center(
              child: Container(
                width: 44,
                height: 5,
                decoration: BoxDecoration(
                  color: AppColors.muted.withValues(alpha: 0.25),
                  borderRadius: BorderRadius.circular(99),
                ),
              ),
            ),
            const SizedBox(height: 18),
            Text(
              _register ? 'BursaApp\'e katıl ✨' : 'Devam etmek için giriş yap',
              style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w900),
            ),
            const SizedBox(height: 6),
            const Text('Beğeni, yorum ve etkinlik için ücretsiz hesap.', style: TextStyle(color: AppColors.muted)),
            const SizedBox(height: 18),
            if (_register) TextField(controller: _name, decoration: const InputDecoration(labelText: 'Ad Soyad')),
            TextField(controller: _email, keyboardType: TextInputType.emailAddress, decoration: const InputDecoration(labelText: 'E-posta')),
            TextField(controller: _password, obscureText: true, decoration: const InputDecoration(labelText: 'Şifre')),
            if (_error != null) ...[
              const SizedBox(height: 8),
              Text(_error!, style: const TextStyle(color: AppColors.coral)),
            ],
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _submit,
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.nav,
                foregroundColor: AppColors.lime,
                padding: const EdgeInsets.symmetric(vertical: 15),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppRadii.md)),
              ),
              child: Text(_register ? 'Kayıt ol' : 'Giriş yap'),
            ),
            TextButton(
              onPressed: () => setState(() => _register = !_register),
              child: Text(_register ? 'Zaten hesabım var' : 'Hesabım yok, kayıt ol'),
            ),
          ],
        ),
      ),
    );
  }
}
