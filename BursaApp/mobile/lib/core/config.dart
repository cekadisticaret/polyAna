class AppConfig {
  static const apiBase = String.fromEnvironment(
    'BURSAAPP_API',
    defaultValue: 'https://bursaapp.com/api/v1',
  );
  static const siteBase = String.fromEnvironment(
    'BURSAAPP_SITE',
    defaultValue: 'https://bursaapp.com',
  );
}
