import time
import random
import logging
import json
import traceback

# Setup multiple loggers for "Top noisy services" testing
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

loggers = [
    logging.getLogger('auth-service'),
    logging.getLogger('db-service'),
    logging.getLogger('payment-service')
]

normal_messages = [
    "User session validated",
    "Query executed successfully",
    "Health check passed",
    "Cache hit for user profile",
    "Metric flushed to datadog",
]

anomaly_messages = [
    "Connection timeout to upstream database",
    "Deadlock detected in transaction",
    "Out of memory error while processing payload",
]

secret_messages = [
    'User authenticated with api_key="sk_dummy_1234567890abcdef1234567890"',
    'Database connection failed. using password="supersecretpassword123"',
    'Invalid token: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c',
    'Found AWS credentials: DUMMY_AKIAIOSFODNN7EXAMPLE',
]

if __name__ == "__main__":
    print("Starting comprehensive mock app for LogSight feature testing...")
    
    while True:
        # Pick a random logger
        logger = random.choice(loggers)
        
        # Decide what kind of log to produce
        log_type = random.choices(['normal', 'anomaly', 'secret', 'json', 'exception'], weights=[80, 5, 5, 5, 5])[0]
        
        if log_type == 'normal':
            logger.info(random.choice(normal_messages))
            
        elif log_type == 'anomaly':
            logger.warning(random.choice(anomaly_messages))
            
        elif log_type == 'secret':
            # This tests secret scrubbing
            logger.info(random.choice(secret_messages))
            
        elif log_type == 'json':
            # This tests the JSON parsing feature in LogSight
            print(json.dumps({
                "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
                "level": "INFO",
                "service": "json-service",
                "message": "Structured logging test",
                "user_id": random.randint(1000, 9999)
            }))
            
        elif log_type == 'exception':
            # This tests multi-line log / exception anomaly detection
            try:
                1 / 0
            except ZeroDivisionError:
                logger.error("A critical error occurred", exc_info=True)
                
        # Sleep randomly between 0.1 and 0.5 seconds
        time.sleep(random.uniform(0.1, 0.5))

    print("Mock app finished")
