import { defineUserConfig } from 'vitepress-export-pdf';

// Page order mirrors the sidebar in .vitepress/config.mts
const SIDEBAR_ORDER = [
  '/devices',
  '/buttons-codes',
  '/automations',
  '/ir-database',
  '/bridges',
  '/settings',
  '/troubleshooting',
  '/mqtt',
  '/websocket',
  '/dev-setup',
  '/dev-testing',
  '/dev-api',
  '/dev-migrations',
];

export default defineUserConfig({
  outFile: 'ir2mqtt-docs.pdf',
  outDir: '..',
  routePatterns: ['/**', '!/404.html', '!/index.html'],
  pdfOptions: {
    format: 'A4',
    printBackground: true,
    margin: {
      top: '15mm',
      right: '15mm',
      bottom: '20mm',
      left: '15mm',
    },
  },
  pdfOutlines: true,
  sorter(a, b) {
    const rank = (path: string) => {
      const idx = SIDEBAR_ORDER.findIndex(p => path.includes(p));
      return idx === -1 ? 999 : idx;
    };
    return rank(a.path) - rank(b.path);
  },
});
