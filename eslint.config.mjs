import { createRequire } from 'node:module';

const require = createRequire(new URL('./frontend/package.json', import.meta.url));
const js = require('@eslint/js');
const globals = require('globals');

export default [
  {
    files: ['scripts/**/*.mjs', 'eslint.config.mjs'],
    ...js.configs.recommended,
    languageOptions: { globals: globals.node },
  },
];
