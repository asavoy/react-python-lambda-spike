output "endpoint" {
  value = aws_apigatewayv2_api.main.api_endpoint
}

output "upload_bucket" {
  value = aws_s3_bucket.upload.id
}

output "lambda_function_name" {
  value = aws_lambda_function.main.function_name
}
