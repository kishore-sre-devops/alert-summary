
import os
import pymysql
from dotenv import load_dotenv

load_dotenv()

MYSQL_USER = os.getenv("MYSQL_USER", "alert_user")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "alert_password")
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3307"))
MYSQL_DB = os.getenv("MYSQL_DB", "alert_summary")

def get_target_details():
    try:
        connection = pymysql.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DB,
            port=MYSQL_PORT,
            cursorclass=pymysql.cursors.DictCursor
        )
        with connection.cursor() as cursor:
            # Query unique instances with their latest metadata
            query = """
            SELECT Instance, Company, Asset, job_name as Job, `Group` as `GroupName`, group1 as Group1, MAX(time) as LastSeen
            FROM alerts
            GROUP BY Instance, Company, Asset, job_name, `Group`, group1
            ORDER BY LastSeen DESC;
            """
            cursor.execute(query)
            results = cursor.fetchall()
            return results
    except Exception as e:
        print(f"Error: {e}")
        return []

if __name__ == "__main__":
    details = get_target_details()
    if not details:
        print("No details found.")
    else:
        print(f"{'Instance':<20} | {'Company':<10} | {'Asset':<6} | {'Job':<25} | {'Group':<15} | {'Last Seen'}")
        print("-" * 110)
        for row in details:
            instance = str(row['Instance']) if row['Instance'] else "Unknown"
            company = str(row['Company']) if row['Company'] else ""
            asset = str(row['Asset']) if row['Asset'] else "N/A"
            job = str(row['Job']) if row['Job'] else "N/A"
            group = str(row['GroupName']) if row['GroupName'] else "N/A"
            last_seen = str(row['LastSeen'])
            print(f"{instance:<20} | {company:<10} | {asset:<6} | {job:<25} | {group:<15} | {last_seen}")
