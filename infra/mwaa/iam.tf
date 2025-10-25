resource "aws_iam_role" "mwaa_exec" {
  name               = "${var.project_name}-mwaa-exec"
  assume_role_policy = data.aws_iam_policy_document.mwaa_trust.json
}

data "aws_iam_policy_document" "mwaa_trust" {
  statement {
    effect = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["airflow-env.amazonaws.com"]
    }
  }
}

data "aws_caller_identity" "current" {}

resource "aws_iam_policy" "mwaa_execution" {
  name        = "${var.project_name}-mwaa-exec-policy"
  description = "Execution permissions for Amazon MWAA"
  policy      = data.aws_iam_policy_document.mwaa_execution.json
}

data "aws_iam_policy_document" "mwaa_execution" {
  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListBucketMultipartUploads",
      "s3:ListBucket",
      "s3:GetBucketLocation",
      "s3:GetBucketAcl",
      "s3:PutObject"
    ]
    resources = [
      "arn:aws:s3:::${var.project_name}-dags",
      "arn:aws:s3:::${var.project_name}-dags/*",
      "arn:aws:s3:::${var.project_name}-data",
      "arn:aws:s3:::${var.project_name}-data/*"
    ]
  }

  statement {
    effect    = "Allow"
    actions   = ["s3:GetAccountPublicAccessBlock"]
    resources = ["*"]
  }

  statement {
    effect  = "Allow"
    actions = ["s3:GetBucketPublicAccessBlock"]
    resources = [
      "arn:aws:s3:::${var.project_name}-dags",
      "arn:aws:s3:::${var.project_name}-data"
    ]
  }

  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
      "logs:PutLogEvents",
      "logs:GetLogEvents"
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:airflow-*",
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:airflow-*:*"
    ]
  }

  statement {
    effect = "Allow"
    actions = [
      "sqs:ChangeMessageVisibility",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
      "sqs:ReceiveMessage",
      "sqs:SendMessage"
    ]
    resources = [
      "arn:aws:sqs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:airflow-celery-*"
    ]
  }

  statement {
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:GetAuthorizationToken",
      "ecr:GetDownloadUrlForLayer"
    ]
    resources = ["*"]
  }

  statement {
    effect = "Allow"
    actions = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["Airflow"]
    }
  }

  statement {
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey"
    ]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["airflow.${var.aws_region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy_attachment" "mwaa_execution" {
  role       = aws_iam_role.mwaa_exec.name
  policy_arn = aws_iam_policy.mwaa_execution.arn
}
