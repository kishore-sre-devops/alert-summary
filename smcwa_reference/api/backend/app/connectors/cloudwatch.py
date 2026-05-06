from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import boto3
from app.connectors.base import BaseConnector
import logging

logger = logging.getLogger(__name__)

class CloudWatchConnector(BaseConnector):
    """
    AWS CloudWatch Data Connector.
    Uses boto3 to fetch metrics from CloudWatch.
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.client = None
        self.region = config.get('region', 'ap-south-1')
        self.access_key = config.get('access_key')
        self.secret_key = config.get('secret_key')
        self.role_arn = config.get('role_arn')

    def connect(self) -> bool:
        try:
            # Case 1: Keys + Assume Role
            if self.access_key and self.secret_key and self.role_arn:
                sts = boto3.client(
                    'sts',
                    region_name=self.region,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key
                )
                assumed = sts.assume_role(
                    RoleArn=self.role_arn, 
                    RoleSessionName='LamaCloudWatchSession',
                    ExternalId='SMC-LAMA-OBSERVABILITY'
                )
                creds = assumed['Credentials']
                self.client = boto3.client(
                    'cloudwatch',
                    region_name=self.region,
                    aws_access_key_id=creds['AccessKeyId'],
                    aws_secret_access_key=creds['SecretAccessKey'],
                    aws_session_token=creds['SessionToken']
                )
            
            # Case 2: Keys Only
            elif self.access_key and self.secret_key:
                self.client = boto3.client(
                    'cloudwatch',
                    region_name=self.region,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key
                )
            
            # Case 3: Instance Profile + Assume Role
            elif self.role_arn:
                sts = boto3.client('sts', region_name=self.region)
                assumed = sts.assume_role(
                    RoleArn=self.role_arn, 
                    RoleSessionName='LamaCloudWatchSession',
                    ExternalId='SMC-LAMA-OBSERVABILITY'
                )
                creds = assumed['Credentials']
                self.client = boto3.client(
                    'cloudwatch',
                    region_name=self.region,
                    aws_access_key_id=creds['AccessKeyId'],
                    aws_secret_access_key=creds['SecretAccessKey'],
                    aws_session_token=creds['SessionToken']
                )
            
            # Case 4: Instance Profile Only
            else:
                self.client = boto3.client('cloudwatch', region_name=self.region)
                
            return True
        except Exception as e:
            logger.error(f"Failed to connect to CloudWatch: {e}")
            return False

    def execute_query(self, query: str, index: Optional[str] = None) -> Any:
        """
        In CloudWatch context:
        - query: A JSON string containing MetricDataQueries or simplified params
        - index: Not used (could be used for Namespace)
        
        Expected JSON query format:
        {
            "Namespace": "AWS/EC2",
            "MetricName": "CPUUtilization",
            "Dimensions": [{"Name": "InstanceId", "Value": "i-12345"}],
            "Period": 300,
            "Stat": "Average"
        }
        """
        import json
        try:
            params = json.loads(query)
            
            # Default time range: last 5 minutes if not specified
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(minutes=10) # 10m to ensure we get data
            
            namespace = params.get('Namespace')
            metric_name = params.get('MetricName')
            dimensions = params.get('Dimensions', [])
            period = int(params.get('Period', 300))
            stat = params.get('Stat', 'Average')
            
            response = self.client.get_metric_statistics(
                Namespace=namespace,
                MetricName=metric_name,
                Dimensions=dimensions,
                StartTime=start_time,
                EndTime=end_time,
                Period=period,
                Statistics=[stat]
            )
            
            datapoints = response.get('Datapoints', [])
            if datapoints:
                # Sort by timestamp and return latest
                datapoints.sort(key=lambda x: x['Timestamp'], reverse=True)
                return datapoints
            return []
            
        except Exception as e:
            logger.error(f"CloudWatch query execution failed: {e}")
            return []

    def close(self):
        self.client = None
