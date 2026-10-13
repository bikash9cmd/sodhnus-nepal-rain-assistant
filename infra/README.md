# Deploying to AWS

Everything is in [`template.yaml`](template.yaml) (AWS SAM). Region: **ap-south-1** (Mumbai), the nearest to Nepal (ADR-009 in [docs/ALTERNATIVES.md](../docs/ALTERNATIVES.md)).

## Prerequisites

- An AWS account and credentials (`aws configure`)
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) and Docker (the image is built for arm64)
- **Model access for Amazon Nova Lite** in the Bedrock console for ap-south-1 (and the regions the APAC inference profile routes to)
- Barsha deployed, with at least one run so `gold/` exists in its lake bucket. Without Barsha, upload `data/barsha-gold/*` to any bucket under `gold/` and point at that instead.

## Deploy

```bash
sam build --template-file infra/template.yaml
sam deploy --guided --region ap-south-1
#   BarshaLakeBucket: the LakeBucket output of the Barsha stack
#   OpsEmail:         to receive alarms and the budget warning (confirm the email AWS sends)
#   Backend:          bedrock (or rules, to run with no Bedrock spend)
```

## Try it

```bash
API=<ApiUrl from the outputs>
curl -s $API/health
curl -s $API/ask -H 'content-type: application/json' \
  -d '{"question": "How unusual was the rain in Pokhara on असोज १२?"}'
curl -s $API/feedback -H 'content-type: application/json' -d '{"id": "<id from /ask>", "helpful": true}'
```

## Evaluate the deployed model

From your machine, with the same credentials:

```bash
SODHNUS_BACKEND=bedrock SODHNUS_BEDROCK_REGION=ap-south-1 make eval-bedrock
```

This runs the 60 questions through Nova Lite and writes `eval/results/bedrock.json`, including tokens, rewrites and fallbacks per question. Set `SODHNUS_GUARDRAIL_ID` and `SODHNUS_GUARDRAIL_VERSION` (stack outputs) to include the guardrail.

## Changing the guardrail

`AWS::Bedrock::GuardrailVersion` snapshots the guardrail. After editing the guardrail's policies, change the version's `Description` so CloudFormation creates a new version, and the function picks it up from its environment.

## Tear down

```bash
sam delete
```

The answer log table is deleted with the stack. Barsha's bucket is not touched.

## What's verified and what isn't

- `cfn-lint infra/template.yaml` passes, and CI runs it.
- The Lambda handler runs against mocked S3 (Barsha's bucket) and DynamoDB in `tests/test_aws_handlers.py`, including redaction, metrics and feedback.
- The Bedrock path (Converse with tool use, ApplyGuardrail, rewrite, every fallback) is tested against a scripted stand-in that returns real Converse response shapes.
- **Not yet done:** deploying the stack and calling Nova Lite. Expect small fixes on a first deploy (model access, the inference profile ARN in the IAM policy, the arm64 image build).
