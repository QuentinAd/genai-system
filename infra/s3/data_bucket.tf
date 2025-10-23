locals {
  tags = {
    Project     = var.project_name
    Environment = var.environment
  }

  hirag_ingest_bucket = "${var.project_name}-${var.environment}-hirag-ingestion"
  hirag_archive_prefix = "archive/"
}

resource "aws_s3_bucket" "data_bucket" {
  bucket        = "${var.project_name}-data"
  force_destroy = true
  tags          = merge(local.tags, { Name = "${var.project_name}-data" })
}

resource "aws_s3_bucket_versioning" "data_bucket" {
  bucket = aws_s3_bucket.data_bucket.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data_bucket" {
  bucket = aws_s3_bucket.data_bucket.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "data_bucket" {
  bucket                  = aws_s3_bucket.data_bucket.id
  block_public_acls       = true
  block_public_policy     = true
  restrict_public_buckets = true
  ignore_public_acls      = true
}

resource "aws_s3_bucket" "dags_bucket" {
  bucket        = "${var.project_name}-dags"
  force_destroy = true
  tags          = merge(local.tags, { Name = "${var.project_name}-dags" })
}

resource "aws_s3_bucket_versioning" "dags_bucket" {
  bucket = aws_s3_bucket.dags_bucket.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "dags_bucket" {
  bucket = aws_s3_bucket.dags_bucket.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "dags_bucket" {
  bucket                  = aws_s3_bucket.dags_bucket.id
  block_public_acls       = true
  block_public_policy     = true
  restrict_public_buckets = true
  ignore_public_acls      = true
}

resource "aws_s3_bucket" "hirag_ingestion" {
  bucket        = local.hirag_ingest_bucket
  tags          = merge(local.tags, { Name = local.hirag_ingest_bucket, Purpose = "hirag-ingest" })
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "hirag_ingestion" {
  bucket = aws_s3_bucket.hirag_ingestion.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "hirag_ingestion" {
  bucket = aws_s3_bucket.hirag_ingestion.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "hirag_ingestion" {
  bucket                  = aws_s3_bucket.hirag_ingestion.id
  block_public_acls       = true
  block_public_policy     = true
  restrict_public_buckets = true
  ignore_public_acls      = true
}

resource "aws_s3_bucket_lifecycle_configuration" "hirag_ingestion" {
  bucket = aws_s3_bucket.hirag_ingestion.id

  rule {
    id     = "transition-ingest"
    status = "Enabled"

    transition {
      days          = var.ingest_transition_days
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = var.ingest_glacier_days
      storage_class = "GLACIER"
    }
  }
}

# Placeholders for common prefixes used by Airflow DAGs
resource "aws_s3_object" "hirag_archive_prefix" {
  bucket       = aws_s3_bucket.hirag_ingestion.id
  key          = local.hirag_archive_prefix
  content      = ""
  content_type = "application/x-directory"
}

output "dags_bucket_name" {
  value = aws_s3_bucket.dags_bucket.id
}

output "data_bucket_name" {
  value = aws_s3_bucket.data_bucket.id
}

output "hirag_ingestion_bucket_name" {
  description = "Bucket receiving HiRAG source documents"
  value       = aws_s3_bucket.hirag_ingestion.id
}

output "hirag_archive_prefix" {
  description = "Prefix within the ingestion bucket used for archival"
  value       = local.hirag_archive_prefix
}
