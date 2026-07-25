from pathlib import Path

from jsonschema import Draft202012Validator

from m32_bridge.config.schemas import CONTRACTS_DIR, load_schema, validate_with_schema


def test_all_contract_schemas_are_valid_draft_2020_12():
    for path in CONTRACTS_DIR.glob("*.schema.json"):
        schema = load_schema(path.name)
        Draft202012Validator.check_schema(schema)


def test_config_example_matches_config_schema():
    import yaml

    config = yaml.safe_load(Path("config.example.yaml").read_text())
    validate_with_schema(config, "config.schema.json")

