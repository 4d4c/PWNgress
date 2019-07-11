import os
import sys
import sqlite3


def read_settings_file(settings_filepath):
    """
    Read settings file and return Discord token.
    """

    if not os.path.exists(settings_filepath):
        print("[-] ERROR: Settings file is missing")
        sys.exit(1)

    with open(settings_filepath, "r") as settings_file:
        settings = settings_file.read().splitlines()

    return dict(setting.split('=') for setting in settings)


def create_db(db_filename):
    """
    Create database structure.
    """

    db_conn = sqlite3.connect(db_filename)
    db_cursor = db_conn.cursor()

    db_cursor.execute("""
        CREATE TABLE names (
            id text,
            htb_name text,
            discord_name text
        )
    """)
    db_conn.commit()

    db_cursor.execute("""
        CREATE TABLE boxes (
            name text,
            score text,
            image text,
            wts text,
            working text,
            user text,
            root text
        )
    """)
    db_conn.commit()

    db_cursor.execute("""
        CREATE TABLE status_update (
            id text,
            status text
        )
    """)
    db_conn.commit()

settings_data = read_settings_file("settings.cfg")
create_db(settings_data["DB_FILENAME"])
