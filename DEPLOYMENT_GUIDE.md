# Deployment Guide: Google Cloud VM

This guide explains how to deploy your `quant-trading` system to a Google Cloud Platform (GCP) Virtual Machine and run it 24/7 using Docker.

## 1. Prepare Your VM
1.  **Create an Instance**: Go to GCP Console -> Compute Engine -> VM Instances -> Create Instance.
    - **Machine Type**: `e2-micro` is sufficient for this bot.
    - **OS**: Ubuntu 22.04 LTS (recommended).
2.  **SSH into VM**: Use the "SSH" button in the GCP console.
3.  **Install Docker**: Run these commands on your VM:
    ```bash
    sudo apt-get update
    sudo apt-get install -y docker.io
    sudo systemctl start docker
    sudo systemctl enable docker
    sudo usermod -aG docker $USER
    # Logout and log back in for group changes to take effect
    ```

## 2. Upload Your Code
You can use `git` or `scp` to upload your code to the VM.
- **Git**: Clone your repository directly to the VM.
- **SCP**: `gcloud compute scp --recurse . your-instance-name:~/quant-trading`

## 3. Configure Environment Variables
On the VM, create a `.env` file in the project root:
```bash
nano .env
```
Paste your credentials (Alpaca keys, Email SMTP, etc.) into this file. **Note**: The `Dockerfile` is configured to copy the rest of the code but ignores your local `.env` for security. You must create it on the VM.

## 4. Build and Run with Docker Compose

I have provided a `docker-compose.yaml` file that simplifies the setup.

### Starting the Scanner (Background):
```bash
docker-compose up -d scanner
```

### Starting the Paper Bot:
If you want to run the execution bot instead of the scanner, uncomment the `bot` section in `docker-compose.yaml` and run:
```bash
docker-compose up -d bot
```

## 5. Persistence
The system is configured to use **Volumes**. This means your trade data (`data/`) and your notification history (`logs/`) are stored on the VM itself, not just inside the container. If you update the code or restart the container, your data will **not** be lost.

## 6. Monitoring
- **Check Logs**: `docker-compose logs -f scanner`
- **Stop Everything**: `docker-compose down`
- **Check Status**: `docker-compose ps`

## 6. Security Note
Never commit your `.env` file to a public repository. The `.dockerignore` file ensures your local secrets stay local.
