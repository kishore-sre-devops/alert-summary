AWS_ASSUME_ROLE_EXTERNAL_ID = "SMC-LAMA-OBSERVABILITY"

ECS_SERVICES = [
    {
        "name": "smc-pre-trade-sanjay-api",
        "cluster": "smc-pre-trade-ecs-fargate",
        "type": "ALB",
        "alb_arn": "arn:aws:elasticloadbalancing:ap-south-1:396913716058:loadbalancer/app/smc-pre-trade-alb/cbd8dd63bce4d36b",
        "target_group_arn": "arn:aws:elasticloadbalancing:ap-south-1:396913716058:targetgroup/smc-pre-trade-sanjay-api/b8b7184e678d78c0",
        "application_id": 101,
        "environment": "uat",
    },
    {
        "name": "smc-pre-trade-research-tool-api",
        "cluster": "smc-pre-trade-ecs-fargate",
        "type": "ALB",
        "alb_arn": "arn:aws:elasticloadbalancing:ap-south-1:396913716058:loadbalancer/app/smc-pre-trade-alb-research/fcd62708e3de301c",
        "target_group_arn": "arn:aws:elasticloadbalancing:ap-south-1:396913716058:targetgroup/smc-pre-trade-research-tool-api/5264a09f1aacd95d",
        "application_id": 102,
        "environment": "uat",
    },
    {
        "name": "smc-pre-trade-algo-api",
        "cluster": "smc-pre-trade-ecs-ec2",
        "type": "NLB",
        "nlb_arn": "arn:aws:elasticloadbalancing:ap-south-1:396913716058:loadbalancer/net/smc-pre-trade-nlb-algo-api/51d4d6271fbceaad",
        "target_group_arn": "arn:aws:elasticloadbalancing:ap-south-1:396913716058:targetgroup/smc-pre-trade-algo-api/6c66e67f0cb8dfe3",
        "application_id": 103,
        "environment": "uat",
    },
    {
        "name": "smc-pre-trade-munshi-api",
        "cluster": "smc-pre-trade-ecs-ec2",
        "type": "NLB",
        "nlb_arn": "arn:aws:elasticloadbalancing:ap-south-1:396913716058:loadbalancer/net/smc-pre-trade-nlb-munshi-api/9329d236add9ca32",
        "target_group_arn": "arn:aws:elasticloadbalancing:ap-south-1:396913716058:targetgroup/smc-pre-trade-munshi-api/8332851d210f601a",
        "application_id": 104,
        "environment": "uat",
    },
    {
        "name": "smc-pre-trade-dispatcher-api",
        "cluster": "smc-pre-trade-ecs-ec2",
        "type": "NLB",
        "nlb_arn": "arn:aws:elasticloadbalancing:ap-south-1:396913716058:loadbalancer/net/smc-pre-trade-new-nlb-dispatch/abe29ce5acad5cdc",
        "target_group_arn": "arn:aws:elasticloadbalancing:ap-south-1:396913716058:targetgroup/smc-pre-trade-dispatcher-api/e9d38708ff638166",
        "application_id": 105,
        "environment": "uat",
    },
    {
        "name": "smc-pre-trade-khabri-daemon",
        "cluster": "smc-pre-trade-ecs-fargate",
        "type": "BACKGROUND",
        "application_id": 106,
        "environment": "uat",
    },
    # Sample PROD services (Placeholders for validation)
    {
        "name": "smc-trading-api-prod",
        "cluster": "smc-trading-ecs-prod",
        "type": "ALB",
        "alb_arn": "arn:aws:elasticloadbalancing:ap-south-1:396913716058:loadbalancer/app/smc-prod-alb/123456",
        "target_group_arn": "arn:aws:elasticloadbalancing:ap-south-1:396913716058:targetgroup/smc-prod-tg/7890",
        "application_id": 201,
        "environment": "prod",
    }
]
