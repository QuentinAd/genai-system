output "neptune_cluster_endpoint" {
  description = "Writer endpoint for the Neptune cluster"
  value       = aws_neptune_cluster.hirag.endpoint
}

output "neptune_reader_endpoint" {
  description = "Reader endpoint for the Neptune cluster"
  value       = aws_neptune_cluster.hirag.reader_endpoint
}

output "neptune_security_group_id" {
  description = "Security group protecting Neptune"
  value       = aws_security_group.neptune.id
}

output "neptune_secret_arn" {
  description = "Secrets Manager ARN storing Neptune endpoints"
  value       = aws_secretsmanager_secret.neptune.arn
}

output "neptune_ingest_bucket_name" {
  description = "S3 bucket used for Neptune bulk loader jobs"
  value       = aws_s3_bucket.neptune_ingest.id
}
