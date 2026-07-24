const Database = require('better-sqlite3');
const fs = require('fs');
const path = require('path');
const config = require('../config');

const dbDir = path.dirname(config.DB_PATH);
if (!fs.existsSync(dbDir)) fs.mkdirSync(dbDir, { recursive: true });

const db = new Database(config.DB_PATH);

db.exec(`
  CREATE TABLE IF NOT EXISTS seen_items (
    id TEXT PRIMARY KEY,
    source TEXT,
    title TEXT,
    url TEXT,
    impact_score INTEGER,
    notified INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
  );
`);

function isSeen(id) {
  const row = db.prepare('SELECT 1 FROM seen_items WHERE id = ?').get(id);
  return !!row;
}

function markSeen({ id, source, title, url, impact_score, notified }) {
  db.prepare(`
    INSERT OR IGNORE INTO seen_items (id, source, title, url, impact_score, notified)
    VALUES (?, ?, ?, ?, ?, ?)
  `).run(id, source, title, url, impact_score || null, notified ? 1 : 0);
}

// eski kayitlari temizle (7 gunden eski)
function cleanup() {
  db.prepare(`DELETE FROM seen_items WHERE created_at < datetime('now', '-7 days')`).run();
}

module.exports = { isSeen, markSeen, cleanup };
