"""
Tests for CI/CD workflow configuration validation
"""
import yaml
from pathlib import Path


def test_infrastructure_workflow_exports_outputs():
    """Test that infrastructure workflow exports Terraform outputs."""
    workflows_dir = Path(__file__).parent.parent.parent / ".github" / "workflows"
    infra_workflow = workflows_dir / "infrastructure.yaml"
    
    assert infra_workflow.exists(), "infrastructure.yaml workflow should exist"
    
    with open(infra_workflow, 'r') as f:
        workflow = yaml.safe_load(f)
    
    # Check that the infra job has outputs
    assert 'jobs' in workflow, "Workflow should have jobs"
    assert 'infra' in workflow['jobs'], "Should have infra job"
    
    infra_job = workflow['jobs']['infra']
    assert 'outputs' in infra_job, "Infra job should have outputs"
    assert 'terraform-outputs' in infra_job['outputs'], "Should export terraform-outputs"
    
    # Check for terraform output step
    steps = infra_job['steps']
    output_step_found = False
    for step in steps:
        if 'Export Terraform Outputs' in step.get('name', ''):
            output_step_found = True
            assert 'terraform output -json' in step['run'], "Should run terraform output -json"
            break
    
    assert output_step_found, "Should have step to export Terraform outputs"


def test_cd_workflow_uses_helm():
    """Test that CD workflow uses Helm for deployment."""
    workflows_dir = Path(__file__).parent.parent.parent / ".github" / "workflows"
    cd_workflow = workflows_dir / "cd.yaml"
    
    assert cd_workflow.exists(), "cd.yaml workflow should exist"
    
    with open(cd_workflow, 'r') as f:
        workflow = yaml.safe_load(f)
    
    # Check that there's a helm deployment job
    assert 'jobs' in workflow, "Workflow should have jobs"
    assert 'deploy-helm' in workflow['jobs'], "Should have deploy-helm job"
    
    helm_job = workflow['jobs']['deploy-helm']
    steps = helm_job['steps']
    
    # Check for Helm installation step
    helm_install_found = False
    helm_deploy_found = False
    
    for step in steps:
        step_name = step.get('name', '')
        if 'Install Helm' in step_name:
            helm_install_found = True
        elif 'Deploy with Helm' in step_name:
            helm_deploy_found = True
            assert 'helm upgrade --install' in step['run'], "Should use helm upgrade --install"
            assert '--set backend.image=' in step['run'], "Should set backend image dynamically"
            assert '--set sparkJob.image=' in step['run'], "Should set spark image dynamically"
    
    assert helm_install_found, "Should install Helm"
    assert helm_deploy_found, "Should deploy with Helm"


def test_cd_workflow_builds_both_images():
    """Test that CD workflow builds both backend and Spark images."""
    workflows_dir = Path(__file__).parent.parent.parent / ".github" / "workflows"
    cd_workflow = workflows_dir / "cd.yaml"
    
    with open(cd_workflow, 'r') as f:
        workflow = yaml.safe_load(f)
    
    build_job = workflow['jobs']['build-and-push']
    steps = build_job['steps']
    
    spark_build_found = False
    backend_build_found = False
    
    for step in steps:
        step_name = step.get('name', '')
        if 'Spark ETL Docker image' in step_name:
            spark_build_found = True
            assert 'spark-etl:' in step['run'], "Should build spark-etl image"
        elif 'Backend Docker image' in step_name:
            backend_build_found = True
            assert 'genai-app:' in step['run'], "Should build genai-app image"
    
    assert spark_build_found, "Should build Spark ETL image"
    assert backend_build_found, "Should build backend image"


def test_workflows_have_proper_triggers():
    """Test that workflows have appropriate triggers."""
    workflows_dir = Path(__file__).parent.parent.parent / ".github" / "workflows"
    
    # Test infrastructure workflow
    with open(workflows_dir / "infrastructure.yaml", 'r') as f:
        content = f.read()
    
    # Check for trigger patterns in raw content since YAML parser converts 'on:' to True
    assert 'workflow_dispatch:' in content, "Infrastructure workflow should allow manual dispatch"
    assert 'push:' in content, "Infrastructure workflow should trigger on push"
    assert 'paths: [ \'infra/**\' ]' in content, "Should only trigger on infra changes"
    
    # Test CD workflow
    with open(workflows_dir / "cd.yaml", 'r') as f:
        cd_content = f.read()
    
    assert 'workflow_dispatch:' in cd_content, "CD workflow should allow manual dispatch"
    assert 'workflow_run:' in cd_content, "CD workflow should trigger after infrastructure workflow"
    assert (
        'Infrastructure Deployment Pipeline' in cd_content
    ), "Should reference infrastructure workflow"


def test_ci_workflow_unchanged():
    """Test that CI workflow still works for basic validation."""
    workflows_dir = Path(__file__).parent.parent.parent / ".github" / "workflows"
    ci_workflow = workflows_dir / "ci.yaml"
    
    assert ci_workflow.exists(), "ci.yaml workflow should exist"
    
    with open(ci_workflow, 'r') as f:
        workflow = yaml.safe_load(f)
    
    # Check basic CI functionality is preserved
    assert 'jobs' in workflow, "CI workflow should have jobs"
    assert 'ci' in workflow['jobs'], "Should have ci job"
    
    ci_job = workflow['jobs']['ci']
    steps = ci_job['steps']
    
    lint_found = False
    test_found = False
    
    for step in steps:
        step_name = step.get('name', '')
        if 'Lint with Ruff' in step_name:
            lint_found = True
        elif 'Run tests' in step_name:
            test_found = True
    
    assert lint_found, "Should have linting step"
    assert test_found, "Should have testing step"