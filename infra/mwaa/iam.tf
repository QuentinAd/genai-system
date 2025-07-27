
resource "aws_iam_role" "mwaa_exec" {
  name = "${var.project_name}-mwaa-exec"
  assume_role_policy = data.aws_iam_policy_document.mwaa_trust.json
}

data "aws_iam_policy_document" "mwaa_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["airflow.amazonaws.com"]
    }
  }
}
