"""
Upload seed data JSONs para o Cloudflare R2.
Executa uma vez para popular o bucket com os dados iniciais.

Uso:
    python -m scripts.upload_seed_to_r2
"""
import json
import os
import sys
from pathlib import Path

try:
    import boto3
except ImportError:
    print("ERRO: boto3 nao instalado. Rode: pip install boto3")
    sys.exit(1)

# Config from env vars
ENDPOINT = os.getenv("R2_ENDPOINT_URL")
KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
SECRET = os.getenv("R2_SECRET_ACCESS_KEY")
BUCKET = os.getenv("R2_BUCKET_NAME", "climarisk-og")

if not all([ENDPOINT, KEY_ID, SECRET]):
    print("ERRO: Variaveis de ambiente R2 nao configuradas.")
    print("Necessarias: R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY")
    sys.exit(1)

s3 = boto3.client(
    "s3",
    endpoint_url=ENDPOINT,
    aws_access_key_id=KEY_ID,
    aws_secret_access_key=SECRET,
)

DATA_DIR = Path(__file__).parent.parent / "app" / "data"


def upload_all():
    """Upload all JSON files from data dir to R2."""
    files = list(DATA_DIR.glob("results_*.json"))
    if not files:
        print(f"Nenhum arquivo results_*.json encontrado em {DATA_DIR}")
        return

    for f in files:
        key = f"results/{f.name}"
        print(f"Uploading {f.name} -> s3://{BUCKET}/{key} ...", end=" ")
        try:
            s3.upload_file(
                str(f),
                BUCKET,
                key,
                ExtraArgs={"ContentType": "application/json"},
            )
            print("OK")
        except Exception as e:
            print(f"ERRO: {e}")

    # Verify
    print("\nVerificando conteudo do bucket:")
    try:
        response = s3.list_objects_v2(Bucket=BUCKET, Prefix="results/")
        for obj in response.get("Contents", []):
            print(f"  {obj['Key']} ({obj['Size']} bytes)")
    except Exception as e:
        print(f"  Erro ao listar: {e}")


if __name__ == "__main__":
    upload_all()
