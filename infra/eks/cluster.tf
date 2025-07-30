# infra/eks/cluster.tf
resource "aws_eks_cluster" "this" {
  name     = "${var.project_name}-eks"
  role_arn = aws_iam_role.eks_cluster.arn

  version = "1.32"

  vpc_config {
    subnet_ids         = var.subnet_ids
    endpoint_public_access  = false
    endpoint_private_access = true
  }

  # Optional: enable logging
  enabled_cluster_log_types = ["api", "audit", "authenticator"]
}
