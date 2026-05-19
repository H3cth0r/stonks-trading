"""Tigris S3 client for Parquet archival.

Provides S3-compatible storage operations for:
- OHLCV data in Hive-style partitioned Parquet format
- Genome archives for disaster recovery
- Training artifacts and checkpoints

Compatible with both Tigris Cloud (production) and MinIO (local development).
"""

import gzip
from datetime import datetime
from io import BytesIO
from typing import Any

import boto3
import pandas as pd
from botocore.client import Config
from botocore.exceptions import ClientError

from stonks_trading.shared.ingest.adapter import Candle
from stonks_trading.shared.logger import logger


class TigrisClient:
    """Tigris S3-compatible storage client for Parquet archival.

    Stores OHLCV data in Hive-style partitioned Parquet format:
    s3://bucket/ohlcv/symbol=BTCUSDT/year=2024/month=03/data.parquet

    This format enables efficient querying by symbol and time range,
    and is compatible with data lake tools like DuckDB, Athena, etc.

    The client also supports archiving genomes as compressed pickles
    for disaster recovery and model versioning.

    Example:
        client = TigrisClient(
            endpoint="https://s3.us-east-1.tigris.dev",
            access_key="your_key",
            secret_key="your_secret",
            bucket="stonks-trading-data",
        )
        key = client.upload_ohlcv_partition("BTCUSDT", 2024, 3, df)
        df = client.download_ohlcv_partition("BTCUSDT", 2024, 3)
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
    ) -> None:
        """Initialize Tigris S3 client.

        Args:
            endpoint: S3 endpoint URL (Tigris or MinIO)
            access_key: S3 access key
            secret_key: S3 secret key
            bucket: Bucket name
        """
        self.bucket = bucket
        self.endpoint = endpoint

        self.s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4"),
        )

        logger.info(
            "Tigris S3 client initialized",
            endpoint=endpoint,
            bucket=bucket,
        )

    def upload_ohlcv_partition(
        self,
        symbol: str,
        year: int,
        month: int,
        df: pd.DataFrame,
    ) -> str:
        """Upload OHLCV data as Parquet partition.

        Stores data in Hive-style partition format:
        ohlcv/symbol={symbol}/year={year}/month={month:02d}/data.parquet

        Uses zstd compression for efficient storage.

        Args:
            symbol: Trading symbol (e.g., BTCUSDT)
            year: Year partition (e.g., 2024)
            month: Month partition (e.g., 3 for March)
            df: DataFrame with OHLCV columns

        Returns:
            S3 key of uploaded object

        Raises:
            ClientError: If upload fails
        """
        key = f"ohlcv/symbol={symbol}/year={year}/month={month:02d}/data.parquet"

        # Convert to Parquet in memory
        buffer = BytesIO()
        df.to_parquet(buffer, index=False, compression="zstd")
        buffer.seek(0)

        try:
            self.s3.upload_fileobj(
                buffer,
                self.bucket,
                key,
            )

            logger.info(
                "Uploaded OHLCV partition to S3",
                bucket=self.bucket,
                key=key,
                rows=len(df),
                size_bytes=buffer.getbuffer().nbytes,
            )

            return key

        except ClientError as e:
            logger.error(
                "Failed to upload OHLCV partition",
                error=str(e),
                bucket=self.bucket,
                key=key,
            )
            raise

    def download_ohlcv_partition(
        self,
        symbol: str,
        year: int,
        month: int,
    ) -> pd.DataFrame | None:
        """Download OHLCV Parquet partition.

        Downloads and parses a Parquet partition from S3.

        Args:
            symbol: Trading symbol (e.g., BTCUSDT)
            year: Year partition (e.g., 2024)
            month: Month partition (e.g., 3 for March)

        Returns:
            DataFrame with OHLCV data, or None if partition doesn't exist

        Raises:
            ClientError: If download fails (other than NoSuchKey)
        """
        key = f"ohlcv/symbol={symbol}/year={year}/month={month:02d}/data.parquet"

        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=key)
            df = pd.read_parquet(BytesIO(response["Body"].read()))

            logger.info(
                "Downloaded OHLCV partition from S3",
                bucket=self.bucket,
                key=key,
                rows=len(df),
            )

            return df

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "NoSuchKey":
                logger.debug(
                    "OHLCV partition not found in S3",
                    bucket=self.bucket,
                    key=key,
                )
                return None
            raise

    def archive_genome(
        self,
        genome_id: str,
        genome_data: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Archive pickled genome to S3.

        Stores a compressed genome pickle for disaster recovery.
        Genomes are organized by archive date for easy lifecycle management.

        Args:
            genome_id: Unique genome identifier
            genome_data: Pickled genome bytes
            metadata: Optional metadata dictionary (stored as JSON sidecar)

        Returns:
            S3 key of archived genome

        Raises:
            ClientError: If upload fails
        """
        now = datetime.utcnow()
        key = f"genomes/archive/{now.year}/{now.month:02d}/{genome_id}.pkl.gz"

        # Compress the genome data
        compressed = gzip.compress(genome_data)

        try:
            self.s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=compressed,
                ContentEncoding="gzip",
            )

            # Upload metadata sidecar if provided
            if metadata:
                metadata_key = f"genomes/archive/{now.year}/{now.month:02d}/{genome_id}.json"
                import json

                self.s3.put_object(
                    Bucket=self.bucket,
                    Key=metadata_key,
                    Body=json.dumps(metadata, default=str).encode(),
                    ContentType="application/json",
                )

            logger.info(
                "Archived genome to S3",
                bucket=self.bucket,
                key=key,
                genome_id=genome_id,
                original_size=len(genome_data),
                compressed_size=len(compressed),
            )

            return key

        except ClientError as e:
            logger.error(
                "Failed to archive genome",
                error=str(e),
                bucket=self.bucket,
                key=key,
            )
            raise

    def download_genome(self, genome_key: str) -> bytes | None:
        """Download archived genome from S3.

        Args:
            genome_key: S3 key of the genome (e.g., genomes/archive/2024/03/genome_123.pkl.gz)

        Returns:
            Decompressed genome bytes, or None if not found

        Raises:
            ClientError: If download fails (other than NoSuchKey)
        """
        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=genome_key)
            compressed = response["Body"].read()
            decompressed = gzip.decompress(compressed)

            logger.info(
                "Downloaded genome from S3",
                bucket=self.bucket,
                key=genome_key,
                compressed_size=len(compressed),
                decompressed_size=len(decompressed),
            )

            return decompressed

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "NoSuchKey":
                logger.debug(
                    "Genome not found in S3",
                    bucket=self.bucket,
                    key=genome_key,
                )
                return None
            raise

    def upload_candles_as_partition(
        self,
        symbol: str,
        candles: list[Candle],
    ) -> str:
        """Upload a list of candles as a Parquet partition.

        Convenience method that converts candles to DataFrame and uploads
        to the appropriate year/month partition based on candle timestamps.

        Args:
            symbol: Trading symbol
            candles: List of normalized candles

        Returns:
            S3 key of uploaded partition

        Raises:
            ValueError: If candles list is empty
            ClientError: If upload fails
        """
        if not candles:
            raise ValueError("Cannot upload empty candle list")

        # Convert candles to DataFrame
        df = pd.DataFrame([
            {
                "timestamp": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
                "venue": c.venue,
            }
            for c in candles
        ])

        # Determine partition from timestamp range
        timestamps = [c.timestamp for c in candles]
        year = max(ts.year for ts in timestamps)
        month = max(ts.month for ts in timestamps)

        return self.upload_ohlcv_partition(symbol, year, month, df)

    def list_partitions(
        self,
        symbol: str,
        prefix: str = "ohlcv",
    ) -> list[dict[str, Any]]:
        """List available partitions for a symbol.

        Args:
            symbol: Trading symbol to list partitions for
            prefix: S3 prefix (default: ohlcv)

        Returns:
            List of partition information dictionaries
        """
        prefix_path = f"{prefix}/symbol={symbol}/"

        try:
            response = self.s3.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix_path,
            )

            partitions = []
            for obj in response.get("Contents", []):
                key = obj["Key"]
                # Parse partition info from key
                # Format: ohlcv/symbol=X/year=Y/month=M/data.parquet
                parts = key.split("/")
                if len(parts) >= 4 and parts[-1] == "data.parquet":
                    year = int(parts[2].split("=")[1])
                    month = int(parts[3].split("=")[1])
                    partitions.append({
                        "key": key,
                        "symbol": symbol,
                        "year": year,
                        "month": month,
                        "size": obj["Size"],
                        "last_modified": obj["LastModified"],
                    })

            return partitions

        except ClientError as e:
            logger.error(
                "Failed to list partitions",
                error=str(e),
                bucket=self.bucket,
                prefix=prefix_path,
            )
            raise

    def check_health(self) -> dict[str, Any]:
        """Check S3 connection health.

        Verifies the S3 connection by listing the bucket.

        Returns:
            Health status dictionary
        """
        try:
            self.s3.head_bucket(Bucket=self.bucket)
            return {
                "status": "healthy",
                "endpoint": self.endpoint,
                "bucket": self.bucket,
            }
        except ClientError as e:
            return {
                "status": "unhealthy",
                "endpoint": self.endpoint,
                "bucket": self.bucket,
                "error": str(e),
            }
