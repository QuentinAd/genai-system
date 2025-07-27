module "s3_data" {
  project_name = var.project_name
  source = "./s3"
}

module "vpc" {
  source      = "./vpc"
  project_name = var.project_name
}

module "mwaa" {
  source            = "./mwaa"
  project_name      = var.project_name
  dags_bucket_name  = module.s3_data.dags_bucket_name
  data_bucket_name  = module.s3_data.data_bucket_name
  private_subnets   = module.vpc.public_subnet_ids
  vpc_id            = module.vpc.vpc_id
}

module "eks" {
  source       = "./eks"
  project_name = var.project_name
  environment  = var.environment
  vpc_id       = module.vpc.vpc_id
  subnet_ids   = module.vpc.public_subnet_ids
}

