output "cluster_name" {
  value = aws_eks_cluster.this.name
  description = "The name of the EKS cluster"
}

output "cluster_endpoint" {
  value = aws_eks_cluster.this.endpoint
  description = "The endpoint for the EKS cluster API server"
}

output "cluster_version" {
  value = aws_eks_cluster.this.version
  description = "The Kubernetes version of the EKS cluster"
}

output "cluster_security_group_id" {
  value = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
  description = "The security group ID attached to the EKS cluster"
}

output "cluster_iam_role_arn" {
  value = aws_eks_cluster.this.role_arn
  description = "The IAM role ARN used by the EKS cluster"
}