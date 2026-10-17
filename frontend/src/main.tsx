import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
// Polices auto-hébergées (aucun CDN) : Vite copie les fichiers woff2 dans
// dist/assets et les sert depuis la même origine que l'app.
// - Fraunces, variante « opsz » : axes graisse + taille optique, le
//   navigateur adapte automatiquement le dessin à la taille du titre.
// - Figtree, variante graisse : corps de texte et interface.
import '@fontsource-variable/fraunces/opsz.css';
import '@fontsource-variable/figtree';
import App from './App.tsx';
import { TestEnvironmentBanner } from './components/layout/TestEnvironmentBanner';
import { captureInstallPrompt } from './lib/pwa/installPrompt';
import { setupServiceWorker } from './lib/pwa/serviceWorker';
import './index.css';

// Application installable : l'invitation d'installation (Android) peut
// survenir avant tout écran, et le service worker s'enregistre au chargement.
captureInstallPrompt();
setupServiceWorker();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {/* Hors production uniquement (décidé par le backend, voir le composant). */}
    <TestEnvironmentBanner />
    <App />
  </StrictMode>,
);
