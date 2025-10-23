locals {
  cluster_identifier = "${var.project_name}-${var.environment}-hirag-neptune"
  subnet_group_name  = "${var.project_name}-${var.environment}-hirag-neptune-subnet"
  secret_name        = "${var.project_name}/${var.environment}/hirag/neptune-endpoints"
  ingest_bucket_name = "${var.project_name}-${var.environment}-neptune-ingest"
  tags = {
    Project     = var.project_name
    Environment = var.environment
    Service     = "hirag"
    Component   = "neptune"
  }
}

resource "aws_security_group" "neptune" {
  name        = "${local.cluster_identifier}-sg"
  description = "Neptune access within VPC"
  vpc_id      = var.vpc_id

  ingress {
    description = "Gremlin/SPARQL access from inside the VPC"
    from_port   = var.neptune_port
    to_port     = var.neptune_port
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, { Name = "${local.cluster_identifier}-sg" })
}

resource "aws_neptune_subnet_group" "hirag" {
  name       = local.subnet_group_name
  subnet_ids = var.private_subnet_ids
  tags       = merge(local.tags, { Name = local.subnet_group_name })
}

resource "aws_neptune_cluster_parameter_group" "lab_mode" {
  name   = "${local.cluster_identifier}-pg"
  family = "neptune1"

  parameter {
    name  = "neptune_dfe_query_engine"
    value = "1"
  }

  parameter {
    name  = "neptune_ml_enabled"
    value = "1"
  }

  tags = local.tags
}

resource "aws_neptune_cluster" "hirag" {
  cluster_identifier                  = local.cluster_identifier
  neptune_subnet_group_name           = aws_neptune_subnet_group.hirag.name
  vpc_security_group_ids              = [aws_security_group.neptune.id]
  engine                              = "neptune"
  backup_retention_period             = var.backups_retention_days
  preferred_backup_window             = var.preferred_backup_window
  apply_immediately                   = true
  iam_database_authentication_enabled = true
  storage_encrypted                   = true
  neptune_cluster_parameter_group_name = aws_neptune_cluster_parameter_group.lab_mode.name
  deletion_protection                 = true
  skip_final_snapshot                 = false
  final_snapshot_identifier           = "${replace(local.cluster_identifier, "-", "")}-final"

  tags = local.tags
}

resource "aws_neptune_cluster_instance" "primary" {
  cluster_identifier = aws_neptune_cluster.hirag.id
  instance_class     = var.neptune_instance_class
  engine             = "neptune"
  apply_immediately  = true
  tags               = merge(local.tags, { Role = "primary" })
}

resource "aws_s3_bucket" "neptune_ingest" {
  bucket        = local.ingest_bucket_name
  force_destroy = var.neptune_ingest_bucket_force_destroy
  tags          = merge(local.tags, { Name = local.ingest_bucket_name })
}

resource "aws_s3_bucket_versioning" "neptune_ingest" {
  bucket = aws_s3_bucket.neptune_ingest.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "neptune_ingest" {
  bucket = aws_s3_bucket.neptune_ingest.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "neptune_ingest" {
  bucket = aws_s3_bucket.neptune_ingest.id

  rule {
    id     = "archive-ingest"
    status = "Enabled"

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 90
      storage_class = "GLACIER"
    }
  }
}

resource "aws_secretsmanager_secret" "neptune" {
  name = local.secret_name
  tags = local.tags
}

resource "aws_secretsmanager_secret_version" "neptune" {
  secret_id     = aws_secretsmanager_secret.neptune.id
  secret_string = jsonencode({
    endpoint        = aws_neptune_cluster.hirag.endpoint,
    reader_endpoint = aws_neptune_cluster.hirag.reader_endpoint,
    port            = var.neptune_port
  })
}

resource "aws_neptune_graph" "analytics" {
  count      = var.enable_analytics ? 1 : 0
  graph_name = "${var.project_name}-${var.environment}-hirag"
  graph_type = "PROPERTY_GRAPH"

  provisioned_capacity {
    read_capacity  = 2
    write_capacity = 2
  }

  tags = merge(local.tags, { Component = "neptune-analytics" })
}
