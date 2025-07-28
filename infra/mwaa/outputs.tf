output "environment_name" {
    value = aws_mwaa_environment.mwaa.name
    description = "The name of the MWAA environment"
}