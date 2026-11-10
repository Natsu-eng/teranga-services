"""Fournisseurs de triage IA, derrière une interface indépendante du
fournisseur (BUILD_PLAN.md §3.2, §6 Lot 11).

Le fournisseur actif est choisi par configuration (`AI_TRIAGE_PROVIDER`),
jamais codé en dur -- voir `get_ai_triage_provider`, même principe que
`app.services.sms.get_sms_provider`. `HeuristicTriageProvider` est le filet
de secours : aucun appel réseau, toujours disponible, portée depuis l'ancien
Express `/api/analyze-problem`. Aucun code de ce module ne référence un nom
de fournisseur concret en dehors de `MistralTriageProvider` lui-même --
`app.services.ai_triage` (l'orchestrateur) ne connaît que le `Protocol`.
"""

import json
import logging
from typing import Protocol

import httpx

from app.core.config import Settings, get_settings
from app.models.enums import Urgency
from app.schemas.ai_triage import SuggestedQuoteOut, TriageResult

logger = logging.getLogger(__name__)


class AiTriageProvider(Protocol):
    async def analyze(self, description: str) -> TriageResult:
        """Analyse la description d'un problème et renvoie un triage
        strictement validé (schéma, montants, énumérations)."""
        ...


class AiTriageProviderError(Exception):
    """Le fournisseur réseau a échoué (timeout, erreur HTTP, JSON malformé,
    sortie non conforme au schéma). Capturée par `app.services.ai_triage`
    pour basculer sur l'heuristique -- jamais propagée telle quelle au
    client (pas de 500 pour un incident IA)."""


# --- Heuristique (filet de secours, sans réseau) ----------------------------

_URGENCY_IMMEDIATE_KEYWORDS = ("immédiat", "immediat", "tout de suite", "au plus vite")
_URGENCY_URGENT_KEYWORDS = ("urgent", "urgence")

# Ordre de priorité : la première règle dont un mot-clé matche l'emporte.
# Porté depuis l'ancien frontend/server.ts, étendu à la maçonnerie (métier
# seedé côté backend, scripts/seed.py, mais absent de l'ancienne heuristique).
# La plomberie a désormais ses propres mots-clés : elle n'est plus le métier
# renvoyé par défaut quand rien n'est reconnu (`trade_code=None` alors).
_TRADE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("electricite", ("electr", "électr", "prise", "courant", "disjoncteur")),
    ("climatisation", ("clim", "froid", "chaleur")),
    ("menuiserie", ("porte", "bois", "serrure", "menuisier")),
    ("maconnerie", ("mur", "fissure", "béton", "beton", "carrelage", "ciment")),
    (
        "plomberie",
        (
            "plomb",
            "fuite",
            "fuit",
            "robinet",
            "évier",
            "evier",
            "tuyau",
            "canalisation",
            # Formes complètes : « eau » seul reconnaîtrait aussi « bureau »,
            # « nouveau »... et « bouch » reconnaîtrait « boucher ».
            "d'eau",
            "l'eau",
            "chauffe-eau",
            "wc",
            "toilette",
            "chasse d'eau",
            "douche",
            "lavabo",
            "bouché",
            "bouchon",
            "débouch",
            "deboucher",
            "égout",
            "egout",
        ),
    ),
)

# code -> (price_min_fcfa, price_max_fcfa, labor_fcfa, materials_fcfa),
# repris des montants de l'ancienne heuristique Express (plus maçonnerie).
_QUOTE_BY_TRADE: dict[str, tuple[int, int, int, int]] = {
    "plomberie": (8_000, 15_000, 8_000, 4_000),
    "electricite": (12_000, 25_000, 15_000, 5_000),
    "climatisation": (15_000, 30_000, 18_000, 7_000),
    "menuiserie": (10_000, 20_000, 12_000, 4_000),
    "maconnerie": (15_000, 35_000, 20_000, 10_000),
}


