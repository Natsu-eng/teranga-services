<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://ai.google.dev/static/site-assets/images/share-ais-513315318.png" />
</div>

# Run and deploy your AI Studio app

This contains everything you need to run your app locally.

View your app in AI Studio: https://ai.studio/apps/257d8f30-3428-49e0-b60d-1181dad9fb1e

## Développement local

**Prérequis :** Node.js LTS (v20+) et git.

1. Installer les dépendances :
   `npm install`
2. (Optionnel) Copier [.env.local.example](.env.local.example) vers `.env.local` et y renseigner
   votre clé `GEMINI_API_KEY`. Sans clé (ou fichier absent), le serveur fonctionne quand même :
   `/api/analyze-problem` bascule automatiquement sur une heuristique par mots-clés au lieu
   d'appeler Gemini.
3. Lancer le serveur de développement (Express + middleware Vite, avec HMR) :
   `npm run dev`
   L'application est servie sur http://localhost:3000.
4. Avant de commit/push, faire passer la porte de validation unique (typecheck + lint + tests) :
   `npm run validate`
