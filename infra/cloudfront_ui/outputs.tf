output "ui_bucket_name" {
  description = "S3 bucket name hosting the UI static assets"
  value       = aws_s3_bucket.ui.id
}

output "ui_distribution_id" {
  description = "CloudFront distribution ID for the UI"
  value       = aws_cloudfront_distribution.ui.id
}

output "ui_distribution_domain_name" {
  description = "CloudFront domain name serving the UI"
  value       = aws_cloudfront_distribution.ui.domain_name
}
