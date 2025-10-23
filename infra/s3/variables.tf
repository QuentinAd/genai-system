variable "project_name" {
  description = "Name of the project"
  type        = string
}

variable "environment" {
  description = "Deployment environment for tagging and naming"
  type        = string
}

variable "ingest_transition_days" {
  description = "Days before moving ingestion objects to infrequent access storage"
  type        = number
  default     = 30
}

variable "ingest_glacier_days" {
  description = "Days before transitioning ingestion objects to Glacier"
  type        = number
  default     = 90
}
