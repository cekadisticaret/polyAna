const cron = require('node-cron');
const config = require('./config');
const { runScan } = require('./src/scan');

const runOnce = process.argv.includes('--once');

if (runOnce) {
  runScan()
    .then(() => process.exit(0))
    .catch((err) => {
      console.error('Hata:', err);
      process.exit(1);
    });
} else {
  console.log(`Crypto News Monitor baslatildi. Zamanlama: "${config.CRON_SCHEDULE}"`);
  // Baslarken bir kere hemen calistir
  runScan().catch((err) => console.error('Ilk tarama hatasi:', err));

  cron.schedule(config.CRON_SCHEDULE, () => {
    runScan().catch((err) => console.error('Zamanlanmis tarama hatasi:', err));
  });
}
