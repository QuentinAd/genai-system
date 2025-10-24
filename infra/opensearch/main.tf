locals {
  domain_name      = "${var.project_name}-${var.environment}-hirag"
  log_group_name   = "/aws/opensearch/${local.domain_name}"
  security_group_name = "${local.domain_name}-sg"
  secret_name      = "${var.project_name}/${var.environment}/hirag/opensearch"
  tags = {
    Project     = var.project_name
    Environment = var.environment
    Service     = "hirag"
    Component   = "opensearch"
  }

  index_body = jsonencode({
    settings = {
      index = {
        number_of_shards   = 3
        number_of_replicas = 1
        refresh_interval   = "1s"
        knn                = true
      }
      knn = {
        engine = "nmslib"
      }
    }
    mappings = {
      properties = {
        id = { type = "keyword" }
        document_type = { type = "keyword" }
        namespace = { type = "keyword" }
        text = { type = "text" }
        metadata = { type = "object" }
        embedding = {
          type = "knn_vector"
          dimension = var.embedding_dimensions
          method = {
            name       = "hnsw"
            space_type = "cosinesimil"
            engine     = "nmslib"
            parameters = {
              m   = 16
              ef_construction = 200
            }
          }
        }
        created_at = {
          type   = "date"
          format = "strict_date_optional_time||epoch_millis"
        }
      }
    }
  })
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

resource "aws_iam_service_linked_role" "opensearch" {
  aws_service_name = "opensearchservice.amazonaws.com"
}

resource "random_password" "domain_master" {
  length  = 24
  special = true
  override_special = "!@#%^*-_=+"
}

resource "aws_security_group" "opensearch" {
  name        = local.security_group_name
  description = "OpenSearch VPC access"
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTPS access scoped to VPC CIDR"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, { Name = local.security_group_name })
}

resource "aws_cloudwatch_log_group" "opensearch" {
  name              = local.log_group_name
  retention_in_days = 14
  tags              = local.tags
}

resource "aws_opensearch_domain" "hirag" {
  domain_name    = local.domain_name
  engine_version = "OpenSearch_2.11"

  depends_on = [aws_iam_service_linked_role.opensearch]

  cluster_config {
    instance_type          = var.domain_instance_type
    instance_count         = var.domain_instance_count
    zone_awareness_enabled = true
    zone_awareness_config {
      availability_zone_count = min(length(var.subnet_ids), 2)
    }
  }

  vpc_options {
    subnet_ids         = var.subnet_ids
    security_group_ids = [aws_security_group.opensearch.id]
  }

  ebs_options {
    ebs_enabled = true
    volume_type = "gp3"
    volume_size = var.ebs_volume_size
  }

  encrypt_at_rest {
    enabled = true
  }

  node_to_node_encryption {
    enabled = true
  }

  domain_endpoint_options {
    enforce_https       = true
    tls_security_policy = "Policy-Min-TLS-1-2-2019-07"
  }

  advanced_security_options {
    enabled                        = true
    internal_user_database_enabled = true
    master_user_options {
      master_user_name     = var.domain_admin_username
      master_user_password = random_password.domain_master.result
    }
  }

  log_publishing_options {
    cloudwatch_log_group_arn = aws_cloudwatch_log_group.opensearch.arn
    log_type                 = "INDEX_SLOW_LOGS"
  }

  log_publishing_options {
    cloudwatch_log_group_arn = aws_cloudwatch_log_group.opensearch.arn
    log_type                 = "SEARCH_SLOW_LOGS"
  }

  access_policies = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = "*"
        Action = "es:*"
        Resource = format("arn:%s:es:%s:%s:domain/%s/*", data.aws_partition.current.partition, var.aws_region, data.aws_caller_identity.current.account_id, local.domain_name)
        Condition = {
          IpAddress = {
            "aws:SourceIp" = [var.vpc_cidr]
          }
        }
      }
    ]
  })

  tags = local.tags
}

resource "aws_cloudwatch_metric_alarm" "cluster_cpu" {
  alarm_name          = "${local.domain_name}-cpu"
  alarm_description   = "OpenSearch CPU utilization high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ES"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
  ok_actions          = var.alarm_actions

  dimensions = {
    DomainName = aws_opensearch_domain.hirag.domain_name
    ClientId   = data.aws_caller_identity.current.account_id
  }
}

resource "aws_secretsmanager_secret" "opensearch" {
  name = local.secret_name
  tags = local.tags
}

resource "aws_secretsmanager_secret_version" "opensearch" {
  secret_id     = aws_secretsmanager_secret.opensearch.id
  secret_string = jsonencode({
    endpoint  = aws_opensearch_domain.hirag.endpoint
    username  = var.domain_admin_username
    password  = random_password.domain_master.result
    index     = var.index_name
  })
}

resource "null_resource" "create_index" {
  triggers = {
    domain_endpoint = aws_opensearch_domain.hirag.endpoint
    index_name      = var.index_name
    index_body_hash = sha1(local.index_body)
    admin_username  = var.domain_admin_username
    admin_password  = random_password.domain_master.result
  }

  provisioner "local-exec" {
    when    = create
    command = <<EOT
curl --fail -s -X PUT "https://${self.triggers.domain_endpoint}/${self.triggers.index_name}" \
  -H 'Content-Type: application/json' \
  -u '${self.triggers.admin_username}:${self.triggers.admin_password}' \
  -d '${local.index_body}'
EOT
  }

  provisioner "local-exec" {
    when    = destroy
    command = <<EOT
curl --fail -s -X DELETE "https://${self.triggers.domain_endpoint}/${self.triggers.index_name}" \
  -u '${self.triggers.admin_username}:${self.triggers.admin_password}' || true
EOT
  }
}
