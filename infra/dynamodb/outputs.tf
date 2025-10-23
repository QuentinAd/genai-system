output "hirag_kv_table_name" {
  description = "Name of the hirag_kv DynamoDB table"
  value       = aws_dynamodb_table.hirag_kv.name
}

output "hirag_kv_table_arn" {
  description = "ARN of the hirag_kv DynamoDB table"
  value       = aws_dynamodb_table.hirag_kv.arn
}

output "chat_history_table_name" {
  description = "Name of the chat_history DynamoDB table"
  value       = aws_dynamodb_table.chat_history.name
}

output "chat_history_table_arn" {
  description = "ARN of the chat_history DynamoDB table"
  value       = aws_dynamodb_table.chat_history.arn
}

output "airflow_policy_arn" {
  description = "IAM policy ARN granting Airflow access to HiRAG DynamoDB tables"
  value       = aws_iam_policy.airflow_dynamodb.arn
}

output "backend_policy_arn" {
  description = "IAM policy ARN granting backend services access to HiRAG DynamoDB tables"
  value       = aws_iam_policy.backend_dynamodb.arn
}
