"""Secure QUIC networking with TLS authentication.

Provides TLS-based authentication and encryption for QUIC connections between nodes.
Integrates with exo's existing QUIC networking layer.

Features:
- TLS 1.3 with certificate-based authentication
- Self-signed certificate generation for development
- Certificate pinning for production
- Mutual TLS (mTLS) support
- Certificate rotation
"""

import asyncio
import logging
import ssl
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtensionOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)


@dataclass
class TLSConfig:
    """TLS configuration for secure QUIC."""

    cert_path: Path
    """Path to TLS certificate file (PEM format)"""

    key_path: Path
    """Path to private key file (PEM format)"""

    ca_cert_path: Optional[Path] = None
    """Path to CA certificate for verification (None = self-signed)"""

    verify_mode: ssl.VerifyMode = ssl.CERT_REQUIRED
    """Certificate verification mode"""

    check_hostname: bool = True
    """Whether to verify hostname in certificate"""

    min_tls_version: ssl.TLSVersion = ssl.TLSVersion.TLSv1_3
    """Minimum TLS version (default: TLS 1.3)"""

    ciphers: Optional[str] = None
    """Allowed cipher suites (None = default secure ciphers)"""

    cert_expiry_days: int = 365
    """Certificate validity period for self-signed certs"""


class SecureQUICManager:
    """Manager for secure QUIC connections with TLS authentication."""

    def __init__(self, config: TLSConfig):
        """Initialize secure QUIC manager.

        Args:
            config: TLS configuration
        """
        self.config = config
        self._ssl_context: Optional[ssl.SSLContext] = None
        self._cert_fingerprint: Optional[str] = None

        logger.info("Secure QUIC manager initialized")

    async def initialize(self) -> None:
        """Initialize TLS context and load certificates."""
        try:
            # Ensure certificates exist
            if not self.config.cert_path.exists() or not self.config.key_path.exists():
                logger.info("Certificates not found, generating self-signed certificate...")
                await self._generate_self_signed_cert()

            # Create SSL context
            self._ssl_context = self._create_ssl_context()

            # Calculate certificate fingerprint for pinning
            self._cert_fingerprint = self._get_cert_fingerprint()

            logger.info(
                f"TLS initialized with certificate: {self.config.cert_path} "
                f"(fingerprint: {self._cert_fingerprint[:16]}...)"
            )

        except Exception as e:
            logger.error(f"Failed to initialize TLS: {e}")
            raise RuntimeError(f"TLS initialization failed: {e}") from e

    def _create_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context for QUIC connections.

        Returns:
            ssl.SSLContext: Configured SSL context
        """
        # Create context with TLS 1.3
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = self.config.min_tls_version

        # Load certificate and private key
        context.load_cert_chain(
            certfile=str(self.config.cert_path),
            keyfile=str(self.config.key_path),
        )

        # Configure verification
        context.verify_mode = self.config.verify_mode
        context.check_hostname = self.config.check_hostname

        # Load CA certificate if provided
        if self.config.ca_cert_path:
            context.load_verify_locations(cafile=str(self.config.ca_cert_path))

        # Set cipher suites
        if self.config.ciphers:
            context.set_ciphers(self.config.ciphers)
        else:
            # Use secure default ciphers (TLS 1.3)
            context.set_ciphers("TLS_AES_256_GCM_SHA384:TLS_AES_128_GCM_SHA256")

        # Disable compression (CRIME attack mitigation)
        context.options |= ssl.OP_NO_COMPRESSION

        logger.debug(f"SSL context created with TLS {self.config.min_tls_version}")

        return context

    async def _generate_self_signed_cert(self) -> None:
        """Generate self-signed certificate for development/testing.

        Creates a new RSA key pair and self-signed certificate.
        """
        try:
            # Generate private key
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend(),
            )

            # Generate certificate
            subject = issuer = x509.Name(
                [
                    x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                    x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
                    x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "exo"),
                    x509.NameAttribute(NameOID.COMMON_NAME, "exo-node"),
                ]
            )

            cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(private_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.now(tz=timezone.utc))
                .not_valid_after(
                    datetime.now(tz=timezone.utc)
                    + timedelta(days=self.config.cert_expiry_days)
                )
                .add_extension(
                    x509.SubjectAlternativeName([x509.DNSName("localhost")]),
                    critical=False,
                )
                .sign(private_key, hashes.SHA256(), default_backend())
            )

            # Ensure directory exists
            self.config.cert_path.parent.mkdir(parents=True, exist_ok=True)
            self.config.key_path.parent.mkdir(parents=True, exist_ok=True)

            # Write private key
            with open(self.config.key_path, "wb") as f:
                f.write(
                    private_key.private_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PrivateFormat.TraditionalOpenSSL,
                        encryption_algorithm=serialization.NoEncryption(),
                    )
                )

            # Write certificate
            with open(self.config.cert_path, "wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))

            logger.info(
                f"Generated self-signed certificate: {self.config.cert_path} "
                f"(valid for {self.config.cert_expiry_days} days)"
            )

        except Exception as e:
            logger.error(f"Failed to generate self-signed certificate: {e}")
            raise RuntimeError(f"Certificate generation failed: {e}") from e

    def _get_cert_fingerprint(self) -> str:
        """Calculate SHA256 fingerprint of certificate for pinning.

        Returns:
            str: Hex-encoded certificate fingerprint
        """
        try:
            with open(self.config.cert_path, "rb") as f:
                cert_data = f.read()

            cert = x509.load_pem_x509_certificate(cert_data, default_backend())
            fingerprint = cert.fingerprint(hashes.SHA256())

            return fingerprint.hex()

        except Exception as e:
            logger.warning(f"Failed to calculate certificate fingerprint: {e}")
            return ""

    def get_ssl_context(self) -> ssl.SSLContext:
        """Get SSL context for QUIC connections.

        Returns:
            ssl.SSLContext: Configured SSL context

        Raises:
            RuntimeError: If not initialized
        """
        if self._ssl_context is None:
            raise RuntimeError("SecureQUICManager not initialized")

        return self._ssl_context

    def get_cert_fingerprint(self) -> str:
        """Get certificate fingerprint for pinning.

        Returns:
            str: Hex-encoded certificate fingerprint

        Raises:
            RuntimeError: If not initialized
        """
        if self._cert_fingerprint is None:
            raise RuntimeError("SecureQUICManager not initialized")

        return self._cert_fingerprint

    async def verify_peer_certificate(
        self,
        peer_cert_der: bytes,
        expected_fingerprint: Optional[str] = None,
    ) -> bool:
        """Verify peer certificate.

        Args:
            peer_cert_der: Peer certificate in DER format
            expected_fingerprint: Expected certificate fingerprint (for pinning)

        Returns:
            bool: True if certificate is valid, False otherwise
        """
        try:
            # Load certificate
            cert = x509.load_der_x509_certificate(peer_cert_der, default_backend())

            # Check expiration
            now = datetime.now(tz=timezone.utc)
            if now < cert.not_valid_before_utc or now > cert.not_valid_after_utc:
                logger.warning("Peer certificate expired or not yet valid")
                return False

            # Check fingerprint if provided (certificate pinning)
            if expected_fingerprint:
                fingerprint = cert.fingerprint(hashes.SHA256()).hex()
                if fingerprint != expected_fingerprint:
                    logger.warning(
                        f"Certificate fingerprint mismatch: "
                        f"expected {expected_fingerprint[:16]}..., "
                        f"got {fingerprint[:16]}..."
                    )
                    return False

            logger.debug("Peer certificate verified successfully")
            return True

        except Exception as e:
            logger.warning(f"Failed to verify peer certificate: {e}")
            return False

    async def rotate_certificate(self) -> None:
        """Rotate certificate by generating a new one.

        Useful for periodic certificate rotation in production.
        """
        try:
            logger.info("Rotating TLS certificate...")

            # Backup old certificate
            backup_cert = self.config.cert_path.with_suffix(".pem.bak")
            backup_key = self.config.key_path.with_suffix(".pem.bak")

            if self.config.cert_path.exists():
                self.config.cert_path.rename(backup_cert)
            if self.config.key_path.exists():
                self.config.key_path.rename(backup_key)

            # Generate new certificate
            await self._generate_self_signed_cert()

            # Reinitialize SSL context
            self._ssl_context = self._create_ssl_context()
            self._cert_fingerprint = self._get_cert_fingerprint()

            logger.info(
                f"Certificate rotated successfully "
                f"(new fingerprint: {self._cert_fingerprint[:16]}...)"
            )

        except Exception as e:
            logger.error(f"Failed to rotate certificate: {e}")
            # Restore backup
            if backup_cert.exists():
                backup_cert.rename(self.config.cert_path)
            if backup_key.exists():
                backup_key.rename(self.config.key_path)
            raise RuntimeError(f"Certificate rotation failed: {e}") from e

    async def shutdown(self) -> None:
        """Cleanup secure QUIC manager."""
        self._ssl_context = None
        self._cert_fingerprint = None
        logger.info("Secure QUIC manager shutdown")


# ===== Helper Functions =====


def create_default_tls_config(
    cert_dir: Optional[Path] = None,
) -> TLSConfig:
    """Create default TLS configuration.

    Args:
        cert_dir: Directory for certificates (default: ~/.exo/certs)

    Returns:
        TLSConfig: Default configuration
    """
    if cert_dir is None:
        cert_dir = Path.home() / ".exo" / "certs"

    return TLSConfig(
        cert_path=cert_dir / "node.crt",
        key_path=cert_dir / "node.key",
        verify_mode=ssl.CERT_OPTIONAL,  # Allow self-signed for development
        check_hostname=False,  # Disable hostname check for cluster nodes
    )


def create_production_tls_config(
    cert_path: Path,
    key_path: Path,
    ca_cert_path: Path,
) -> TLSConfig:
    """Create production TLS configuration with CA verification.

    Args:
        cert_path: Path to node certificate
        key_path: Path to private key
        ca_cert_path: Path to CA certificate

    Returns:
        TLSConfig: Production configuration
    """
    return TLSConfig(
        cert_path=cert_path,
        key_path=key_path,
        ca_cert_path=ca_cert_path,
        verify_mode=ssl.CERT_REQUIRED,
        check_hostname=True,
        min_tls_version=ssl.TLSVersion.TLSv1_3,
    )
