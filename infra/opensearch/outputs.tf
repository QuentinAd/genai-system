output "opensearch_domain_endpoint" {
  description = "HTTPS endpoint for the HiRAG OpenSearch domain"
  value       = aws_opensearch_domain.hirag.endpoint
}

output "opensearch_domain_arn" {
  description = "ARN for the HiRAG OpenSearch domain"
  value       = aws_opensearch_domain.hirag.arn
}

output "opensearch_security_group_id" {
  description = "Security group applied to the OpenSearch domain"
  value       = aws_security_group.opensearch.id
}

output "opensearch_admin_secret_arn" {
  description = "Secrets Manager ARN containing OpenSearch credentials"
  value       = aws_secretsmanager_secret.opensearch.arn
}
