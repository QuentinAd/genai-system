
variable "aws_region" {
  default = "ca-central-1"
}

variable "project_name" {
  default = "rbc-interview"
}

variable "private_subnets" {
  type = list(string)
  default = ["subnet-02e4b37a9d28c0c9d", "subnet-0817c7e61008a7063"]
}
