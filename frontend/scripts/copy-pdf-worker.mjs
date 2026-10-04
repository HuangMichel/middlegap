import { copyFileSync, cpSync, mkdirSync } from 'node:fs';
mkdirSync('public', { recursive: true });
copyFileSync('node_modules/pdfjs-dist/build/pdf.worker.min.mjs', 'public/pdf.worker.min.mjs');
cpSync('node_modules/pdfjs-dist/standard_fonts', 'public/pdf-standard-fonts', { recursive: true });
cpSync('node_modules/pdfjs-dist/wasm', 'public/pdf-wasm', { recursive: true });
