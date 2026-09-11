# Automated ECS Fargate CI/CD Pipeline via GitHub Actions & OIDC

A production-grade Continuous Integration and Continuous Deployment (CI/CD) pipeline that builds, tests, and deploys a containerized web application to **Amazon ECS (Elastic Container Service) on AWS Fargate** using **Keyless OpenID Connect (OIDC)** authentication.

---

## Architecture Overview

Push to main
│
▼
┌─────────────────────────────────────────────────────────────┐
│ GitHub Actions Runner                                       │
│                                                             │
│  1. Checkout Code                                           │
│  2. Authenticate to AWS STS via OIDC (No static API keys)   │
│  3. Log in to Amazon ECR                                    │
│  4. Build & Tag Docker Image (${{ github.sha }})            │
│  5. Push Image to Amazon ECR                                │
│  6. Render dynamic Task Definition                          │
│  7. Initiate ECS Rolling Deployment                         │
│  8. Await Service Stability                                 │
└──────────────────────────────┬──────────────────────────────┘
│
┌───────────────┴───────────────┐
▼                               ▼
┌───────────────┐               ┌───────────────┐
│  Amazon ECR   │               │  Amazon ECS   │
│  Repository   │               │    Fargate    │
└───────────────┘               └───────────────┘
---

## Key Features

- **Zero Static Credentials:** Eliminates long-lived IAM access keys (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`) using AWS STS web identity federation (`AssumeRoleWithWebIdentity`).
- **Immutable Container Tagging:** Docker images are tagged with the Git commit SHA (`${{ github.sha }}`), enabling full auditability and instant rollbacks.
- **Zero-Downtime Rolling Updates:** ECS launches new tasks, confirms health status, routes traffic, and gracefully stops deprecated tasks.
- **Service Stability Gating:** The pipeline blocks until AWS validates that the new deployment is healthy (`wait-for-service-stability: true`).

---

## Project Structure

```text
.
├── .github/
│   └── workflows/
│       └── deploy.yml          # GitHub Actions CI/CD deployment pipeline
├── app/
│   └── main.py                 # Application source code
├── Dockerfile                  # Container build instructions
├── task-definition.json        # ECS Task Definition schema
├── trust-policy.json           # IAM OIDC Role Trust Policy
└── README.md
Infrastructure & IAM Configuration
1. GitHub Actions OIDC Provider
An IAM Identity Provider connects GitHub Actions to your AWS account:

Provider URL: https://token.actions.githubusercontent.com

Audience: sts.amazonaws.com

2. IAM Role Trust Policy (github-actions-ecs-role)
The IAM role requires an exact trust relationship matching GitHub's OIDC subject claims with case-sensitive condition operators (StringEquals and StringLike):

{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::088923313807:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:ormendelgit/ecs-fargate-cicd:*"
        }
      }
    }
  ]
}

3. IAM Role Permissions
The deployment role requires permissions to push to ECR and manage ECS tasks:

AmazonEC2ContainerRegistryPowerUser

Custom policy granting ecs:DescribeServices, ecs:UpdateService, ecs:RegisterTaskDefinition, and iam:PassRole for task execution roles.

CI/CD Pipeline Details
The workflow (.github/workflows/deploy.yml) triggers on every push to the main branch:

OIDC Handshake: aws-actions/configure-aws-credentials@v4 exchanges a signed GitHub JWT token for short-lived AWS STS credentials.

ECR Authentication: Authenticates the Docker daemon to the private ECR registry.

Build & Push: Builds the Dockerfile and pushes my-fargate-app:<commit-sha>.

Render Task Definition: aws-actions/amazon-ecs-render-task-definition@v1 inserts the new image URI into task-definition.json.

ECS Rolling Update: aws-actions/amazon-ecs-deploy-task-definition@v2 updates prod-fargate-service on prod-fargate-cluster and tracks service stability.

Verification & Testing
Test the Live Application Endpoint
Retrieve the public IP assigned to the active Fargate task:

# 1. Get the running task ARN
TASK_ARN=$(aws ecs list-tasks \
  --cluster prod-fargate-cluster \
  --service-name prod-fargate-service \
  --region us-east-1 \
  --query "taskArns[0]" \
  --output text)

# 2. Extract the Elastic Network Interface (ENI) ID
ENI_ID=$(aws ecs describe-tasks \
  --cluster prod-fargate-cluster \
  --tasks "$TASK_ARN" \
  --region us-east-1 \
  --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value" \
  --output text)

# 3. Resolve the public IP
PUBLIC_IP=$(aws ec2 describe-network-interfaces \
  --network-interface-ids "$ENI_ID" \
  --region us-east-1 \
  --query "NetworkInterfaces[0].Association.PublicIp" \
  --output text)

# 4. Query the application
curl -s "http://${PUBLIC_IP}"

View Application CloudWatch Logs

aws logs tail /ecs/my-fargate-app --region us-east-1 --follow

Cost Management (FinOps)
To prevent ongoing AWS Fargate compute charges when not actively testing:

# Scale down running tasks to 0
aws ecs update-service \
  --cluster prod-fargate-cluster \
  --service prod-fargate-service \
  --desired-count 0 \
  --region us-east-1

# Scale back up to 1 when ready
aws ecs update-service \
  --cluster prod-fargate-cluster \
  --service prod-fargate-service \
  --desired-count 1 \
  --region us-east-1

