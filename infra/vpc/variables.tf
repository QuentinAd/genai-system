variable "project_name"   { 
    type = string 
}
variable "aws_region"     { 
    type = string 
}
variable "public_cidr_az1"  {
    type = string
    default = "10.0.1.0/24" 
}
variable "public_cidr_az2"  {
    type = string
    default = "10.0.2.0/24" 
}
variable "private_cidr_az1" {
    type = string
    default = "10.0.11.0/24"
}
variable "private_cidr_az2" {
    type = string
    default = "10.0.12.0/24"
}
