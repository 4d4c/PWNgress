import hashlib
import os
import sys


def read_settings_file(settings_filepath):
    """
    Read settings file and return dictionary with settings.
    """

    if not os.path.exists(settings_filepath):
        print("[-] ERROR: Settings file is missing")
        sys.exit(1)

    with open(settings_filepath, "r") as settings_file:
        settings = settings_file.read().splitlines()

    return dict(setting.split('=') for setting in settings)


def create_sha256_hash(str_to_hash):
    """
    Generate SHA-256 hash.
    """

    sha256_hash = hashlib.new("sha256")
    sha256_hash.update(str_to_hash.encode())

    return sha256_hash.hexdigest()
