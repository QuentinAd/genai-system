resource "aws_ecr_repository" "this" {
  name                 = var.ecr_repo
  image_scanning_configuration {
    scan_on_push = true
  }
  tags = {
    Project = var.project_name
  }
}

output "repository_url" {
  value = aws_ecr_repository.this.repository_url
}
