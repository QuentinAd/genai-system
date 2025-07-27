
resource "aws_mwaa_environment" "mwaa" {
  name = "${var.project_name}-airflow"

  dag_s3_path = "dags"
  source_bucket_arn = "arn:aws:s3:::${var.dags_bucket_name}"
  execution_role_arn = aws_iam_role.mwaa_exec.arn

  airflow_version = "2.8.1"
  environment_class = "mw1.small"
  max_workers = 5
  min_workers = 1
  schedulers = 2

  network_configuration {
    security_group_ids = [aws_security_group.mwaa_sg.id]
    subnet_ids = var.private_subnets
  }

  logging_configuration {
    dag_processing_logs {
      enabled = true
      log_level = "INFO"
    }
    task_logs {
      enabled = true
      log_level = "INFO"
    }
  }
}

resource "aws_security_group" "mwaa_sg" {
  name   = "${var.project_name}-mwaa-sg"
  vpc_id = var.vpc_id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # You may want to restrict this later
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-mwaa-sg"
  }
}
