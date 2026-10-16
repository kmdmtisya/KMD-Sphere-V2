# WealthSphere cloud infrastructure (P15-T02)

AWS, one EU region (ADR-0019, DEC-02). Terraform only. Nothing here holds a secret and no state is committed.

```
bootstrap/              once per AWS account: encrypted, versioned S3 bucket for Terraform state (S3 native locking)
modules/network         VPC, availability zones, public / private / data subnets, NAT, flow logs
modules/iam             GitHub Actions OIDC provider and deploy roles (plan is read-only, apply is per environment)
envs/dev|staging|prod   one root module per environment, each with its own state key
```

## Using it

1. In each AWS account, once: `cd bootstrap && terraform init && terraform apply` (needs AWS credentials; creates the state bucket).
2. For an environment: `cd envs/<env> && terraform init -backend-config=backend.hcl`, where `backend.hcl` (not committed) sets `bucket`, `key` and `region`.
3. `terraform plan -var-file=<env>.tfvars`.

Checks that need no credentials: `terraform fmt -check -recursive` and, in every directory, `terraform init -backend=false` then `terraform validate`. They run in `.github/workflows/infra.yml`. `terraform plan` needs AWS credentials and is not run in CI until the accounts exist.

## Decisions

- The region is a variable (default `eu-central-1`) so a residency change (ADR-0019) is cheap.
- Production runs one NAT gateway per availability zone; dev and staging share one to save cost.
- The data subnets have no route to the internet. The managed data services (P15-T03) live there.
- State holds no secrets by design: modules take no secret inputs and output no secret values.
