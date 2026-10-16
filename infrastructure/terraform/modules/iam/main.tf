terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

variable "name" {
  type        = string
  description = "Environment name, used as a prefix."
}

variable "github_repository" {
  type        = string
  description = "owner/repo allowed to assume the deploy roles."
}

variable "create_oidc_provider" {
  type        = bool
  default     = true
  description = "One GitHub OIDC provider exists per AWS account; set false if it already exists."
}

variable "apply_branch" {
  type        = string
  default     = "main"
  description = "Branch whose workflows may apply."
}

variable "github_environment" {
  type        = string
  description = "GitHub environment (protected, with required approval) whose jobs may apply."
}

variable "region" {
  type = string
}

variable "state_bucket_arn" {
  type        = string
  description = "ARN of the Terraform state bucket (from bootstrap)."
}

variable "state_key_prefix" {
  type        = string
  description = "State object key this environment uses, for example dev/terraform.tfstate."
}

variable "state_kms_key_arn" {
  type        = string
  description = "KMS key that encrypts the state bucket."
}

resource "aws_iam_openid_connect_provider" "github" {
  count          = var.create_oidc_provider ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_caller_identity" "current" {}

locals {
  provider_arn = var.create_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/token.actions.githubusercontent.com"
}

# Plan role: any pull request of this repository, read-only.
data "aws_iam_policy_document" "plan_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:pull_request"]
    }
  }
}

# Apply role: only jobs that run in the protected GitHub environment of this deployment.
data "aws_iam_policy_document" "apply_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:environment:${var.github_environment}"]
    }
  }
}

resource "aws_iam_role" "plan" {
  name                 = "${var.name}-terraform-plan"
  assume_role_policy   = data.aws_iam_policy_document.plan_trust.json
  max_session_duration = 3600
}

resource "aws_iam_role" "apply" {
  name                 = "${var.name}-terraform-apply"
  assume_role_policy   = data.aws_iam_policy_document.apply_trust.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "plan_read" {
  role       = aws_iam_role.plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

data "aws_iam_policy_document" "state_access" {
  statement {
    actions   = ["s3:ListBucket"]
    resources = [var.state_bucket_arn]
  }
  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${var.state_bucket_arn}/${var.state_key_prefix}", "${var.state_bucket_arn}/${var.state_key_prefix}.tflock"]
  }
  statement {
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [var.state_kms_key_arn]
  }
}

resource "aws_iam_role_policy" "plan_state" {
  name   = "state"
  role   = aws_iam_role.plan.id
  policy = data.aws_iam_policy_document.state_access.json
}

resource "aws_iam_role_policy" "apply_state" {
  name   = "state"
  role   = aws_iam_role.apply.id
  policy = data.aws_iam_policy_document.state_access.json
}

# The apply role manages what P15 deploys. Services are listed, not wildcarded to everything, and
# it cannot change IAM users, the organisation or billing. Narrow further once the modules settle.
data "aws_iam_policy_document" "apply_permissions" {
  statement {
    actions = [
      "ec2:*", "elasticloadbalancing:*", "ecs:*", "ecr:*", "rds:*", "elasticache:*", "s3:*", "sqs:*",
      "mq:*", "kms:*", "logs:*", "cloudwatch:*", "secretsmanager:*", "route53:*", "acm:*",
      "autoscaling:*", "application-autoscaling:*", "events:*", "ssm:*", "backup:*", "wafv2:*",
    ]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.region]
    }
  }
  statement {
    actions = [
      "iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:UpdateRole", "iam:TagRole", "iam:UntagRole",
      "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:GetRolePolicy", "iam:ListRolePolicies",
      "iam:AttachRolePolicy", "iam:DetachRolePolicy", "iam:ListAttachedRolePolicies", "iam:PassRole",
      "iam:CreateServiceLinkedRole", "iam:ListInstanceProfilesForRole",
    ]
    resources = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${var.name}-*"]
  }
}

resource "aws_iam_role_policy" "apply" {
  name   = "deploy"
  role   = aws_iam_role.apply.id
  policy = data.aws_iam_policy_document.apply_permissions.json
}

output "plan_role_arn" {
  value = aws_iam_role.plan.arn
}

output "apply_role_arn" {
  value = aws_iam_role.apply.arn
}
