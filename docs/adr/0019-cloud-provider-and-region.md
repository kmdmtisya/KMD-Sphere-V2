# ADR-0019: Cloud provider, region and data residency (DEC-02)

**Status:** **Accepted** by the user on 2026-10-16 (P15-T01): AWS, one EU region.

**Context**

P15 needs a target for Terraform, managed PostgreSQL, Redis, object storage, a queue, container compute, Keycloak and observability. The platform is a modular monolith plus a Next.js portal, Keycloak, Celery workers and RabbitMQ/Redis (CLAUDE.md). Users are expected in the UAE and Kenya.

**Options**

| Option | For | Against |
|---|---|---|
| AWS | Widest managed coverage for this stack (RDS PostgreSQL, ElastiCache, S3, SQS/Amazon MQ, ECS Fargate, ALB, ACM, KMS, Secrets Manager); mature Terraform provider; regions in the EU, Bahrain and UAE | Cost needs active control |
| GCP | Simple container platform (Cloud Run) | Fewer regional options near users; team has no existing use |
| OCI | Lowest list price | Smaller ecosystem and Terraform module base |

**Decision**

- Provider: **AWS**.
- Region: **one EU region** (eu-central-1 Frankfurt as the working choice; eu-west-1 Ireland is the alternative if a service is missing). All personal and financial data stays in that region: database, backups, object storage, logs and queue. No cross-region replication in v1.
- Environments: dev, staging and production as separate accounts or at least separate VPCs, state and IAM (P15-T02).
- Secrets in AWS Secrets Manager with KMS customer keys; no secrets in Terraform state outputs.

**Consequences**

- Latency from the UAE and Kenya to the EU is higher than to a regional deployment. The portal and API are measured against the DEC-36 budgets from a staging site; a CDN fronts static assets only.
- Data-residency rules for the UAE and Kenya (the UAE federal data protection law and Kenya's Data Protection Act both restrict cross-border transfer in some cases) are not legally reviewed here. This is tracked under the legal review (DEC-10) and must be cleared before production launch. If it requires in-country storage, the region choice is revisited by a superseding ADR; the Terraform modules take the region as a variable so that stays cheap.
- No multi-region failover in v1; recovery is by backups and infrastructure as code (P15-T10 sets targets).

**Related:** DEC-32 (web hosting, domain and CDN) follows this decision.
