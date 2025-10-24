"""
Tests for Terraform configuration validation
"""

import re
from pathlib import Path


def test_terraform_main_has_outputs():
    """Test that main.tf defines all required outputs."""
    infra_dir = Path(__file__).parent.parent.parent / "infra"
    main_file = infra_dir / "main.tf"

    assert main_file.exists(), "main.tf file should exist"

    with open(main_file, "r") as f:
        content = f.read()

    # Check for required outputs
    required_outputs = [
        "vpc_id",
        "private_subnet_ids",
        "public_subnet_ids",
        "ecr_etl_repository_url",
        "ecr_backend_repository_url",
        "mwaa_env_name",
        "dags_bucket",
        "data_bucket",
        "hirag_ingestion_bucket",
        "hirag_kv_table_name",
        "opensearch_domain_endpoint",
        "neptune_writer_endpoint",
        "ui_bucket_name",
        "ui_distribution_domain_name",
        "ui_distribution_id",
    ]

    for output in required_outputs:
        assert f'output "{output}"' in content, f"Output {output} should be defined in main.tf"


def test_terraform_modules_exist():
    """Test that all required Terraform modules exist."""
    infra_dir = Path(__file__).parent.parent.parent / "infra"

    expected_modules = [
        "vpc",
        "s3",
        "ecr",
        "mwaa",
        "dynamodb",
        "neptune",
        "opensearch",
        "cloudfront_ui",
    ]

    for module in expected_modules:
        module_dir = infra_dir / module
        assert module_dir.exists(), f"Module {module} directory should exist"
        assert module_dir.is_dir(), f"Module {module} should be a directory"


def test_opensearch_module_has_outputs():
    """Test that OpenSearch module defines required outputs."""
    opensearch_dir = Path(__file__).parent.parent.parent / "infra" / "opensearch"
    outputs_file = opensearch_dir / "outputs.tf"

    assert outputs_file.exists(), "OpenSearch module should have outputs.tf"

    with open(outputs_file, "r") as f:
        content = f.read()

    required_outputs = [
        "opensearch_domain_endpoint",
        "opensearch_domain_arn",
        "opensearch_security_group_id",
        "opensearch_admin_secret_arn",
    ]

    for output in required_outputs:
        assert f'output "{output}"' in content, f"OpenSearch output {output} should be defined"


def test_ui_module_has_outputs():
    """Test that UI (CloudFront) module defines required outputs."""
    ui_dir = Path(__file__).parent.parent.parent / "infra" / "cloudfront_ui"
    outputs_file = ui_dir / "outputs.tf"

    assert outputs_file.exists(), "UI module should have outputs.tf"

    with open(outputs_file, "r") as f:
        content = f.read()

    required_outputs = [
        "ui_bucket_name",
        "ui_distribution_id",
        "ui_distribution_domain_name",
    ]

    for output in required_outputs:
        assert f'output "{output}"' in content, f"UI output {output} should be defined"


def test_ecr_module_has_outputs():
    """Test that ECR module defines required outputs."""
    ecr_dir = Path(__file__).parent.parent.parent / "infra" / "ecr"
    outputs_file = ecr_dir / "outputs.tf"

    assert outputs_file.exists(), "ECR module should have outputs.tf"

    with open(outputs_file, "r") as f:
        content = f.read()

    required_outputs = ["repository_url", "repository_name", "registry_id"]

    for output in required_outputs:
        assert f'output "{output}"' in content, f"ECR output {output} should be defined"


def test_main_tf_has_dual_ecr_modules():
    """Test that main.tf defines both ECR modules for etl and backend."""
    infra_dir = Path(__file__).parent.parent.parent / "infra"
    main_file = infra_dir / "main.tf"

    with open(main_file, "r") as f:
        content = f.read()

    assert 'module "ecr_etl"' in content, "Should define ecr_etl module"
    assert 'module "ecr_backend"' in content, "Should define ecr_backend module"
    assert 'ecr_repo     = "etl"' in content, "ETL module should use etl repo name"
    assert 'ecr_repo     = "genai-app"' in content, "Backend module should use genai-app repo name"


def test_terraform_file_formatting():
    """Test basic Terraform file formatting and syntax."""
    infra_dir = Path(__file__).parent.parent.parent / "infra"

    # Test main.tf formatting
    main_file = infra_dir / "main.tf"
    with open(main_file, "r") as f:
        content = f.read()

    # Check for common formatting issues
    assert not re.search(
        r"depends_on = \[ [^]]+\]", content
    ), "depends_on should be formatted correctly"
    assert "depends_on = [module.vpc]" in content, "depends_on should use proper formatting"
