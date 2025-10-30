output "lambda_function_name" {
  description = "Name of the backend Lambda function."
  value       = aws_lambda_function.backend.function_name
}

output "lambda_function_arn" {
  description = "ARN of the backend Lambda function."
  value       = aws_lambda_function.backend.arn
}

output "lambda_function_url" {
  description = "Public Function URL for the backend Lambda."
  value       = aws_lambda_function_url.backend.function_url
}

output "lambda_role_arn" {
  description = "IAM role ARN assumed by the backend Lambda."
  value       = aws_iam_role.lambda.arn
}

output "log_group_name" {
  description = "CloudWatch log group capturing Lambda logs."
  value       = aws_cloudwatch_log_group.lambda.name
}

output "security_group_id" {
  description = "Security group ID created for the Lambda function, if applicable."
  value       = length(aws_security_group.lambda) > 0 ? aws_security_group.lambda[0].id : null
}
