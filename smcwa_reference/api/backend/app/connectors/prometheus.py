from typing import Any, Dict, List, Optional
import httpx
from app.connectors.base import BaseConnector
import logging

logger = logging.getLogger(__name__)

class PrometheusConnector(BaseConnector):
    """
    Prometheus Data Connector.
    Queries Prometheus HTTP API. Supports IAM Role (SigV4) authentication.
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.url = config.get('url', '').rstrip('/')
        self.timeout = float(config.get('timeout', 10.0))
        self.use_iam = config.get('use_iam', False)
        self.role_arn = config.get('role_arn')
        self.region = config.get('region', 'ap-south-1')

    def _get_auth_headers(self) -> Dict[str, str]:
        """Generate AWS SigV4 auth headers if IAM is enabled"""
        if not self.use_iam:
            return {}
            
        try:
            import boto3
            from botocore.auth import SigV4Auth
            from botocore.awsrequest import AWSRequest
            
            # 1. Get Credentials
            if self.role_arn:
                sts = boto3.client('sts', region_name=self.region)
                assumed = sts.assume_role(
                    RoleArn=self.role_arn,
                    RoleSessionName='LamaMimirSession',
                    ExternalId='SMC-LAMA-OBSERVABILITY'
                )
                creds = assumed['Credentials']
                access_key = creds['AccessKeyId']
                secret_key = creds['SecretAccessKey']
                token = creds['SessionToken']
            else:
                session = boto3.Session()
                creds = session.get_credentials().get_frozen_credentials()
                access_key = creds.access_key
                secret_key = creds.secret_key
                token = creds.token

            # 2. Sign Request (Simplified SigV4 for Prometheus API)
            # Note: Many Mimir/AMP setups require X-Amz-Content-Sha256 header
            from botocore.credentials import Credentials
            boto_creds = Credentials(access_key, secret_key, token)
            
            # Construct request for signing
            request = AWSRequest(method='GET', url=f"{self.url}/api/v1/query")
            SigV4Auth(boto_creds, 'aps', self.region).add_auth(request)
            
            return dict(request.headers)
        except Exception as e:
            logger.error(f"Failed to generate AWS SigV4 auth: {e}")
            return {}

    def connect(self) -> bool:
        return bool(self.url)

    def execute_query(self, query: str, index: Optional[str] = None) -> Any:
        api_url = f"{self.url}/api/v1/query"
        headers = self._get_auth_headers()
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(api_url, params={"query": query}, headers=headers)
                if response.status_code != 200:
                    logger.error(f"Prometheus query failed ({response.status_code}): {response.text}")
                    return []
                
                data = response.json()
                if data.get('status') == 'success':
                    return data.get('data', {}).get('result', [])
                return []
        except Exception as e:
            logger.error(f"Prometheus connection failed: {e}")
            return []

    def close(self):
        pass
