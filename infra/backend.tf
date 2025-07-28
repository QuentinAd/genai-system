terraform {
  backend "s3" {
    bucket         = "rbc-interview-terraform-state"
    key            = "dev/terraform.tfstate"
    region         = "ca-central-1"
    dynamodb_table = "rbc-interview-terraform-locks"
    encrypt        = true
  }
}