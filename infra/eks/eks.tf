
module "eks" {
  source          = "terraform-aws-modules/eks/aws"
  version         = "21.0.4"

  name    = "${var.project_name}-eks"
  kubernetes_version = "1.29"
  subnet_ids      = var.subnet_ids
  vpc_id          = var.vpc_id

  eks_managed_node_groups = {
    default = {
      desired_capacity = 2
      max_capacity     = 3
      min_capacity     = 1

      instance_types = ["t3.medium"]
    }
  }

  enable_irsa = true

  tags = {
    Environment = "dev"
    Project     = var.project_name
  }
}

output "cluster_name" {
  value = module.eks.cluster_name
}

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "cluster_security_group_id" {
  value = module.eks.cluster_security_group_id
}
