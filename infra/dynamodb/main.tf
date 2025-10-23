locals {
  kv_table_name          = "${var.project_name}-${var.environment}-hirag-kv"
  chat_history_tableName = "${var.project_name}-${var.environment}-chat-history"
  table_tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

resource "aws_dynamodb_table" "hirag_kv" {
  name         = local.kv_table_name
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "namespace"
  range_key = "key"

  attribute {
    name = "namespace"
    type = "S"
  }

  attribute {
    name = "key"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  ttl {
    attribute_name = var.kv_ttl_attribute
    enabled        = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = merge(local.table_tags, {
    Table = "hirag_kv"
  })
}

resource "aws_dynamodb_table" "chat_history" {
  name         = local.chat_history_tableName
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "session_id"
  range_key = "ts"

  attribute {
    name = "session_id"
    type = "S"
  }

  attribute {
    name = "ts"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = merge(local.table_tags, {
    Table = "chat_history"
  })
}

# Alarm helpers keep settings consistent across tables.
locals {
  alarm_common = {
    comparison_operator = "GreaterThanThreshold"
    evaluation_periods  = var.alarm_evaluation_periods
    period              = var.alarm_period_seconds
    statistic           = "Sum"
    treat_missing_data  = "notBreaching"
  }
}

resource "aws_cloudwatch_metric_alarm" "hirag_kv_read_capacity" {
  alarm_name          = "${local.kv_table_name}-read-capacity"
  alarm_description   = "Hirag KV table consumed read capacity exceeded threshold"
  threshold           = var.alarm_read_threshold
  actions_enabled     = length(var.alarm_actions) > 0
  alarm_actions       = var.alarm_actions
  ok_actions          = var.alarm_actions

  metric_name = "ConsumedReadCapacityUnits"
  namespace   = "AWS/DynamoDB"
  dimensions = {
    TableName = aws_dynamodb_table.hirag_kv.name
  }

  # Merge defaults with resource-specific overrides.
  comparison_operator = local.alarm_common.comparison_operator
  evaluation_periods  = local.alarm_common.evaluation_periods
  period              = local.alarm_common.period
  statistic           = local.alarm_common.statistic
  treat_missing_data  = local.alarm_common.treat_missing_data
}

resource "aws_cloudwatch_metric_alarm" "hirag_kv_write_capacity" {
  alarm_name          = "${local.kv_table_name}-write-capacity"
  alarm_description   = "Hirag KV table consumed write capacity exceeded threshold"
  threshold           = var.alarm_write_threshold
  actions_enabled     = length(var.alarm_actions) > 0
  alarm_actions       = var.alarm_actions
  ok_actions          = var.alarm_actions

  metric_name = "ConsumedWriteCapacityUnits"
  namespace   = "AWS/DynamoDB"
  dimensions = {
    TableName = aws_dynamodb_table.hirag_kv.name
  }

  comparison_operator = local.alarm_common.comparison_operator
  evaluation_periods  = local.alarm_common.evaluation_periods
  period              = local.alarm_common.period
  statistic           = local.alarm_common.statistic
  treat_missing_data  = local.alarm_common.treat_missing_data
}

resource "aws_cloudwatch_metric_alarm" "chat_history_read_capacity" {
  alarm_name          = "${local.chat_history_tableName}-read-capacity"
  alarm_description   = "Chat history table consumed read capacity exceeded threshold"
  threshold           = var.alarm_read_threshold
  actions_enabled     = length(var.alarm_actions) > 0
  alarm_actions       = var.alarm_actions
  ok_actions          = var.alarm_actions

  metric_name = "ConsumedReadCapacityUnits"
  namespace   = "AWS/DynamoDB"
  dimensions = {
    TableName = aws_dynamodb_table.chat_history.name
  }

  comparison_operator = local.alarm_common.comparison_operator
  evaluation_periods  = local.alarm_common.evaluation_periods
  period              = local.alarm_common.period
  statistic           = local.alarm_common.statistic
  treat_missing_data  = local.alarm_common.treat_missing_data
}

resource "aws_cloudwatch_metric_alarm" "chat_history_write_capacity" {
  alarm_name          = "${local.chat_history_tableName}-write-capacity"
  alarm_description   = "Chat history table consumed write capacity exceeded threshold"
  threshold           = var.alarm_write_threshold
  actions_enabled     = length(var.alarm_actions) > 0
  alarm_actions       = var.alarm_actions
  ok_actions          = var.alarm_actions

  metric_name = "ConsumedWriteCapacityUnits"
  namespace   = "AWS/DynamoDB"
  dimensions = {
    TableName = aws_dynamodb_table.chat_history.name
  }

  comparison_operator = local.alarm_common.comparison_operator
  evaluation_periods  = local.alarm_common.evaluation_periods
  period              = local.alarm_common.period
  statistic           = local.alarm_common.statistic
  treat_missing_data  = local.alarm_common.treat_missing_data
}

# Policies for Airflow and backend services. Caller attaches them to roles.
resource "aws_iam_policy" "airflow_dynamodb" {
  name        = "${var.project_name}-${var.environment}-airflow-hirag-dynamodb"
  description = "Least-privilege DynamoDB access for HiRAG Airflow ingestion"
  policy      = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = [
          "dynamodb:BatchGetItem",
          "dynamodb:BatchWriteItem",
          "dynamodb:DescribeTable",
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:UpdateItem"
        ]
        Resource = [
          aws_dynamodb_table.hirag_kv.arn,
          aws_dynamodb_table.chat_history.arn
        ]
      }
    ]
  })
}

resource "aws_iam_policy" "backend_dynamodb" {
  name        = "${var.project_name}-${var.environment}-backend-hirag-dynamodb"
  description = "Least-privilege DynamoDB access for backend chat services"
  policy      = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = [
          "dynamodb:BatchGetItem",
          "dynamodb:DescribeTable",
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:UpdateItem"
        ]
        Resource = [
          aws_dynamodb_table.hirag_kv.arn,
          aws_dynamodb_table.chat_history.arn
        ]
      }
    ]
  })
}
