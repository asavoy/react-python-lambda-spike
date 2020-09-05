provider "aws" {
  region              = "us-west-2"
}

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}

resource "random_id" "id" {
  byte_length = 8
}

locals {
  # Generate a unique name
  name = "react-python-app-${random_id.id.hex}"
}

resource "aws_lambda_function" "main" {
  function_name = local.name

  runtime = "python3.8"
  handler = "proxy.lambda_handler"
  role    = aws_iam_role.main.arn

  memory_size = 1024
  timeout     = 15 # in seconds

  environment {
    variables = {
      foo = "bar"
    }
  }

  # Use a bootstrap function since function deployments happen externally
  filename         = "bootstrap/bootstrap.zip"
  source_code_hash = filebase64sha256("bootstrap/bootstrap.zip")

  # Ignore these attributes that would be changed by a function deployment
  lifecycle {
    ignore_changes = [
      filename,
      last_modified,
      qualified_arn,
      source_code_hash,
      version,
    ]
  }

  depends_on = [
    aws_iam_role_policy_attachment.main,
    aws_cloudwatch_log_group.main,
  ]
}

resource "aws_s3_bucket" "upload" {
  bucket        = local.name
  acl           = "private"
  force_destroy = true
}

resource "aws_cloudwatch_log_group" "main" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = 14
}

resource "aws_apigatewayv2_api" "main" {
  name          = local.name
  protocol_type = "HTTP"
  route_key     = "$default"
  target        = aws_lambda_function.main.arn
}

resource "aws_lambda_permission" "main" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.main.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

resource "aws_iam_role" "main" {
  name = "${local.name}_role"

  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowAssumeRole",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      }
    }
  ]
}
EOF
}

resource "aws_iam_policy" "main" {
  name        = "${local.name}_policy"
  path        = "/"
  description = "IAM policy for logging from a lambda"

  policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowLogging",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
EOF
}

resource "aws_iam_role_policy_attachment" "main" {
  role       = aws_iam_role.main.name
  policy_arn = aws_iam_policy.main.arn
}
