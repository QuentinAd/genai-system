# Infrastructure Scripts

## get_helm.sh

This script is the official Helm installation script from the Helm project (https://github.com/helm/helm).

**Purpose**: Downloads and installs the latest version of the Helm CLI tool.

**Usage**: 
```bash
# From the infra directory
./get_helm.sh

# Or with specific version
./get_helm.sh --version v3.12.0
```

**When to use**:
- Setting up local development environments
- CI/CD pipelines that need Helm CLI (though most CI systems now provide Helm via actions/setup-helm)
- Container images that need Helm installed

**Note**: The GitHub Actions workflow uses `azure/setup-helm@v4` action instead of this script for better caching and integration. This script is provided as a backup option for local development or other deployment scenarios.

**Source**: This is the unmodified official installer script from the Helm project.