
variable "aws_region" {
  default = "ca-central-1"
}

variable "project_name" {
  default = "rbc-interview"
}

variable "environment" {
  description = "Environment for the infrastructure (e.g., dev, prod)"
  type        = string
  default     = "dev"
}
