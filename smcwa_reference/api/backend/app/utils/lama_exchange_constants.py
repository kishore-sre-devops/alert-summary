# api/backend/app/utils/lama_exchange_constants.py
"""
LAMA Exchange API Constants
Exchange IDs and Application IDs as per V1.2 specification
"""

# Exchange ID Constants
EXCHANGE_ID_NOT_APPLICABLE = -1
EXCHANGE_ID_NSE = 1
EXCHANGE_ID_BSE = 2
EXCHANGE_ID_MSE = 3
EXCHANGE_ID_MCX = 4
EXCHANGE_ID_NCDEX = 5

VALID_EXCHANGE_IDS = {
    EXCHANGE_ID_NOT_APPLICABLE: "Not Applicable",
    EXCHANGE_ID_NSE: "National Stock Exchange",
    EXCHANGE_ID_BSE: "Bombay Stock Exchange",
    EXCHANGE_ID_MSE: "Metropolitan Stock Exchange",
    EXCHANGE_ID_MCX: "Multi-Commodity Exchange",
    EXCHANGE_ID_NCDEX: "National Commodity and Derivatives Exchange",
}

DEFAULT_EXCHANGE_ID = EXCHANGE_ID_NSE

def validate_exchange_id(exchange_id: int) -> bool:
    """Validate if exchange_id is a valid value"""
    return exchange_id in VALID_EXCHANGE_IDS

def get_exchange_id_description(exchange_id: int) -> str:
    """Get description for exchange_id"""
    return VALID_EXCHANGE_IDS.get(exchange_id, "Unknown Exchange ID")

# Application ID Constants
APPLICATION_ID_NOT_APPLICABLE = -1
APPLICATION_ID_CLIENT_CONNECTIVITY = 1
APPLICATION_ID_ORDER_MANAGEMENT_SYSTEM = 2
APPLICATION_ID_RISK_MANAGEMENT_SYSTEM = 3
APPLICATION_ID_EXCHANGE_CONNECTIVITY = 4

VALID_APPLICATION_IDS = {
    APPLICATION_ID_NOT_APPLICABLE: "Not Applicable",
    APPLICATION_ID_CLIENT_CONNECTIVITY: "Client Connectivity",
    APPLICATION_ID_ORDER_MANAGEMENT_SYSTEM: "Order Management System",
    APPLICATION_ID_RISK_MANAGEMENT_SYSTEM: "Risk Management System",
    APPLICATION_ID_EXCHANGE_CONNECTIVITY: "Exchange Connectivity",
}

DEFAULT_APPLICATION_ID = APPLICATION_ID_NOT_APPLICABLE

def validate_application_id(application_id: int) -> bool:
    """Validate if application_id is a valid value"""
    return application_id in VALID_APPLICATION_IDS

def get_application_id_description(application_id: int) -> str:
    """Get description for application_id"""
    return VALID_APPLICATION_IDS.get(application_id, "Unknown Application ID")

