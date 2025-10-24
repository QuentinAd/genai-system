variable "project_name" {
  description = "Project name used for tagging and resource names."
  type        = string
}

variable "environment" {
  description = "Deployment environment (e.g., dev, staging, prod)."
  type        = string
}

variable "aws_region" {
  description = "AWS region for OpenSearch resources."
  type        = string
}

variable "vpc_id" {
  description = "VPC identifier for VPC-enabled OpenSearch."
  type        = string
}

variable "vpc_cidr" {
  description = "Primary CIDR block for the VPC to use as a fallback ingress rule."
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for OpenSearch VPC endpoints."
  type        = list(string)
}

variable "domain_instance_type" {
  description = "Instance type for OpenSearch data nodes."
  type        = string
  default     = "m6g.large.search"
}

variable "domain_instance_count" {
  description = "Number of OpenSearch data nodes."
  type        = number
  default     = 2

  validation {
    condition     = var.domain_instance_count % 2 == 0
    error_message = "domain_instance_count must be an even number when zone awareness is enabled."
  }
}

variable "create_service_linked_role" {
  description = "Whether to create the OpenSearch service-linked role. Set to true for first-time setup."
  type        = bool
  default     = false
}

variable "ebs_volume_size" {
  description = "Size in GiB for OpenSearch EBS volumes."
  type        = number
  default     = 200
}

variable "domain_admin_username" {
  description = "Username for the internal master user configured on the domain."
  type        = string
  default     = "hirag_admin"
}

variable "index_name" {
  description = "Primary OpenSearch index name for HiRAG embeddings."
  type        = string
  default     = "hirag_embeddings"
}

variable "embedding_dimensions" {
  description = "Dimension of the embedding vectors for the HiRAG index."
  type        = number
  default     = 1536
}

variable "enable_ultrawarm" {
  description = "Toggle UltraWarm storage for the domain."
  type        = bool
  default     = false
}

variable "alarm_actions" {
  description = "Optional list of ARNs for alarm notifications."
  type        = list(string)
  default     = []
}
