import os
import json
import time

import pika
import numpy as np
import requests

from analysis import process_file_hist

QUEUE_FILES = "hzz_files"
QUEUE_PARTIALS = "hzz_partials"


def main():
    rabbitmq_host = os.environ.get("RABBITMQ_HOST", "rabbitmq")

    params = pika.ConnectionParameters(
        host=rabbitmq_host,
        port=5672,
        heartbeat=600,
        blocked_connection_timeout=300,
    )

    connection = None
    while connection is None:
        try:
            print(f"[worker] Connecting to RabbitMQ at {rabbitmq_host}:5672 ...")
            connection = pika.BlockingConnection(params)
            print("[worker] Connected to RabbitMQ")
        except Exception as e:
            print(f"[worker] Connection failed: {repr(e)}. Retrying in 5 seconds...")
            time.sleep(5)

    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_FILES, durable=True)
    channel.queue_declare(queue=QUEUE_PARTIALS, durable=True)

    def process_message(ch, method, properties, body):
        try:
            data = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            print("[worker] Failed to decode message, dropping it")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        sample = data["sample"]
        file_path = data["file_path"]
        fraction = float(data.get("fraction", 1.0))

        print(f"[worker] Received file job for sample '{sample}'")
        try:
            hist, hist_w2 = process_file_hist(sample, file_path, fraction)

            result_message = {
                "sample": sample,
                "hist": hist.tolist(),
                "hist_w2": hist_w2.tolist() if hist_w2 is not None else None,
            }

            ch.basic_publish(
                exchange="",
                routing_key=QUEUE_PARTIALS,
                body=json.dumps(result_message),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type="application/json",
                ),
            )

            print(f"[worker] Finished file job for sample '{sample}'")
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            print(f"[worker] Error while processing file for '{sample}': {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_FILES, on_message_callback=process_message)

    print("[worker] Waiting for file jobs. To exit, stop the container.")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        connection.close()
        print("[worker] Connection closed")


if __name__ == "__main__":
    main()
