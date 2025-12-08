import os
import json
import time

import pika

from config import samples


QUEUE_NAME = "hzz_files" #queue to distribute the files to workers


def send_file_jobs(fraction=1.0): #sends one messsage per ROOT file into RabbitMQ
    rabbitmq_host = os.environ.get("RABBITMQ_HOST", "rabbitmq")

    params = pika.ConnectionParameters(
        host=rabbitmq_host,
        port=5672,
        heartbeat=600,
        blocked_connection_timeout=300,
    )

    connection = None
    while connection is None: #retries connection to RMQ 
        try:
            print(f"[producer] Connecting to RabbitMQ at {rabbitmq_host}:5672 ...")
            connection = pika.BlockingConnection(params)
            print("[producer] Connected to RabbitMQ")
        except Exception as e:
            print(f"[producer] Connection failed: {repr(e)}. Retrying in 5 seconds...")
            time.sleep(5)

    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)

    jobs = []
    for sample_name in samples:
        for file_path in samples[sample_name]["list"]:
            jobs.append((sample_name, file_path))

    print(f"[producer] Preparing {len(jobs)} file jobs")

    for i, (sample_name, file_path) in enumerate(jobs, start=1):
        message = {
            "sample": sample_name,
            "file_path": file_path,
            "fraction": float(fraction),
        }

        channel.basic_publish( #sends file job as a json message to the work queue
            exchange="",
            routing_key=QUEUE_NAME,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
            ),
        )
        print(f"[producer] Sent job {i}/{len(jobs)} for sample '{sample_name}'")

    connection.close()
    print("[producer] All jobs sent, connection closed")


if __name__ == "__main__":
    fraction = float(os.environ.get("JOB_FRACTION", "1.0"))
    send_file_jobs(fraction=fraction)
