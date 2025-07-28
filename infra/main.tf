module "s3_data" {
  source       = "./s3"
  project_name = var.project_name
}

module "vpc" {
  source       = "./vpc"
  project_name = var.project_name
  aws_region   = var.aws_region
}

module "eks" {
  source       = "./eks"
  project_name = var.project_name
  environment  = var.environment
  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnet_ids # for control-plane + nodes

  depends_on = [
    aws_nat_gateway.nat_a,
    aws_nat_gateway.nat_b,
  ]
}

module "mwaa" {
  source       = "./mwaa"
  project_name = var.project_name

  vpc_id           = module.vpc.vpc_id
  private_subnets  = module.vpc.private_subnet_ids # to live in private subnets
  dags_bucket_name = module.s3_data.dags_bucket_name
  data_bucket_name = module.s3_data.data_bucket_name

  depends_on = [
    aws_nat_gateway.nat_a,
    aws_nat_gateway.nat_b,
  ]
}

module "ecr" {
  source       = "./ecr"
  project_name = var.project_name
  ecr_repo     = "spark-etl"
}

# Outputs (handy for CI/CD, kubeconfig, etc.)
output "vpc_id" { value = module.vpc.vpc_id }
output "private_subnet_ids" { value = module.vpc.private_subnet_ids }
output "public_subnet_ids" { value = module.vpc.public_subnet_ids }

output "eks_cluster_name" { value = module.eks.cluster_name }
output "eks_cluster_endpoint" { value = module.eks.cluster_endpoint }

output "mwaa_env_name" { value = module.mwaa.environment_name }
output "dags_bucket" { value = module.s3_data.dags_bucket_name }
output "data_bucket" { value = module.s3_data.data_bucket_name }
