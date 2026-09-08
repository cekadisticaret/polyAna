import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../api/bursa_api.dart';
import '../api/models.dart';

class AuthStore extends ChangeNotifier {
  AuthStore();

  static const _tokenKey = 'bursaapp_token';
  final _storage = const FlutterSecureStorage();
  BursaApi? _api;
  AuthUser? user;
  String? token;
  bool loading = false;

  BursaApi get api {
    _api ??= BursaApi(token: token);
    _api!.token = token;
    return _api!;
  }

  bool get isLoggedIn => token != null && token!.isNotEmpty;

  Future<void> load() async {
    token = await _storage.read(key: _tokenKey);
    if (token != null && token!.isNotEmpty) {
      try {
        user = await api.me();
      } catch (_) {
        await logout();
      }
    }
    notifyListeners();
  }

  Future<void> login(String email, String password) async {
    loading = true;
    notifyListeners();
    try {
      user = await api.login(email.trim(), password);
      token = api.token;
      await _storage.write(key: _tokenKey, value: token);
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<void> register(String name, String email, String password) async {
    loading = true;
    notifyListeners();
    try {
      user = await api.register(name.trim(), email.trim(), password);
      token = api.token;
      await _storage.write(key: _tokenKey, value: token);
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<void> logout() async {
    token = null;
    user = null;
    _api = null;
    await _storage.delete(key: _tokenKey);
    notifyListeners();
  }
}
