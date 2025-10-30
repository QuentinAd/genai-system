variable "project_name" {
  description = "Project name used for tagging and resource names."
  type        = string
}

variable "environment" {
  description = "Deployment environment (e.g., dev, staging, prod)."
  type        = string
}

variable "aws_region" {
  description = "AWS region where the Lambda function will run."
  type        = string
}

variable "lambda_image_uri" {
  description = "Fully qualified ECR image URI for the backend Lambda container."
  type        = string
}

variable "lambda_function_name" {
  description = "Optional explicit name for the Lambda function."
  type        = string
  default     = ""
}

variable "memory_size" {
  description = "Lambda memory allocation in MB."
  type        = number
  default     = 1024
}

variable "timeout" {
  description = "Lambda timeout in seconds."
  type        = number
  default     = 30
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention period."
  type        = number
  default     = 14
}

variable "environment_variables" {
  description = "Environment variables to inject into the Lambda runtime."
  type        = map(string)
  default     = {}
}

variable "vpc_id" {
  description = "VPC identifier for optional Lambda VPC networking."
  type        = string
  default     = ""
}

variable "subnet_ids" {
  description = "Subnet IDs for Lambda VPC configuration."
  type        = list(string)
  default     = []
}

variable "security_group_ids" {
  description = "Security group IDs to associate with the Lambda when VPC enabled."
  type        = list(string)
  default     = []
}

variable "create_security_group" {
  description = "Whether to create a dedicated security group when Lambda is placed in a VPC."
  type        = bool
  default     = true
}

variable "cors_allowed_origins" {
  description = "Origins allowed by the Lambda Function URL CORS configuration."
  type        = list(string)
  default     = ["*"]
}

variable "cors_allowed_headers" {
  description = "Headers allowed by the Lambda Function URL CORS configuration."
  type        = list(string)
  default     = ["*"]
}

variable "cors_allowed_methods" {
  description = "HTTP methods allowed by the Lambda Function URL CORS configuration."
  type        = list(string)
  default     = ["GET", "POST", "OPTIONS"]
}

variable "cors_expose_headers" {
  description = "Response headers exposed by the Lambda Function URL CORS configuration."
  type        = list(string)
  default     = []
}

variable "cors_max_age" {
  description = "Max age in seconds for cached CORS preflight responses."
  type        = number
  default     = 86400
}

variable "managed_policy_arns" {
  description = "Additional managed IAM policies to attach to the Lambda role."
  type        = list(string)
  default     = []
}

variable "dynamodb_table_arns" {
  description = "DynamoDB table ARNs requiring direct access."
  type        = list(string)
  default     = []
}

variable "neptune_resource_arns" {
  description = "Neptune resource ARNs permitting neptune-db:connect."
  type        = list(string)
  default     = []
}

variable "secrets_manager_arns" {
  description = "Secrets Manager ARNs the Lambda must fetch."
  type        = list(string)
  default     = []
}

variable "opensearch_resource_arns" {
  description = "OpenSearch resource ARNs permitted for HTTP access."
  type        = list(string)
  default     = []
}

variable "kms_key_arns" {
  description = "KMS keys the Lambda must decrypt."
  type        = list(string)
  default     = []
}

variable "enable_alarms" {
  description = "Whether to create CloudWatch alarms for Lambda errors and latency."
  type        = bool
  default     = false
}

variable "alarm_topic_arn" {
  description = "Optional SNS topic ARN to notify when alarms fire."
  type        = string
  default     = ""
}
