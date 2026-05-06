
import json
from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql://lama:lama@localhost:5432/lama_prod"
# Since I'm outside the container, I'll use the docker exec approach instead or connect via host if possible.
# Actually, I'll just use docker exec with a python script.