class HeuristicTriageProvider:
    """Filet de secours par mots-clés français, sans aucun appel réseau."""

    async def analyze(self, description: str) -> TriageResult:
        lowered = description.lower()
        trade_code = self._detect_trade(lowered)
        urgency = self._detect_urgency(lowered)
        if trade_code is None:
            # Aucun mot-clé reconnu : on le DIT (le client choisira le métier),
            # sans montant -- jamais un métier ni un prix inventés.
            return TriageResult(trade_code=None, urgency=urgency)
        price_min, price_max, labor, materials = _QUOTE_BY_TRADE[trade_code]
        return TriageResult(
            trade_code=trade_code,
            price_min_fcfa=price_min,
            price_max_fcfa=price_max,
            urgency=urgency,
            suggested_quote=SuggestedQuoteOut(
                labor_fcfa=labor, materials_fcfa=materials, total_fcfa=labor + materials
            ),
        )

    @staticmethod
    def _detect_trade(lowered: str) -> str | None:
        for code, keywords in _TRADE_RULES:
            if any(keyword in lowered for keyword in keywords):
                return code
        return None

    @staticmethod
    def _detect_urgency(lowered: str) -> Urgency:
        if any(keyword in lowered for keyword in _URGENCY_IMMEDIATE_KEYWORDS):
            return Urgency.IMMEDIAT
        if any(keyword in lowered for keyword in _URGENCY_URGENT_KEYWORDS):
            return Urgency.URGENT
        return Urgency.NORMAL


# --- Mistral (réseau, sortie JSON forcée, timeout explicite) ---------------

_MISTRAL_SYSTEM_PROMPT = """Tu es l'assistant de triage de "Téranga Services", \
une plateforme de mise en relation avec des artisans à Dakar, Sénégal.

Analyse la description du problème fournie par le client et réponds \
UNIQUEMENT avec un objet JSON strictement conforme au schéma suivant, sans \
texte autour ni bloc markdown :

{
  "trade_code": "plomberie",
  "price_min_fcfa": 8000,
  "price_max_fcfa": 15000,
  "urgency": "normal",
  "suggested_quote": {
    "labor_fcfa": 8000,
    "materials_fcfa": 4000,
    "total_fcfa": 12000
  }
}

Contraintes :
- "trade_code" doit être EXACTEMENT l'un de : plomberie, electricite, \
climatisation, menuiserie, maconnerie. Si AUCUN ne correspond, réponds \
"trade_code": null avec "price_min_fcfa", "price_max_fcfa" et \
"suggested_quote" à null (ne jamais forcer un métier).
- "price_min_fcfa" et "price_max_fcfa" sont des entiers positifs, en FCFA, \
avec price_max_fcfa >= price_min_fcfa, réalistes pour Dakar.
- "urgency" doit être EXACTEMENT l'un de : normal, urgent, immediat.
- "total_fcfa" doit être EXACTEMENT égal à labor_fcfa + materials_fcfa.
"""


class MistralTriageProvider:
    """Triage via l'API Mistral (mode JSON pour forcer une sortie
    structurée, validée ensuite par `TriageResult` -- jamais d'extraction
    par regex). Le nom du fournisseur, le modèle, la clé et l'URL de base ne
    sont jamais codés en dur : tout vient de `Settings`
    (voir backend/.env.example)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def analyze(self, description: str) -> TriageResult:
        if not self._settings.mistral_api_key:
            raise AiTriageProviderError(
                "MISTRAL_API_KEY absente alors que AI_TRIAGE_PROVIDER=mistral."
            )
        try:
            async with httpx.AsyncClient(timeout=self._settings.mistral_timeout_seconds) as client:
                response = await client.post(
                    f"{self._settings.mistral_api_base_url}/chat/completions",
                    json=self._build_payload(description),
                    headers={"Authorization": f"Bearer {self._settings.mistral_api_key}"},
                )
                response.raise_for_status()
                body = response.json()
            content = body["choices"][0]["message"]["content"]
            raw = json.loads(content)
            return TriageResult.model_validate(raw)
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
            raise AiTriageProviderError(f"Appel Mistral échoué : {exc}") from exc

    def _build_payload(self, description: str) -> dict[str, object]:
        return {
            "model": self._settings.mistral_model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _MISTRAL_SYSTEM_PROMPT},
                {"role": "user", "content": description},
            ],
        }


def get_ai_triage_provider(settings: Settings | None = None) -> AiTriageProvider:
    settings = settings or get_settings()
    if settings.ai_triage_provider == "mistral":
        return MistralTriageProvider(settings)
    return HeuristicTriageProvider()
