resource "aws_iam_role" "mwaa_exec" {
  name = "${var.project_name}-mwaa-exec"
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

resource "aws_iam_policy" "mwaa_s3" {
  name        = "${var.project_name}-mwaa-s3-policy"
  description = "Allow MWAA to access DAGs and data buckets"
  policy = data.aws_iam_policy_document.mwaa_s3.json
}

data "aws_iam_policy_document" "mwaa_s3" {
  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
      "s3:PutObject"
    ]
    resources = [
      "arn:aws:s3:::${var.project_name}-dags",
      "arn:aws:s3:::${var.project_name}-dags/*",
      "arn:aws:s3:::${var.project_name}-data",
      "arn:aws:s3:::${var.project_name}-data/*"
    ]
  }
}

resource "aws_iam_role_policy_attachment" "mwaa_s3" {
  role       = aws_iam_role.mwaa_exec.name
  policy_arn = aws_iam_policy.mwaa_s3.arn
}
