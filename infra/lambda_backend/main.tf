locals {
  base_name   = "${var.project_name}-${var.environment}-backend"
  lambda_name = trimspace(var.lambda_function_name) != "" ? var.lambda_function_name : local.base_name
  tags = {
    Project     = var.project_name
    Environment = var.environment
    Service     = "backend"
    Component   = "lambda"
  }
  use_vpc                 = length(var.subnet_ids) > 0
  security_group_required = local.use_vpc && length(var.security_group_ids) == 0 && var.create_security_group && trimspace(var.vpc_id) != ""
  environment_variables   = merge(var.environment_variables, { AWS_REGION = var.aws_region })
  managed_policy_arns     = toset([for arn in var.managed_policy_arns : arn if trimspace(arn) != ""])
  policy_statements = concat(
    length(var.dynamodb_table_arns) > 0 ? [
      {
        Sid    = "DynamoAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:BatchGetItem",
          "dynamodb:BatchWriteItem",
          "dynamodb:DescribeTable",
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:UpdateItem"
        ]
        Resource = var.dynamodb_table_arns
      }
    ] : [],
    length(var.opensearch_resource_arns) > 0 ? [
      {
        Sid    = "OpenSearchHttpAccess"
        Effect = "Allow"
        Action = [
          "es:ESHttpGet",
          "es:ESHttpPost",
          "es:ESHttpPut",
          "es:ESHttpDelete"
        ]
        Resource = var.opensearch_resource_arns
      }
    ] : [],
    length(var.neptune_resource_arns) > 0 ? [
      {
        Sid    = "NeptuneConnect"
        Effect = "Allow"
        Action = [
          "neptune-db:connect"
        ]
        Resource = var.neptune_resource_arns
      }
    ] : [],
    length(var.secrets_manager_arns) > 0 ? [
      {
        Sid    = "SecretsAccess"
        Effect = "Allow"
        Action = [
          "secretsmanager:DescribeSecret",
          "secretsmanager:GetSecretValue"
        ]
        Resource = var.secrets_manager_arns
      }
    ] : [],
    length(var.kms_key_arns) > 0 ? [
      {
        Sid    = "KmsDecrypt"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:DescribeKey"
        ]
        Resource = var.kms_key_arns
      }
    ] : []
  )
  cors_allowed_origins = length(var.cors_allowed_origins) > 0 ? var.cors_allowed_origins : ["*"]
  cors_allowed_headers = length(var.cors_allowed_headers) > 0 ? var.cors_allowed_headers : ["*"]
  cors_allowed_methods = length(var.cors_allowed_methods) > 0 ? var.cors_allowed_methods : ["GET", "POST", "OPTIONS"]
}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_security_group" "lambda" {
  count       = local.security_group_required ? 1 : 0
  name        = "${local.lambda_name}-sg"
  description = "Security group for ${local.lambda_name} Lambda function"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, { Name = "${local.lambda_name}-sg" })
}

resource "aws_iam_role" "lambda" {
  name               = "${replace(local.lambda_name, " ", "-")}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "basic_execution" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "vpc_execution" {
  count      = local.use_vpc ? 1 : 0
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy_attachment" "managed" {
  for_each   = local.managed_policy_arns
  role       = aws_iam_role.lambda.name
  policy_arn = each.value
}

resource "aws_iam_role_policy" "lambda_access" {
  count = length(local.policy_statements) > 0 ? 1 : 0
  name  = "${replace(local.lambda_name, " ", "-")}-access"
  role  = aws_iam_role.lambda.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = local.policy_statements
  })
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.lambda_name}"
  retention_in_days = var.log_retention_days
  tags              = local.tags
}

resource "aws_lambda_function" "backend" {
  function_name = local.lambda_name
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = var.lambda_image_uri
  memory_size   = var.memory_size
  timeout       = var.timeout
  architectures = ["x86_64"]
  publish       = false

  environment {
    variables = local.environment_variables
  }

  dynamic "vpc_config" {
    for_each = local.use_vpc ? [true] : []
    content {
      subnet_ids         = var.subnet_ids
      security_group_ids = length(var.security_group_ids) > 0 ? var.security_group_ids : aws_security_group.lambda[*].id
    }
  }

  tags = local.tags

  depends_on = [
    aws_cloudwatch_log_group.lambda
  ]
}

resource "aws_lambda_function_url" "backend" {
  function_name      = aws_lambda_function.backend.function_name
  authorization_type = "NONE"

  cors {
    allow_credentials = false
    allow_headers     = local.cors_allowed_headers
    allow_methods     = local.cors_allowed_methods
    allow_origins     = local.cors_allowed_origins
    expose_headers    = var.cors_expose_headers
    max_age           = var.cors_max_age
  }
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  count               = var.enable_alarms ? 1 : 0
  alarm_name          = "${local.lambda_name}-errors"
  alarm_description   = "Lambda function errors exceeded threshold"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Sum"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = aws_lambda_function.backend.function_name
  }
  alarm_actions = trimspace(var.alarm_topic_arn) != "" ? [var.alarm_topic_arn] : []
  ok_actions    = trimspace(var.alarm_topic_arn) != "" ? [var.alarm_topic_arn] : []
}

resource "aws_cloudwatch_metric_alarm" "lambda_latency" {
  count               = var.enable_alarms ? 1 : 0
  alarm_name          = "${local.lambda_name}-p95"
  alarm_description   = "Lambda function p95 duration exceeded threshold"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 5000
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 300
  extended_statistic  = "p95"
  treat_missing_data  = "notBreaching"
  dimensions = {
    FunctionName = aws_lambda_function.backend.function_name
  }
  alarm_actions = trimspace(var.alarm_topic_arn) != "" ? [var.alarm_topic_arn] : []
  ok_actions    = trimspace(var.alarm_topic_arn) != "" ? [var.alarm_topic_arn] : []
}
