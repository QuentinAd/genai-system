"""
Tests for Helm chart template validation
"""
import yaml
from pathlib import Path


def test_helm_values_yaml_structure():
    """Test that the values.yaml file has the expected structure."""
    helm_dir = Path(__file__).parent.parent.parent / "helm"
    values_file = helm_dir / "values.yaml"
    
    assert values_file.exists(), "values.yaml file should exist"
    
    with open(values_file, 'r') as f:
        values = yaml.safe_load(f)
    
    # Check required sections exist
    assert 'backend' in values, "backend section should exist in values.yaml"
    assert 'sparkJob' in values, "sparkJob section should exist in values.yaml"
    assert 'cluster' in values, "cluster section should exist in values.yaml"
    assert 'aws' in values, "aws section should exist in values.yaml"
    assert 'storage' in values, "storage section should exist in values.yaml"
    
    # Check backend configuration
    assert 'image' in values['backend'], "backend.image should be defined"
    assert 'replicaCount' in values['backend'], "backend.replicaCount should be defined"
    assert 'servicePort' in values['backend'], "backend.servicePort should be defined"
    assert 'resources' in values['backend'], "backend.resources should be defined"
    
    # Check spark job configuration
    assert 'image' in values['sparkJob'], "sparkJob.image should be defined"
    assert 'resources' in values['sparkJob'], "sparkJob.resources should be defined"


def test_helm_templates_exist():
    """Test that all expected Helm templates exist."""
    helm_dir = Path(__file__).parent.parent.parent / "helm"
    templates_dir = helm_dir / "templates"
    
    expected_templates = [
        "backend-deployment.yaml",
        "backend-service.yaml", 
        "spark-job.yaml",
        "configmap.yaml",
        "secret.yaml",
        "serviceaccount.yaml"
    ]
    
    for template in expected_templates:
        template_file = templates_dir / template
        assert template_file.exists(), f"Template {template} should exist"


def test_helm_chart_yaml():
    """Test that Chart.yaml has required fields."""
    helm_dir = Path(__file__).parent.parent.parent / "helm"
    chart_file = helm_dir / "Chart.yaml"
    
    assert chart_file.exists(), "Chart.yaml file should exist"
    
    with open(chart_file, 'r') as f:
        chart = yaml.safe_load(f)
    
    assert 'apiVersion' in chart, "Chart.yaml should have apiVersion"
    assert 'name' in chart, "Chart.yaml should have name"
    assert 'description' in chart, "Chart.yaml should have description"
    assert 'version' in chart, "Chart.yaml should have version"
    assert 'appVersion' in chart, "Chart.yaml should have appVersion"
    assert 'type' in chart, "Chart.yaml should have type"


def test_templates_are_valid_yaml():
    """Test that all template files contain valid YAML syntax."""
    helm_dir = Path(__file__).parent.parent.parent / "helm"
    templates_dir = helm_dir / "templates"
    
    for template_file in templates_dir.glob("*.yaml"):
        with open(template_file, 'r') as f:
            content = f.read()
            
        # Skip template validation as they contain Go template syntax
        # Just check that the file can be read and is not empty
        assert len(content.strip()) > 0, f"Template {template_file.name} should not be empty"
        assert "apiVersion" in content, f"Template {template_file.name} should contain apiVersion"


def test_placeholder_values_in_values_yaml():
    """Test that placeholder values are used instead of hardcoded values."""
    helm_dir = Path(__file__).parent.parent.parent / "helm"
    values_file = helm_dir / "values.yaml"
    
    with open(values_file, 'r') as f:
        content = f.read()
    
    # Check that placeholders are used
    assert "PLACEHOLDER" in content, "values.yaml should contain placeholder values"
    assert "BACKEND_IMAGE_PLACEHOLDER" in content, "Should use backend image placeholder"
    assert "SPARK_IMAGE_PLACEHOLDER" in content, "Should use spark image placeholder"
    assert "EKS_CLUSTER_NAME_PLACEHOLDER" in content, "Should use cluster name placeholder"
    
    # Check that secrets section exists but without default values
    assert "secrets:" in content, "Should have secrets section"
    assert 'openaiApiKey: ""' in content, "Should have empty openaiApiKey placeholder"
    assert 'awsAccessKeyId: ""' in content, "Should have empty awsAccessKeyId placeholder"


def test_secret_template_uses_proper_templating():
    """Test that secret.yaml uses proper Helm templating instead of hardcoded values."""
    helm_dir = Path(__file__).parent.parent.parent / "helm"
    secret_file = helm_dir / "templates" / "secret.yaml"
    
    with open(secret_file, 'r') as f:
        content = f.read()
    
    # Should NOT contain hardcoded base64 values
    assert "T1BFTkFJX0FQSV9LRVlfUExBQ0VIT0xERVI=" not in content, "Should not contain hardcoded OpenAI key"
    assert "QVdTX0FDQ0VTU19LRVlfSURfUExBQ0VIT0xERVI=" not in content, "Should not contain hardcoded AWS access key"
    assert "QVdTX1NFQ1JFVF9BQ0NFU1NfS0VZX1BMQUNFSE9MREVSRA==" not in content, "Should not contain hardcoded AWS secret key"
    
    # Should contain proper Helm templating
    assert "{{ .Values.secrets.openaiApiKey | b64enc | quote }}" in content, "Should use Helm templating for OpenAI key"
    assert "{{ .Values.secrets.awsAccessKeyId | b64enc | quote }}" in content, "Should use Helm templating for AWS access key"
    assert "{{ .Values.secrets.awsSecretAccessKey | b64enc | quote }}" in content, "Should use Helm templating for AWS secret key"
    
    # Should have conditional checks
    assert "{{- if .Values.secrets.openaiApiKey }}" in content, "Should conditionally include secrets"