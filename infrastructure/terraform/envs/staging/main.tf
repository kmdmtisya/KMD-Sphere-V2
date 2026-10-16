terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
  # Partial configuration: bucket, key and region come from -backend-config=backend.hcl (not committed).
  backend "s3" {
    encrypt      = true
    use_lockfile = true
  }
}

variable "region" {
  type    = string
  default = "eu-central-1"
}

variable "github_repository" {
  type    = string
  default = "kmdmtisya/KMD-Sphere-V2"
}

variable "create_oidc_provider" {
  type        = bool
  default     = false
  description = "The GitHub OIDC provider exists once per AWS account; only one environment of an account creates it."
}

variable "state_bucket_arn" {
  type = string
}

variable "state_kms_key_arn" {
  type = string
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { project = "wealthsphere", environment = "staging", managed_by = "terraform" }
  }
}

module "network" {
  source                  = "../../modules/network"
  name                    = "ws-staging"
  cidr                    = "10.20.0.0/16"
  az_count                = 3
  nat_per_az              = false
  flow_log_retention_days = 180
}

module "iam" {
  source               = "../../modules/iam"
  name                 = "ws-staging"
  region               = var.region
  github_repository    = var.github_repository
  github_environment   = "staging"
  create_oidc_provider = var.create_oidc_provider
  state_bucket_arn     = var.state_bucket_arn
  state_key_prefix     = "staging/terraform.tfstate"
  state_kms_key_arn    = var.state_kms_key_arn
}

output "vpc_id" {
  value = module.network.vpc_id
}

output "private_subnet_ids" {
  value = module.network.private_subnet_ids
}

output "public_subnet_ids" {
  value = module.network.public_subnet_ids
}

output "data_subnet_ids" {
  value = module.network.data_subnet_ids
}

output "plan_role_arn" {
  value = module.iam.plan_role_arn
}

output "apply_role_arn" {
  value = module.iam.apply_role_arn
}
