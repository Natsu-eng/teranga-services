import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import eslintConfigPrettier from 'eslint-config-prettier';
import globals from 'globals';

export default tseslint.config(
  {
    ignores: ['dist/**', 'node_modules/**', 'coverage/**'],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    // Align ESLint with the underscore convention already used to satisfy
    // tsc's noUnusedLocals/noUnusedParameters for intentionally-unused
    // bindings (e.g. unused props kept for interface compatibility).
    rules: {
      '@typescript-eslint/no-unused-vars': [
        'error',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          destructuredArrayIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^_',
        },
      ],
    },
  },
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: globals.browser,
    },
    settings: {
      react: { version: 'detect' },
    },
    plugins: {
      react,
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...react.configs.flat.recommended.rules,
      ...react.configs.flat['jsx-runtime'].rules,
      ...reactHooks.configs.recommended.rules,
      ...reactRefresh.configs.vite.rules,
      // Typed via TypeScript interfaces instead of runtime PropTypes.
      'react/prop-types': 'off',
    },
  },
  {
    // Le mock en mémoire et ses données fictives sont réservés aux tests :
    // aucun code de production ne peut les importer (ils ne doivent jamais
    // pouvoir remplacer en silence une réponse du backend -- voir
    // src/lib/api/index.ts). mock.ts lui-même peut lire mockData.
    files: ['src/**/*.{ts,tsx}'],
    ignores: ['src/**/*.test.{ts,tsx}', 'src/lib/api/mock.ts'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              // Tout chemin (relatif ou non) qui se termine par /mock ou /mockData.
              regex: '(^|/)(mock|mockData)(\\.ts)?$',
              message:
                'Mock et données fictives réservés aux tests : le code de production passe par `api` (src/lib/api/index.ts).',
            },
          ],
        },
      ],
    },
  },
  {
    files: ['vite.config.ts', 'vitest.config.ts', 'vitest.setup.ts', 'pwa/serviceWorkerPlugin.ts'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: globals.node,
    },
  },
  {
    // Modèle du service worker (application installable) : script classique
    // exécuté dans le contexte d'un service worker (self, caches, clients).
    files: ['pwa/sw.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'script',
      globals: globals.serviceworker,
    },
  },
  eslintConfigPrettier,
);
