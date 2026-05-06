from sqlalchemy import text, inspect
from database import engine

def fix_db():
    inspector = inspect(engine)
    columns = [c['name'] for c in inspector.get_columns('alerts')]
    
    with engine.begin() as conn:
        if 'is_silenced' not in columns:
            print("Adding is_silenced to alerts table...")
            conn.execute(text("ALTER TABLE alerts ADD COLUMN is_silenced INTEGER DEFAULT 0"))
            print("Column is_silenced added.")
        
        if 'cluster' not in columns:
            print("Adding cluster to alerts table...")
            conn.execute(text("ALTER TABLE alerts ADD COLUMN cluster VARCHAR(255)"))
            print("Column cluster added.")
        
        # Also check prometheus_servers table
        server_columns = [c['name'] for c in inspector.get_columns('prometheus_servers')]
        if 'status' not in server_columns:
            print("Adding status to prometheus_servers table...")
            conn.execute(text("ALTER TABLE prometheus_servers ADD COLUMN status VARCHAR(50) DEFAULT 'unknown'"))
        if 'last_checked' not in server_columns:
            print("Adding last_checked to prometheus_servers table...")
            conn.execute(text("ALTER TABLE prometheus_servers ADD COLUMN last_checked DATETIME"))
        
        # Check prometheus_targets table
        target_columns = [c['name'] for c in inspector.get_columns('prometheus_targets')]
        if 'asset' not in target_columns:
            print("Adding asset to prometheus_targets table...")
            conn.execute(text("ALTER TABLE prometheus_targets ADD COLUMN asset VARCHAR(255)"))
        
        print("Schema update complete.")

if __name__ == "__main__":
    fix_db()
