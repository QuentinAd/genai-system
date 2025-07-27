
resource "aws_s3_bucket" "data_bucket" {
  bucket = "${var.project_name}-data"
  force_destroy = true
}

resource "aws_s3_bucket" "dags_bucket" {
  bucket = "${var.project_name}-dags"
  force_destroy = true
}

output "dags_bucket_name" {
  value = aws_s3_bucket.dags_bucket.id
}

output "data_bucket_name" {
  value = aws_s3_bucket.data_bucket.id
}
