"""Utility functions"""

# Standard libraries
from pathlib import Path

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# Third-party libraries
# Project libraries
from scan_cue.ui import ScannerUI


def merge_json_files(ui: ScannerUI, files_to_merge: list[Path], output_file: Path):
    """Merges json files

    Args:
        ui: The ui object
        files_to_merge: The json files to merge
        output_file: The output file
    """
    ui.show_progress_bar()
    ui.update_progress_bar(current_progress=0, total_progress=len(files_to_merge), description="Joining JSON files")
    with open(file=output_file, mode="wb") as combined_file:
        combined_file.write(b"[")
        for index, file_path in enumerate(files_to_merge, start=1):
            ui.advance_progress_bar()
            with open(file=file_path, mode="rb") as result_file:
                combined_file.write(result_file.read().replace(b"\r\n", b"")[1:-1])
            if index < len(files_to_merge):
                combined_file.write(b",")
        combined_file.write(b"]")
    ui.hide_progress_bar()


def create_ssh_key_pair(output_dir: Path) -> tuple[Path, Path]:
    """Creates an ssh key pair

    Args:
        output_dir: The directory to write the private and public keys to

    Returns:
        Private, public key path
    """
    key = rsa.generate_private_key(backend=default_backend(), public_exponent=65537, key_size=2048)

    # Serialize the private key to PEM format
    private_key = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # Serialize the public key to OpenSSH format
    public_key = key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    )

    # Write the private key to a file
    private_key_path = output_dir / "private_rsa.key"
    with open(private_key_path, "wb") as private_key_file:
        private_key_file.write(private_key)

    # Write the public key to a file
    public_key_path = output_dir / "public_rsa.key"
    with open(public_key_path, "wb") as public_key_file:
        public_key_file.write(public_key)

    return private_key_path, public_key_path
