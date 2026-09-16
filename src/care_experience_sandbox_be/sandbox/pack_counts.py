"""Hub ``loaded_data`` counts from Care pack JSON sizes (not Care core)."""

from care.fixtures.loaders.load import DEFAULT_PACK, load_json

# (loaded_data key, pack JSON stem, list key in that file — None = root is a list)
_PACK_COUNT_SPECS: tuple[tuple[str, str, str | None], ...] = (
    ("organizations", "organizations", "organizations"),
    ("patients", "patients", "patients"),
    ("users", "users", "users"),
    ("departments", "facility_foundation", "departments"),
    ("locations", "facility_foundation", "locations"),
    ("healthcare_services", "facility_foundation", "healthcare_services"),
    ("devices", "facility_foundation", "devices"),
    ("schedules", "schedules", "schedules"),
    ("token_categories", "token_categories", "categories"),
    ("token_queues", "token_queues", "queues"),
    ("appointments", "appointments", "appointments"),
    ("encounters", "encounters", "encounters"),
    ("questionnaires", "questionnaires", None),
    ("templates", "templates", None),
    ("specimens", "specimens", None),
    ("observation_definitions", "observation_definitions", None),
    ("charge_item_definitions", "charge_item_definitions", None),
    ("resource_categories", "resource_categories", None),
    ("activity_definitions", "activity_definitions", None),
    ("product_knowledge", "product_knowledge", None),
    ("accounts", "billing", "accounts"),
    ("invoices", "billing", "invoices"),
    ("payments", "billing", "payments"),
    ("symptoms", "clinical_content", "symptoms"),
    ("diagnoses", "clinical_content", "diagnoses"),
    ("medication_requests", "clinical_content", "medication_requests"),
    ("questionnaire_responses", "clinical_content", "questionnaire_responses"),
    ("service_requests", "clinical_content", "service_requests"),
    ("products", "external_receipts", "products"),
)


def _list_len(data, key: str | None) -> int:
    if key is None:
        return len(data) if isinstance(data, list) else 0
    value = data.get(key, []) if isinstance(data, dict) else []
    return len(value) if isinstance(value, list) else 0


def summarize_pack_counts(pack_name: str = DEFAULT_PACK) -> dict[str, int]:
    """Flat resource→count from pack JSON sizes (what the pack intends to seed)."""
    cache: dict[str, object] = {}
    counts: dict[str, int] = {}
    for label, stem, key in _PACK_COUNT_SPECS:
        if stem not in cache:
            cache[stem] = load_json(stem, pack_name)
        counts[label] = _list_len(cache[stem], key)
    return counts
