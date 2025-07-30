import yaml
from pathlib import Path


def test_airflow_secret_key_present():
    compose = yaml.safe_load(Path("docker-compose.yaml").read_text())
    env_vars = compose["services"]["airflow"]["environment"]
    assert "AIRFLOW__WEBSERVER__SECRET_KEY" in env_vars
