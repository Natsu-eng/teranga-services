"""Schémas Pydantic du triage IA (`POST /api/v1/ai/analyze`, BUILD_PLAN.md §3.2,
§6 Lot 11).

`TriageResult` est la sortie strictement validée d'un `AiTriageProvider`
(app/services/ai_triage_providers.py) -- montants positifs, total cohérent,
urgence dans l'enum fermé -- et sert directement de `response_model` à
l'endpoint : aucune conversion supplémentaire entre "sortie provider" et
"réponse HTTP". L'existence de `trade_code` dans la table `trade` n'est PAS
vérifiée ici (ce schéma n'a pas de session DB) : c'est le rôle de
`app.services.ai_triage.analyze_problem`.
"""

from pydantic import BaseModel, Field, model_validator

from app.models.enums import Urgency


class AnalyzeProblemIn(BaseModel):
    description: str = Field(min_length=3, max_length=2000)


class SuggestedQuoteOut(BaseModel):
    labor_fcfa: int = Field(ge=0)
    materials_fcfa: int = Field(ge=0)
    total_fcfa: int = Field(ge=0)

    @model_validator(mode="after")
    def _check_total_is_labor_plus_materials(self) -> "SuggestedQuoteOut":
        if self.total_fcfa != self.labor_fcfa + self.materials_fcfa:
            raise ValueError("total_fcfa doit être égal à labor_fcfa + materials_fcfa.")
        return self


class TriageResult(BaseModel):
    trade_code: str
    price_min_fcfa: int = Field(ge=0)
    price_max_fcfa: int = Field(ge=0)
    urgency: Urgency
    suggested_quote: SuggestedQuoteOut

    @model_validator(mode="after")
    def _check_price_range_is_ordered(self) -> "TriageResult":
        if self.price_max_fcfa < self.price_min_fcfa:
            raise ValueError("price_max_fcfa doit être supérieur ou égal à price_min_fcfa.")
        return self
