"""Download objects from Amazon S3."""

import boto3


def download_s3_file(bucket_name: str, source_key: str, local_path: str) -> None:
    """Download an S3 object to a local path using the configured AWS credentials."""
    s3_client = boto3.client("s3")
    s3_client.download_file(bucket_name, source_key, local_path)
