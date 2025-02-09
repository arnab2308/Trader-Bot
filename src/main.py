import os
import threading
import datetime 
from json.decoder import JSONDecodeError
import logging
import datetime 
import yaml
import time
import os, sys
from pathlib import Path
import psycopg2
from config import config
import pandas as pd 
# Reading config from yaml file

def setup_logging() -> None:
    """Configure logging with proper format and file handler."""
    today = datetime.date.today()
    log_file = Path(__file__).parent.parent / "logs" / f"run_{today}.log"
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def load_config() -> dict:
    """Load configuration from YAML file."""
    config_path = Path(__file__).parent.parent / "config.yml"
    try:
        with open(config_path, 'r') as file:
            return yaml.safe_load(file)
    except Exception as e:
        logging.error(f"Error reading config file: {e}")
        raise

def cleanup_database(config: dict, days: int = 4) -> None:
    """Remove data older than specified days from the database."""
    logging.info("Cleaning the database with older data")
    deletion_date = datetime.datetime.now() - datetime.timedelta(days=days)
    query = "DELETE FROM banknifty_option_data WHERE date_time <= %s"

    with psycopg2.connect(**config) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (deletion_date.strftime("%Y-%m-%d %H:%M:%S"),))

def generate_tokens() -> None:
    """Generate access and instrument tokens."""
    logging.info("Generating access tokens and instrument tokens")
    access_config_path = Path(__file__).parent / "access_config"

    # Generate access tokens
    os.system(f'cd "{access_config_path}" && python generate_access_token.py')
    
    # Generate instrument tokens
    logging.info("Generating instrument tokens")
    os.system(f'cd "{access_config_path}" && python generate_banknifty_tokens.py')

def manage_celery_websocket(config: dict) -> None:
    """Manage Celery workers and websocket connections."""
    logging.info('Deleting queues from RabbitMQ')
    os.system('./rabbitmqadmin -f tsv -q list queues name | while read queue; do ./rabbitmqadmin -q delete queue name=${queue}; done')

    # Setup paths
    paths = {
        'worker': Path(__file__).parent / "publish_database",
        'ticker': Path(__file__).parent / "ticker",
        'flask': Path(__file__).parent / "flask_app"
    }
    
    queue_name = config['rabbitmq']['queues']['banknifty']
    
    commands = [
        f'cd "{paths["worker"]}" && celery -A insert_database worker -Q {queue_name} --concurrency=1 --loglevel=info -P eventlet -n worker1@%h',
        f'cd "{paths["ticker"]}" && python banknifty_conn.py',
        f'cd "{paths["flask"]}" && python app.py'
    ]
    
    threads = [threading.Thread(target=os.system, args=(cmd,)) for cmd in commands]
    for thread in threads:
        thread.start()
    
    for thread in threads:
        thread.join()

def main() -> None:
    """Main execution function."""
    setup_logging()
    today = datetime.date.today()
    logging.info(f'Starting run for date: {today}')

    exec_date_file = Path("/home/narayana_tariq/Zerodha/Supertrend/last_execution_date.txt")
    config = load_config()

    try:
        last_exec_date = exec_date_file.read_text().strip()
    except FileNotFoundError:
        last_exec_date = ''

    if not last_exec_date:
        cleanup_database(config)
        generate_tokens()
    else:
        last_date = datetime.datetime.strptime(last_exec_date, "%Y-%m-%d").date()
        if last_date != today:
            generate_tokens()

    manage_celery_websocket(config)

if __name__ == "__main__":
    main()
    