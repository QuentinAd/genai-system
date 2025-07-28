data "aws_eks_cluster" "this" {
  name = module.eks.cluster_name
}

data "aws_eks_cluster_auth" "this" {
  name = module.eks.cluster_name
}

data "aws_iam_policy_document" "assume_irsa" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [module.eks.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${replace(module.eks.oidc_provider_url, "https://", "")}:sub"
      values   = ["system:serviceaccount:default:spark-runner"]
    }
  }
}

resource "aws_iam_policy" "s3_rw" {
  name        = "${var.project_name}-s3-rw-policy"
  path        = "/"
  description = "S3 access policy for Spark pods"
  policy      = file("${path.module}/iam_policy_s3_read_write.json")
}

resource "aws_iam_role" "spark_sa_role" {
  name               = "${var.project_name}-spark-irsa-role"
  assume_role_policy = data.aws_iam_policy_document.assume_irsa.json
}

resource "aws_iam_role_policy_attachment" "s3_rw" {
  policy_arn = aws_iam_policy.s3_rw.arn
  role       = aws_iam_role.spark_sa_role.name
}

resource "kubernetes_service_account" "spark_sa" {
  metadata {
    name      = "spark-runner"
    namespace = "default"
    annotations = {
      "eks.amazonaws.com/role-arn" = aws_iam_role.spark_sa_role.arn
    }
  }
}
