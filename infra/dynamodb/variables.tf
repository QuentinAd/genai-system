variable "project_name" {
  description = "Project name used for resource naming."
  type        = string
}

variable "environment" {
  description = "Deployment environment (e.g., dev, prod)."
  type        = string
}

variable "kv_ttl_attribute" {
  description = "Attribute name used for TTL on the hirag_kv table."
  type        = string
  default     = "expires_at"
}

variable "alarm_read_threshold" {
  description = "Consumed read capacity threshold before raising an alarm."
  type        = number
  default     = 5000
}

variable "alarm_write_threshold" {
  description = "Consumed write capacity threshold before raising an alarm."
  type        = number
  default     = 5000
}

variable "alarm_evaluation_periods" {
  description = "Number of evaluation periods for DynamoDB capacity alarms."
  type        = number
  default     = 1
}

variable "alarm_period_seconds" {
  description = "Period in seconds for DynamoDB capacity alarms."
  type        = number
  default     = 300
}

variable "alarm_actions" {
  description = "ARNs for SNS topics or other actions triggered by DynamoDB alarms."
  type        = list(string)
  default     = []
}
