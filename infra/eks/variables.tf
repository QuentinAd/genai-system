
variable "project_name" {
  description = "Name prefix for all EKS resources"
  type        = string
}

variable "environment" {
  description = "Environment for the EKS cluster (e.g., dev, prod)"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID to launch EKS in"
  type        = string
}

variable "subnet_ids" {
  description = "Subnets for worker nodes"
  type        = list(string)
}
