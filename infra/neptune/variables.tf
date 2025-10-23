variable "project_name" {
  description = "Project name used for tagging and resource names."
  type        = string
}

variable "environment" {
  description = "Deployment environment (e.g., dev, staging, prod)."
  type        = string
}

variable "aws_region" {
  description = "AWS region for Neptune resources."
  type        = string
}

variable "vpc_id" {
  description = "VPC identifier where Neptune will be provisioned."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for Neptune subnet group."
  type        = list(string)
}

variable "vpc_cidr" {
  description = "CIDR block of the VPC to scope Neptune security group ingress."
  type        = string
}

variable "neptune_instance_class" {
  description = "Instance class for the primary Neptune instance."
  type        = string
  default     = "db.r6g.large"
}

variable "backups_retention_days" {
  description = "Number of days to retain automated Neptune backups."
  type        = number
  default     = 7
}

variable "preferred_backup_window" {
  description = "Preferred automated backup window for Neptune (UTC)."
  type        = string
  default     = "05:00-07:00"
}

variable "neptune_port" {
  description = "Port Neptune listens on for Gremlin/SPARQL queries."
  type        = number
  default     = 8182
}


variable "neptune_ingest_bucket_force_destroy" {
  description = "Allow Terraform to delete the Neptune ingest bucket even when non-empty."
  type        = bool
  default     = false
}
