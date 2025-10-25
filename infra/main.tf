module "s3_data" {
  source       = "./s3"
  project_name = var.project_name
  environment  = var.environment
}

module "vpc" {
  source       = "./vpc"
  project_name = var.project_name
  aws_region   = var.aws_region
}

module "mwaa" {
  source       = "./mwaa"
  project_name = var.project_name

  vpc_id           = module.vpc.vpc_id
  vpc_cidr         = module.vpc.vpc_cidr_block
  private_subnets  = module.vpc.private_subnet_ids # to live in private subnets
  dags_bucket_name = module.s3_data.dags_bucket_name
  data_bucket_name = module.s3_data.data_bucket_name
  aws_region       = var.aws_region

  depends_on = [module.vpc]
}

module "dynamodb_hirag" {
  source       = "./dynamodb"
  project_name = var.project_name
  environment  = var.environment
}

module "neptune_hirag" {
  source                              = "./neptune"
  project_name                        = var.project_name
  environment                         = var.environment
  aws_region                          = var.aws_region
  vpc_id                              = module.vpc.vpc_id
  private_subnet_ids                  = module.vpc.private_subnet_ids
  vpc_cidr                            = module.vpc.vpc_cidr_block
  neptune_ingest_bucket_force_destroy = false

  depends_on = [module.vpc]
}

module "opensearch_hirag" {
  source       = "./opensearch"
  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region
  vpc_id       = module.vpc.vpc_id
  vpc_cidr     = module.vpc.vpc_cidr_block
  subnet_ids   = module.vpc.private_subnet_ids

  depends_on = [module.vpc]
}

module "ui" {
  source       = "./cloudfront_ui"
  project_name = var.project_name
  environment  = var.environment
}

module "ecr_etl" {
  source       = "./ecr"
  project_name = var.project_name
  ecr_repo     = "etl"
}

module "ecr_backend" {
  source       = "./ecr"
  project_name = var.project_name
  ecr_repo     = "genai-app"
}

# Outputs (handy for CI/CD, kubeconfig, etc.)
output "vpc_id" { value = module.vpc.vpc_id }
output "private_subnet_ids" { value = module.vpc.private_subnet_ids }
output "public_subnet_ids" { value = module.vpc.public_subnet_ids }

output "ecr_etl_repository_url" { value = module.ecr_etl.repository_url }
output "ecr_etl_repository_name" { value = module.ecr_etl.repository_name }
output "ecr_backend_repository_url" { value = module.ecr_backend.repository_url }
output "ecr_backend_repository_name" { value = module.ecr_backend.repository_name }
output "ecr_registry_id" { value = module.ecr_etl.registry_id }

output "mwaa_env_name" { value = module.mwaa.environment_name }
output "dags_bucket" { value = module.s3_data.dags_bucket_name }
output "data_bucket" { value = module.s3_data.data_bucket_name }
output "hirag_ingestion_bucket" { value = module.s3_data.hirag_ingestion_bucket_name }
output "hirag_archive_prefix" { value = module.s3_data.hirag_archive_prefix }

output "hirag_kv_table_name" { value = module.dynamodb_hirag.hirag_kv_table_name }
output "hirag_kv_table_arn" { value = module.dynamodb_hirag.hirag_kv_table_arn }
output "chat_history_table_name" { value = module.dynamodb_hirag.chat_history_table_name }
output "chat_history_table_arn" { value = module.dynamodb_hirag.chat_history_table_arn }
output "dynamodb_airflow_policy_arn" { value = module.dynamodb_hirag.airflow_policy_arn }
output "dynamodb_backend_policy_arn" { value = module.dynamodb_hirag.backend_policy_arn }

output "neptune_writer_endpoint" { value = module.neptune_hirag.neptune_cluster_endpoint }
output "neptune_reader_endpoint" { value = module.neptune_hirag.neptune_reader_endpoint }
output "neptune_secret_arn" { value = module.neptune_hirag.neptune_secret_arn }
output "neptune_ingest_bucket_name" { value = module.neptune_hirag.neptune_ingest_bucket_name }
output "opensearch_domain_endpoint" { value = module.opensearch_hirag.opensearch_domain_endpoint }
output "opensearch_domain_arn" { value = module.opensearch_hirag.opensearch_domain_arn }
output "opensearch_admin_secret_arn" { value = module.opensearch_hirag.opensearch_admin_secret_arn }

output "ui_bucket_name" { value = module.ui.ui_bucket_name }
output "ui_distribution_id" { value = module.ui.ui_distribution_id }
output "ui_distribution_domain_name" { value = module.ui.ui_distribution_domain_name }
