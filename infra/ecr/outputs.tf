output "repository_url" {
  value = aws_ecr_repository.this.repository_url
  description = "The URL of the ECR repository"
}

output "repository_name" {
  value = aws_ecr_repository.this.name
  description = "The name of the ECR repository"
}

output "registry_id" {
  value = aws_ecr_repository.this.registry_id
  description = "The registry ID where the repository was created"
}