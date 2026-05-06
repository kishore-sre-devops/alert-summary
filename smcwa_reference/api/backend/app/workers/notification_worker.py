
from app.celery_app import celery_app

@celery_app.task(name="app.workers.notification_worker.send_notification")
def send_notification(alert_details):
    """
    This worker sends notifications (Email, Slack, etc.) asynchronously.
    """
    # Placeholder: The actual alert sending logic from alert_sender.py will be moved here.
    print(f"Sending notification for alert: {alert_details.get('alert_name')}")
    pass
