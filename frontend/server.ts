import express from 'express';
import path from 'path';
import { createServer as createViteServer } from 'vite';
import { createProxyMiddleware } from 'http-proxy-middleware';
import { GoogleGenAI } from '@google/genai';
import dotenv from 'dotenv';

dotenv.config();
dotenv.config({ path: '.env.local', override: true });

// URL du backend FastAPI (Lots 6-9), jamais codée en dur dans le code du
// front : lue depuis l'environnement, avec un défaut cohérent avec
// `uv run uvicorn app.main:app --reload --port 8000` (backend/README.md).
// En production, /api/v1 est servi par un reverse proxy/la plateforme —
// ce module de proxy n'est monté qu'en dev (voir plus bas).
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

async function startServer() {
  const app = express();
  const PORT = 3000;

  if (process.env.NODE_ENV !== 'production') {
    // Le front n'appelle jamais l'URL absolue du backend : il parle en
    // relatif à /api/v1, et c'est ce middleware de dev qui route vers
    // FastAPI. /api/analyze-problem (ci-dessous) reste géré par Express.
    app.use(
      '/api/v1',
      createProxyMiddleware({
        // Express strips the '/api/v1' mount prefix from req.url before this
        // middleware runs, so it must be included in the target to be
        // preserved when forwarding to the backend (http-proxy-middleware
        // does not reconstruct it automatically).
        target: `${BACKEND_URL}/api/v1`,
        changeOrigin: true,
      }),
    );
  }

  app.use(express.json());

  // API Route: AI Problem Diagnosis
  app.post('/api/analyze-problem', async (req, res) => {
    try {
      const { description } = req.body;
      if (!description || typeof description !== 'string') {
        return res.status(400).json({ error: 'La description est requise.' });
      }

      const apiKey = process.env.GEMINI_API_KEY;

      if (apiKey && apiKey !== 'MY_GEMINI_API_KEY') {
        try {
          const ai = new GoogleGenAI({ apiKey });
          const response = await ai.models.generateContent({
            model: 'gemini-2.5-flash',
            contents: `Tu es l'assistant virtuel intelligent de "Téranga Services", la plateforme leader de services à domicile et d'artisans au Sénégal (Dakar).
Analyse le problème décrit par l'utilisateur et renvoie UNIQUEMENT un objet JSON strictement valide avec cette structure exacte (sans bloc markdown triple quote si possible, ou pur json) :

{
  "trade": "Plomberie — fuite", // Métier et sous-catégorie détectés (ex: Plomberie — fuite, Électricité — panne, Climatisation — entretien, Menuiserie — réparation)
  "priceEstimate": "8 000 – 15 000 FCFA", // Estimation réaliste en FCFA pour Dakar
  "recommendedCount": 3,
  "explanation": "L'IA a analysé votre description pour identifier les meilleurs experts disponibles immédiatement à Dakar.",
  "urgency": "haute" // ou "moyenne" ou "normale",
  "suggestedDevis": {
    "title": "Réparation fuite d'eau",
    "labor": 8000,
    "materials": 4000,
    "total": 12000
  }
}

Description utilisateur: "${description}"`,
          });

          const text = response.text || '';
          // Extract JSON if wrapped in markdown
          const jsonMatch = text.match(/\{[\s\S]*\}/);
          if (jsonMatch) {
            const parsed = JSON.parse(jsonMatch[0]);
            return res.json(parsed);
          }
        } catch (aiErr) {
          console.error('Gemini API Error, fallback to heuristic rules:', aiErr);
        }
      }

      // Smart heuristic fallback if no API key or error
      const descLower = description.toLowerCase();
      let trade = 'Plomberie — fuite';
      let priceEstimate = '8 000 – 15 000 FCFA';
      let labor = 8000;
      let materials = 4000;
      let title = "Réparation fuite d'eau";

      if (
        descLower.includes('electr') ||
        descLower.includes('électricité') ||
        descLower.includes('prise') ||
        descLower.includes('courant') ||
        descLower.includes('disjoncteur')
      ) {
        trade = 'Électricité — dépannage';
        priceEstimate = '12 000 – 25 000 FCFA';
        labor = 15000;
        materials = 5000;
        title = 'Diagnostic et réparation électrique';
      } else if (
        descLower.includes('clim') ||
        descLower.includes('froid') ||
        descLower.includes('chaleur')
      ) {
        trade = 'Climatisation — entretien';
        priceEstimate = '15 000 – 30 000 FCFA';
        labor = 18000;
        materials = 7000;
        title = 'Recharge et nettoyage climatiseur';
      } else if (
        descLower.includes('porte') ||
        descLower.includes('bois') ||
        descLower.includes('serrure') ||
        descLower.includes('menuisier')
      ) {
        trade = 'Menuiserie — réparation';
        priceEstimate = '10 000 – 20 000 FCFA';
        labor = 12000;
        materials = 4000;
        title = 'Réparation porte / serrurerie';
      }

      return res.json({
        trade,
        priceEstimate,
        recommendedCount: 3,
        explanation:
          "L'IA a analysé votre description pour identifier les meilleurs experts disponibles immédiatement à Dakar.",
        urgency: 'moyenne',
        suggestedDevis: {
          title,
          labor,
          materials,
          total: labor + materials,
        },
      });
    } catch (err) {
      console.error('Server error:', err);
      return res.status(500).json({ error: 'Erreur interne du serveur.' });
    }
  });

  // Vite Middleware for Dev or Static Serving for Prod
  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res, next) => {
      if (req.path.startsWith('/api/')) {
        next();
        return;
      }
      res.sendFile(path.join(distPath, 'index.html'));
    });
    app.use('/api', (_req, res) => {
      res.status(404).json({ error: 'Route API introuvable.' });
    });
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Téranga Services Server running on http://0.0.0.0:${PORT}`);
  });
}

startServer();
