"""Blueprint Render (render.yaml, DEPLOYMENT.md §12) : cohérent avec le code.

Analyse volontairement simple (ligne à ligne, le fichier est plat) : pas de
dépendance YAML ajoutée au projet pour un seul test.
"""

import re
from pathlib import Path

from app.core.config import Settings
from app.main import app

REPO = Path(__file__).resolve().parents[2]
BLUEPRINT = (REPO / "render.yaml").read_text(encoding="utf-8")

# Variables à valeur FIXÉE dans le Blueprint (comportement de la beta) :
# toutes les autres sont des secrets ou des adresses, jamais écrites ici.
FIXED = {
    "ENVIRONMENT": "staging",
    "PAYMENT_PROVIDER": "disabled",
    "STORAGE_BACKEND": "s3",
    "WEB_CONCURRENCY": "1",
}


def _field(name: str) -> str:
    match = re.search(rf"^\s+{name}: (.+)$", BLUEPRINT, re.MULTILINE)
    assert match is not None, name
    return match.group(1).strip()


def _env_vars() -> dict[str, str]:
    """{clé: 'value=...' | 'sync: false' | 'generateValue: true'}."""
    entries = re.findall(r"- key: ([A-Z0-9_]+)\n\s+(\w+): (.+)", BLUEPRINT)
    return {key: f"{kind}: {value.strip()}" for key, kind, value in entries}


def test_service_builds_the_backend_image_and_starts_with_serve_py() -> None:
    assert _field("runtime") == "docker"
    assert _field("plan") == "free"
    assert (REPO / _field("dockerfilePath")).is_file()
    assert (REPO / _field("dockerContext") / "scripts" / "serve.py").is_file()
    assert _field("dockerCommand") == "python scripts/serve.py"


def test_health_check_targets_the_readiness_route() -> None:
    assert _field("healthCheckPath") == "/api/v1/health/ready"
    assert "get" in app.openapi()["paths"]["/api/v1/health/ready"]


def test_only_beta_behaviour_is_hardcoded_never_a_secret() -> None:
    env = _env_vars()
    hardcoded = {
        key: spec.split(": ", 1)[1].strip('"')
        for key, spec in env.items()
        if spec.startswith("value")
    }
    assert hardcoded == FIXED
    assert env["JWT_SECRET"] == "generateValue: true"
    for key, spec in env.items():
        if key not in FIXED and key != "JWT_SECRET":
            assert spec == "sync: false", key


def test_every_variable_is_a_real_setting_and_the_required_ones_are_declared() -> None:
    env = _env_vars()
    known = {name.upper() for name in Settings.model_fields} | {"WEB_CONCURRENCY"}
    assert set(env) <= known, set(env) - known
    required = {
        name.upper() for name, field in Settings.model_fields.items() if field.is_required()
    }
    assert required <= set(env)
    # Indispensables à la beta derrière le proxy Render, avec stockage S3 et OTP de test.
    for key in (
        "TRUSTED_PROXY_HOPS",
        "CORS_ORIGINS",
        "FRONTEND_PUBLIC_BASE_URL",
        "BACKEND_PUBLIC_BASE_URL",
        "S3_ENDPOINT_URL",
        "S3_PRIVATE_BUCKET",
        "S3_PUBLIC_BUCKET",
        "S3_PUBLIC_BASE_URL",
        "OTP_TEST_WHITELIST",
        "OTP_TEST_CODE",
        # Livraison des codes (console ou termii, DEPLOYMENT.md §13).
        "SMS_PROVIDER",
        "TERMII_API_KEY",
        "TERMII_SENDER_ID",
        "TERMII_BASE_URL",
        # Notifications push des nouveaux messages (DEPLOYMENT.md §15).
        "WEB_PUSH_ENABLED",
        "VAPID_PUBLIC_KEY",
        "VAPID_PRIVATE_KEY",
        "VAPID_SUBJECT",
    ):
        assert key in env, key


def test_railway_path_is_untouched() -> None:
    """Railway garde sa propre étape de migration et le CMD du Dockerfile."""
    railway = (REPO / "backend" / "railway.json").read_text(encoding="utf-8")
    assert '"preDeployCommand": ["alembic upgrade head"]' in railway
    assert "serve.py" not in railway
    assert "serve.py" not in (REPO / "backend" / "Dockerfile").read_text(encoding="utf-8")
