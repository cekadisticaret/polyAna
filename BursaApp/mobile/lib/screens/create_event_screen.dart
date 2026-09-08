import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/auth/auth_store.dart';
import '../core/theme/app_theme.dart';

class CreateEventScreen extends StatefulWidget {
  const CreateEventScreen({super.key});

  @override
  State<CreateEventScreen> createState() => _CreateEventScreenState();
}

class _CreateEventScreenState extends State<CreateEventScreen> {
  final _title = TextEditingController();
  final _venue = TextEditingController();
  final _address = TextEditingController();
  final _date = TextEditingController();
  String _category = 'concert';
  bool _saving = false;

  Future<void> _submit() async {
    if (_title.text.trim().length < 3) return;
    setState(() => _saving = true);
    try {
      final auth = context.read<AuthStore>();
      await auth.api.createEvent({
        'title': _title.text.trim(),
        'category': _category,
        'venue_name': _venue.text.trim(),
        'address': _address.text.trim(),
        'starts_at': _date.text.trim(),
        'blurb': 'Mobil uygulama üzerinden oluşturuldu',
      });
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Etkinlik gönderildi — admin onayı bekleniyor')),
      );
      Navigator.pop(context);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Etkinlik oluştur')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text(
            'Konser, tiyatro veya buluşma ekle. Onay sonrası herkese görünür.',
            style: TextStyle(color: AppColors.muted),
          ),
          const SizedBox(height: 16),
          TextField(controller: _title, decoration: const InputDecoration(labelText: 'Başlık')),
          TextField(controller: _venue, decoration: const InputDecoration(labelText: 'Mekan')),
          TextField(controller: _address, decoration: const InputDecoration(labelText: 'Adres')),
          TextField(
            controller: _date,
            decoration: const InputDecoration(
              labelText: 'Tarih (YYYY-MM-DD HH:MM)',
              hintText: '2026-09-15 21:00',
            ),
          ),
          const SizedBox(height: 8),
          DropdownButtonFormField<String>(
            value: _category,
            items: const [
              DropdownMenuItem(value: 'concert', child: Text('Konser')),
              DropdownMenuItem(value: 'theater', child: Text('Tiyatro')),
              DropdownMenuItem(value: 'event', child: Text('Etkinlik')),
              DropdownMenuItem(value: 'family', child: Text('Aile')),
            ],
            onChanged: (v) => setState(() => _category = v ?? 'concert'),
          ),
          const SizedBox(height: 20),
          FilledButton(
            onPressed: _saving ? null : _submit,
            style: FilledButton.styleFrom(
              backgroundColor: AppColors.ink,
              padding: const EdgeInsets.symmetric(vertical: 14),
            ),
            child: Text(_saving ? 'Gönderiliyor…' : 'Gönder'),
          ),
        ],
      ),
    );
  }
}
