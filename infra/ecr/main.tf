resource "aws_ecr_repository" "this" {
  name = var.ecr_repo

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Project = var.project_name
  }
}
