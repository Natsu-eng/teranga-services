"""Rate limiting à fenêtre glissante, en mémoire (BUILD_PLAN.md §4).

**Dette technique documentée pour Railway** : cet état vit dans le
processus Python (un `dict` protégé par un verrou asyncio). Il ne survit
ni à un redémarrage, ni à plusieurs instances/workers -- deux instances
derrière un load balancer appliqueraient chacune leur propre limite,
divisant de fait la limite réelle par le nombre d'instances. Acceptable
pour un lancement à une seule instance ; à remplacer par un backend
partagé (Redis, ou une table dédiée) si le trafic ou le nombre
d'instances grandit.
"""

import asyncio
import time


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str, *, max_hits: int, window_seconds: int) -> bool:
        """Enregistre un hit pour `key` et renvoie `False` si `max_hits` est
        dépassé sur les `window_seconds` dernières secondes."""
        now = time.monotonic()
        cutoff = now - window_seconds
        async with self._lock:
            hits = self._hits.get(key, [])
            while hits and hits[0] < cutoff:
                hits.pop(0)
            if not hits:
                # Purge les clés redevenues inactives -- sans ça, chaque
                # numéro/IP jamais revu resterait en mémoire indéfiniment.
                self._hits.pop(key, None)

            if len(hits) >= max_hits:
                return False

            hits.append(now)
            self._hits[key] = hits
            return True


otp_rate_limiter = SlidingWindowRateLimiter()


def get_otp_rate_limiter() -> SlidingWindowRateLimiter:
    """Dépendance FastAPI -- indirection nécessaire pour que les tests
    puissent substituer une instance fraîche par requête (`dependency_overrides`)
    sans se marcher dessus via le singleton partagé par tout le processus.
    """
    return otp_rate_limiter
