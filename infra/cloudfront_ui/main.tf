locals {
  bucket_name = "${var.project_name}-${var.environment}-ui"
  tags = {
    Project     = var.project_name
    Environment = var.environment
    Component   = "ui"
  }
}

resource "aws_s3_bucket" "ui" {
  bucket        = local.bucket_name
  force_destroy = true
  tags          = merge(local.tags, { Name = local.bucket_name })
}

resource "aws_s3_bucket_versioning" "ui" {
  bucket = aws_s3_bucket.ui.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "ui" {
  bucket = aws_s3_bucket.ui.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "ui" {
  bucket                  = aws_s3_bucket.ui.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "ui" {
  bucket = aws_s3_bucket.ui.id
  policy = data.aws_iam_policy_document.ui_bucket.json
}

data "aws_iam_policy_document" "ui_bucket" {
  statement {
    sid    = "AllowCloudFrontOAI"
    effect = "Allow"

    principals {
      type        = "CanonicalUser"
      identifiers = [aws_cloudfront_origin_access_identity.ui.s3_canonical_user_id]
    }

    actions = ["s3:GetObject"]

    resources = ["${aws_s3_bucket.ui.arn}/*"]
  }
}

resource "aws_cloudfront_origin_access_identity" "ui" {
  comment = "${var.project_name}-${var.environment}-ui"
}

resource "aws_cloudfront_distribution" "ui" {
  enabled             = true
  comment             = "${var.project_name}-${var.environment}-ui"
  default_root_object = "index.html"
  price_class         = var.price_class

  origin {
    domain_name = aws_s3_bucket.ui.bucket_regional_domain_name
    origin_id   = "ui-s3-origin"

    s3_origin_config {
      origin_access_identity = aws_cloudfront_origin_access_identity.ui.cloudfront_access_identity_path
    }
  }

  default_cache_behavior {
    target_origin_id       = "ui-s3-origin"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl                = var.min_cache_ttl
    default_ttl            = var.default_cache_ttl
    max_ttl                = var.max_cache_ttl
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
    minimum_protocol_version       = "TLSv1.2_2021"
  }

  tags = local.tags
}
