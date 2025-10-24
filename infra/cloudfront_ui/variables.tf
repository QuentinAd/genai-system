variable "project_name" {
  description = "Project name used for resource naming."
  type        = string
}

variable "environment" {
  description = "Deployment environment identifier (e.g., dev, prod)."
  type        = string
}

variable "default_cache_ttl" {
  description = "Default cache TTL for CloudFront (seconds)."
  type        = number
  default     = 3600
}

variable "max_cache_ttl" {
  description = "Maximum cache TTL for CloudFront (seconds)."
  type        = number
  default     = 86400
}

variable "min_cache_ttl" {
  description = "Minimum cache TTL for CloudFront (seconds)."
  type        = number
  default     = 0
}

variable "price_class" {
  description = "CloudFront price class."
  type        = string
  default     = "PriceClass_100"
}
