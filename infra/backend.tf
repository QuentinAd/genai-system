terraform {
  backend "s3" {
    bucket  = "genai-system-terraform-state"
    key     = "dev/terraform.tfstate"
    region  = "ca-central-1"
    encrypt = true
  }
}
