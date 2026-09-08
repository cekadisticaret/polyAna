import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:bursaapp_mobile/app/bursa_app.dart';
import 'package:bursaapp_mobile/core/auth/auth_store.dart';

void main() {
  testWidgets('BursaApp smoke', (tester) async {
    final auth = AuthStore();
    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: auth,
        child: const BursaApp(),
      ),
    );
    expect(find.text('BursaApp'), findsWidgets);
  });
}
