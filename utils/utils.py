import os
import sys
import requests
import re


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
