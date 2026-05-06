import httpx
import logging
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

class BlasterClient:
    """
    Client for the C-Zentrix 'addlead.php' blaster call API.
    """
    def __init__(self, base_url: str):
        """
        Initializes the client.
        
        Args:
            base_url: The base URL of the C-Zentrix server (e.g., http://172.16.1.60)
        """
        self.base_url = base_url.rstrip('/')

    def make_call(self, destination_number: str, campaign_name: str, cust_unique_id: str, client_id: str) -> bool:
        """
        Initiates a blaster call by adding a lead to a campaign.

        Args:
            destination_number: The customer's phone number to call.
            campaign_name: The name of the campaign to use.
            cust_unique_id: A string containing the alert details.
            client_id: The client ID for the API.

        Returns:
            True if the API call was accepted (e.g., returned HTTP 200), False otherwise.
        """
        if not all([self.base_url, destination_number, campaign_name, cust_unique_id]):
            logger.error("BlasterClient: Missing required parameters for make_call.")
            return False

        # The endpoint path is hardcoded as per the user's example
        endpoint = f"{self.base_url}/apps/addlead.php"
        
        # URL-encode the parameters
        params = {
            "camp_name": campaign_name,
            "CustUniqueId": cust_unique_id,
            "mobile": destination_number,
            # The client_id from the old config might be useful here, 
            # though it was not in the user's example URL. We include it for completeness.
            # "client_id": client_id 
        }

        try:
            logger.info(f"Initiating blaster call to {destination_number} via campaign {campaign_name}")
            logger.debug(f"Blaster API call details: URL={endpoint}, Params={params}")

            with httpx.Client() as client:
                response = client.get(endpoint, params=params, timeout=15.0)
                
                # For this type of simple GET API, a 200 OK response usually means success.
                if response.status_code == 200:
                    logger.info(f"Blaster call API returned success for {destination_number}. Response: {response.text[:200]}")
                    return True
                else:
                    logger.error(f"Blaster call API failed for {destination_number} with status {response.status_code}: {response.text[:200]}")
                    return False
        except httpx.RequestError as e:
            logger.error(f"Error making blaster call to {destination_number}: {e}")
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred during blaster call to {destination_number}: {e}", exc_info=True)
            return False

# For backward compatibility, we can alias the old name to the new one.
# This avoids having to change the import in alert_config.py and alert_sender.py
CZentrixClient = BlasterClient
