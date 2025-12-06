# HZZ Cloud Processing Pipeline

This project refactors an ATLAS Open Data analysis into a distributed, message-driven system using Docker and Kubernetes. The original analysis (`HZZ.py` / `hzz_batch.py`) is sequential and runs on a single machine. This repository converts the workflow into a producer–worker–combiner pipeline using RabbitMQ to distribute ROOT file tasks and containers to scale processing across multiple workers.

## Challenge Overview

The objective of this project is to:
- Take a monolithic scientific analysis script
- Break it into independent, parallel processing tasks
- Use message queues to distribute work to multiple workers
- Automate the execution using container orchestration tools

The system processes ATLAS Open Data files independently across workers, producing partial results that are later recombined into a final output.

---

## Docker Compose Implementation (Local)

This version runs the pipeline locally using Docker Compose and is useful for testing and debugging.

### How to Run

From the `docker-compose` directory:

```bash
docker compose build
docker compose up
```

This will:
- Start RabbitMQ
- Run the producer
- Launch multiple workers
- Run the combiner
- Write output files into a local `outputs/` directory

To stop everything:

```bash
docker compose down
```

If enabled in `docker-compose.yml`, RabbitMQ can be accessed via:

```text
http://localhost:15672
```

---

## Kubernetes Implementation (Main Solution)

This version runs the pipeline on Kubernetes using Deployments, Jobs, and Persistent Volumes.

### Build Image

From the `k8s` directory:

```bash
docker build -t hzz-k8s:latest .
```

### Run Full Pipeline

```bash
cd k8s
chmod +x run_k8s.sh
./run_k8s.sh
```

The script:
1. Deploys RabbitMQ and workers
2. Runs producer and combiner Jobs
3. Waits for completion
4. Copies results back into a local `outputs/` folder

### View RabbitMQ During Runtime

```bash
kubectl port-forward svc/rabbitmq -n hzz-rabbit 15672:15672
```

Then open:

```text
http://localhost:15672
```

### Change Worker Count

Edit in `k8s-all.yaml`:

```yaml
replicas: 8 #e.g., change to any number scaled to workload
```

Apply:

```bash
kubectl apply -f k8s-all.yaml
```

---

## Output Files

After a successful run, the following files will appear locally:

- `hzz_histogram.png`
- `hzz_data.npz`
- `hzz_summary.json`

