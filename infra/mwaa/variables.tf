variable "project_name" {
  description = "Name of the project"
  type        = string
}

variable "dags_bucket_name" {
  description = "Name of the S3 bucket containing DAGs"
  type        = string
}

variable "data_bucket_name" {
  description = "Name of the S3 bucket for input/output data"
  type        = string
}

variable "private_subnets" {
  description = "List of subnet IDs to use for MWAA networking"
  type        = list(string)
}

variable "vpc_id" {
  description = "VPC ID for the MWAA environment"
  type        = string
}

